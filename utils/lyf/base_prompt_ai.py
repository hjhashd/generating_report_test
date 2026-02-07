import httpx
from openai import OpenAI
from typing import Dict, List
import server_config

# ==========================================
# 1. 全局 AI 配置
# ==========================================
class AISettings:
    # 基础连接配置
    API_KEY = server_config.AI_API_KEY
    BASE_URL = server_config.AI_BASE_URL
    MODEL_NAME = server_config.AI_MODEL_NAME
    
    # --- 安全与性能控制 ---
    
    # 细化超时控制 (单位: 秒)
    CONNECT_TIMEOUT = 5.0    # 建立 TCP 连接的最长等待时间
    READ_TIMEOUT = 60.0      # 核心：等待模型吐字（及首字）的最长间隔
    WRITE_TIMEOUT = 5.0      # 发送请求数据的时间
    POOL_TIMEOUT = 10.0      # 从连接池获取可用连接的时间
    
    MAX_TOKENS_LIMIT = 2048  # 强制限制单次输出 Token 数，防止显存溢出
    TEMPERATURE_DEFAULT = 0.3

# ==========================================
# 2. 全局会话管理 (内存级，实现用户隔离)
# ==========================================
class SessionManager:
    """
    用于隔离不同用户的上下文历史记录
    结构: { "user_id": [{"role": "...", "content": "..."}] }
    """
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, str]]] = {}

    def get_history(self, user_id: str) -> List[Dict[str, str]]:
        if not user_id:
            return []
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        return self._sessions[user_id]

    def update_history(self, user_id: str, messages: List[Dict[str, str]]):
        """更新历史并防止内存无限增长"""
        if not user_id:
            return
        # 限制单个会话的记忆长度（如只保留最近20条），保护服务器内存
        if len(messages) > 20:
            messages = messages[-20:]
        self._sessions[user_id] = messages

    def clear_session(self, user_id: str):
        if user_id in self._sessions:
            del self._sessions[user_id]

# ==========================================
# 3. AI 基础服务类 (单例模式)
# ==========================================
class BasePromptAI:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BasePromptAI, cls).__new__(cls)
            
            # 1. 组装复杂的超时逻辑
            # timeout=None 表示不设总耗时限制，只要 READ_TIMEOUT 不触发，生成就不会中断
            custom_timeout = httpx.Timeout(
                timeout=None, 
                connect=AISettings.CONNECT_TIMEOUT,
                read=AISettings.READ_TIMEOUT,
                write=AISettings.WRITE_TIMEOUT,
                pool=AISettings.POOL_TIMEOUT
            )

            # 2. 使用自定义的 httpx 客户端初始化 OpenAI
            # 增加 limits 配置以进一步保护系统句柄资源
            
            # --- 智能网络探测与分流逻辑 ---
            # 1. 优先获取 .env 配置
            api_key = AISettings.API_KEY
            base_url = AISettings.BASE_URL
            model_name = AISettings.MODEL_NAME
            
            candidates = []
            # 候选1: .env 配置 (优先级最高)
            if base_url:
                candidates.append({
                    "url": base_url, 
                    "key": api_key, 
                    "model": model_name, 
                    "source": "ENV"
                })
            
            # 候选2: localhost (用于回退)
            if "localhost" not in base_url and "127.0.0.1" not in base_url:
                 candidates.append({
                    "url": "http://localhost:8005/v1", 
                    "key": api_key, 
                    "model": model_name, 
                    "source": "Localhost"
                })

            # 探测逻辑
            selected_config = None
            
            print(f"🔍 [BasePromptAI] Starting network connectivity check...")
            
            for cand in candidates:
                url = cand["url"]
                print(f"   -> Probing {url} ({cand['source']})...")
                try:
                    # 尝试探测 /models 接口或仅做简单的 TCP 连接
                    # 注意：httpx.get 需要完整的 url，这里我们只测试根路径或 v1
                    probe_url = url.rstrip("/")
                    # 很多 OpenAI 兼容接口支持 GET /models
                    with httpx.Client(timeout=2.0) as client: # 快速探测，2秒超时
                        resp = client.get(f"{probe_url}/models", headers={"Authorization": f"Bearer {cand['key']}"})
                        if resp.status_code == 200:
                            print(f"✅ [BasePromptAI] Connection success: {url}")
                            selected_config = cand
                            break
                        else:
                            print(f"⚠️ [BasePromptAI] Connected but returned {resp.status_code}: {url}")
                            # 即使状态码不对，只要连通了，也可以尝试用？
                            # 不，稳妥起见，如果非200可能认证失败，但这里是探测网络。
                            # 考虑到 Key 可能为 EMPTY，某些服务可能会 401。
                            # 如果是 401/403，说明网络是通的！也可以用！
                            if resp.status_code in [401, 403]:
                                print(f"✅ [BasePromptAI] Network reachable (Auth error ignored): {url}")
                                selected_config = cand
                                break
                except Exception as e:
                    print(f"❌ [BasePromptAI] Connection failed to {url}: {e}")

            # 3. 如果所有网络探测都失败，或者 API_KEY 为空且未探测到有效服务，
            # 尝试回退到数据库 (Kimi 等在线模型)
            if not selected_config and (not api_key or api_key == "EMPTY"):
                 print("⚠️ [BasePromptAI] All network probes failed or invalid config. Falling back to Database...")
                 try:
                    from utils.zzp.ai_generate_langchain import get_default_llm_config
                    db_config = get_default_llm_config()
                    if db_config:
                        selected_config = {
                            "url": db_config.get("base_url"),
                            "key": db_config.get("api_key"),
                            "model": db_config.get("model_name"),
                            "source": "Database"
                        }
                        print(f"✅ [BasePromptAI] Loaded config from DB: {selected_config['model']}")
                 except Exception as e:
                     print(f"❌ [BasePromptAI] DB fallback failed: {e}")

            # 应用最终配置
            if selected_config:
                api_key = selected_config["key"]
                base_url = selected_config["url"]
                model_name = selected_config["model"]
                print(f"🚀 [BasePromptAI] Final Config: {model_name} @ {base_url} ({selected_config['source']})")
            else:
                print("❌ [BasePromptAI] No valid configuration found! Using default ENV values.")

            cls._instance.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=httpx.Client(
                    timeout=custom_timeout,
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
                )
            )
            
            cls._instance.model_name = model_name
            # 实例化会话管理器
            cls._instance.session_manager = SessionManager()
            
        return cls._instance

    def get_client(self) -> OpenAI:
        return self.client

    def get_model_name(self) -> str:
        return self.model_name

    def get_session_manager(self) -> SessionManager:
        return self.session_manager

# 导出全局单例实例
base_ai = BasePromptAI()
