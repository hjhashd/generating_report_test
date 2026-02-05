import os
import sys
import json
import time
import logging
# 异步库
import asyncio
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List, AsyncGenerator

from langchain_openai import ChatOpenAI
# 修复点 1：确保导入 ChatOllama 以配合 fallback 函数
from langchain_ollama import ChatOllama 
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from utils.chat_session_manager import ChatSessionManager

# =========================
# 项目路径 & 日志
# =========================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO) # 移除此行，由主程序统一配置

# =========================
# 全局模型实例和状态
# =========================
ONLINE_LLM = None
LOCAL_LLM = None

# 记录当前在线模型的配置，用于检测是否需要重新初始化
CURRENT_ONLINE_CONFIG = {
    "model_name": None,
    "base_url": None,
    "api_key": None
}

MODEL_STATUS = {
    "online": "NOT_INIT",
    "local": "NOT_INIT",
}

# =========================
# 全局会话（Redis + Memory）
# =========================
# Initialize Manager with 'chat:search' session type
session_manager = ChatSessionManager(session_type="chat:search")

# =========================
# 强制搜索 System Prompt
# =========================
def build_search_system_prompt() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""
今天日期：{today}

你是一个政务级 AI 搜索与分析引擎，必须严格遵循以下流程，不得跳过：

【强制 Workflow】
1. 无论用户提出什么问题，你必须首先调用 web_search。
2. 在调用 web_search 之前，严禁输出任何实质性回答内容。
3. web_search 的 arguments 中，必须包含 1–3 个可检索关键词。
4. 最终回答只能基于搜索结果。

【结果约束】
- 若搜索结果为空，必须回复：
  “联网搜索未找到相关信息”
- 若存在结果：
  - 行文正式
  - 明确说明“根据联网搜索结果”

禁止闲聊。
"""

# =========================
# 初始化模型
# =========================
def init_online_llm(model_name: str, base_url: str, api_key: str) -> ChatOpenAI:
    logger.info(f"初始化【在线搜索模型】: {model_name}")
    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.2,
        streaming=True,
        timeout=120, # 增加超时时间到 120 秒，适应慢速网络或复杂思考
        max_retries=1, # 减少重试次数，以便快速进入 fallback
    )

# 修复点 2：统一使用 ChatOpenAI 结构调用本地 Ollama 接口
def init_local_llm() -> ChatOpenAI:
    logger.warning("⚠️ 切换至【本地 Ollama 模型】")
    # 根据用户要求，使用 qwen3-coder:30b 或 llama3.2:3b
    # 这里默认优先使用性能更强的 qwen3-coder:30b
    return ChatOpenAI(
        model="qwen3-coder:30b",
        base_url="http://localhost:11434/v1",
        api_key="ollama", 
        temperature=0.2,
        streaming=True,
    )

def should_fallback_to_local(e: Exception) -> bool:
    msg = str(e).lower()
    type_name = type(e).__name__.lower()
    logger.warning(f"正在检查是否需要降级 | 异常类型: {type(e).__name__} | 异常消息: {msg}")
    
    # 只要是在线模型授权失败(401)、余额不足(402)、Key无效、或额度超限、模型未找到(404)、超时或连接失败，都触发降级
    reasons = [
        "401", "402", "404", "not found", "incorrect api key", 
        "insufficient balance", "exceeded_current_quota", "authentication",
        "timeout", "connection", "connect", "unreachable", "rate_limit"
    ]
    
    if any(r in msg for r in reasons) or any(r in type_name for r in reasons):
        return True
        
    return False

# =========================
# 异步初始化模型
# =========================
async def async_init_online_llm(model_name: str, base_url: str, api_key: str):
    global ONLINE_LLM
    logger.info(f"🔄 异步初始化【在线搜索模型】: {model_name}")
    ONLINE_LLM = init_online_llm(model_name, base_url, api_key)
    MODEL_STATUS["online"] = "READY"
    logger.info(f"✅ 【在线搜索模型】初始化完成")

async def async_init_local_llm():
    global LOCAL_LLM
    logger.info(f"🔄 异步初始化【本地 Ollama 模型】")
    LOCAL_LLM = init_local_llm()
    # 预热本地模型，避免首次推理耗时过长
    try:
        await LOCAL_LLM.ainvoke([HumanMessage(content="Hello")])
        logger.info(f"✅ 【本地 Ollama 模型】预热完成")
    except Exception as e:
        logger.error(f"❌ 本地模型预热失败: {e}")
    MODEL_STATUS["local"] = "READY"
    logger.info(f"✅ 【本地 Ollama 模型】初始化完成")

# 修复点 5：解决 init_search_llm_with_fallback 的逻辑重复和类定义不一致
def init_search_llm_with_fallback(
    model_name: str,
    base_url: str,
    api_key: str,
):
    if not api_key or not api_key.strip():
        logger.warning("⚠️ 未检测到 API Key，直接使用本地搜索模型")
        return ChatOllama(
            model="deepseek-r1:32b",
            base_url="http://localhost:11434", # 修复：ChatOllama 基础地址不需要 /v1
            temperature=0.2,
        )

    try:
        logger.info(f"尝试初始化在线模型: {model_name}")
        return ChatOpenAI(
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            temperature=0.2,
            streaming=True,
        )
    except Exception as e:
        logger.error(f"初始化失败，降级本地: {e}")
        return ChatOllama(
            model="deepseek-r1:32b",
            base_url="http://localhost:11434",
            temperature=0.2,
        )

# =========================
# 联网搜索实现 (基于 360 搜索爬取 - 更适合国内环境)
# =========================
async def web_search(query: str, max_results: int = 5) -> str:
    """
    真实的联网搜索实现。使用 360 搜索 (so.com) 并解析结果。
    """
    logger.info(f"🌐 正在执行真实联网搜索 (360): {query}")
    url = f"https://www.so.com/s?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            # 360 搜索结果通常在 li.res-list 中
            result_items = soup.select("li.res-list")
            
            for item in result_items[:max_results]:
                title_tag = item.select_one("h3 a")
                if not title_tag:
                    continue
                    
                title = title_tag.get_text(strip=True)
                # 360 有时会把真实链接放在 data-url 中
                link = title_tag.get("data-url") or title_tag.get("href", "")
                
                # 尝试获取摘要
                snippet_tag = item.select_one(".res-desc") or item.select_one(".res-comm-con")
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else "暂无摘要"
                
                results.append(f"标题: {title}\n链接: {link}\n摘要: {snippet}")
            
            if not results:
                logger.warning("360 搜索未返回有效结果")
                return "联网搜索未找到相关信息。"
                
            return "\n\n".join(results)
            
    except Exception as e:
        logger.error(f"联网搜索失败: {e}")
        return f"联网搜索遇到错误: {str(e)}"


# =========================
# 核心搜索生成器
# =========================
import json
import logging
from typing import AsyncGenerator
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)

async def Search_Chat_Generator_Stream(
    user_query: str,
    model_name: str,
    base_url: str,
    api_key: str,
    task_id: str,
) -> AsyncGenerator[str, None]:
    global ONLINE_LLM, LOCAL_LLM, CURRENT_ONLINE_CONFIG
    
    start_time = time.time()
    masked_key = f"{api_key[:6]}******{api_key[-4:]}" if api_key and len(api_key) > 10 else "******"
    logger.info(f"🚀 [AI Search Start] TaskID: {task_id} | Query: {user_query[:100]}... | Model: {model_name}")
    logger.info(f"🔧 [AI Search Config] BaseURL: {base_url} | API Key: {masked_key}")

    # 1. 自动初始化/更新在线模型逻辑
    config_changed = (
        model_name != CURRENT_ONLINE_CONFIG["model_name"] or
        base_url != CURRENT_ONLINE_CONFIG["base_url"] or
        api_key != CURRENT_ONLINE_CONFIG["api_key"]
    )
    
    if ONLINE_LLM is None or config_changed:
        try:
            # 假设该函数已在外部定义
            await async_init_online_llm(model_name, base_url, api_key)
            CURRENT_ONLINE_CONFIG = {
                "model_name": model_name,
                "base_url": base_url,
                "api_key": api_key
            }
        except Exception as e:
            logger.error(f"在线模型初始化失败: {e}")
            MODEL_STATUS["online"] = "ERROR"

    history = session_manager.get_session(task_id)
    if not history:
        history = []

    # 2. 在线状态预检查 (修正了 f-string 引号冲突)
    if MODEL_STATUS.get("online") != "READY":
         status_val = MODEL_STATUS.get("online", "UNKNOWN")
         msg = f"❌ 在线模型未就绪 ({status_val})，请检查配置或网络连接。"
         err_payload = json.dumps({"content": msg}, ensure_ascii=False)
         yield f"data: {err_payload}\n\n"
         return

# --- 修复后的工具定义 ---
# 3. 构造工具集 (修正版：兼容 LangChain 校验)
    # is_moonshot = "moonshot" in base_url.lower()
    
    tools = []
    # if is_moonshot:
    #     # 伪装内置搜索，绕过 Unsupported function 报错
    #     tools.append({
    #         "type": "function",
    #         "function": {
    #             "name": "$web_search",
    #             "description": "内置搜索",
    #             "parameters": {"type": "object", "properties": {}}
    #         }
    #     })
    
    tools.append({
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "自定义搜索",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }
        }
    })

    messages = [
        SystemMessage(content=build_search_system_prompt()),
        *history,
        HumanMessage(content=user_query),
    ]

    try:
        # 第一阶段：使用 ainvoke 探测工具调用 (确保 Kimi 内置搜索握手稳定)
        llm_with_tools = ONLINE_LLM.bind_tools(tools)
        response = await llm_with_tools.ainvoke(messages)
        
        # 记录是否触发了工具
        if response.tool_calls:
            logger.info(f"🛠️ [AI Search Tool] Triggered: {len(response.tool_calls)} tools | TaskID: {task_id}")
            for tc in response.tool_calls:
                logger.info(f"   -> Tool: {tc['name']} | Args: {tc['args']}")
                # --- A 计划：Kimi 内置搜索协议 ---
                if tc["name"] == "$web_search":
                    payload = json.dumps({"content": "🌐 激活 Kimi 原生联网搜索...\n\n"}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    
                    messages.append(response)
                    # Kimi 协议核心：ToolMessage 的 content 必须是原始 args 的 JSON 字符串
                    messages.append(ToolMessage(
                        content=json.dumps(tc["args"], ensure_ascii=False),
                        tool_call_id=tc["id"]
                    ))
                
                # --- B 计划：手写 web_search 兜底 ---
                elif tc["name"] == "web_search":
                    s_query = tc["args"].get("query", user_query)
                    payload = json.dumps({"content": f"🔍 正在执行手写增强搜索: {s_query}...\n\n"}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    
                    # 执行您原有的 web_search 函数
                    s_results = await web_search(s_query)
                    logger.info(f"📄 [AI Search Result] Length: {len(s_results)} chars | TaskID: {task_id}")
                    messages.append(response)
                    messages.append(ToolMessage(content=s_results, tool_call_id=tc["id"]))

        # 第二阶段：生成最终流式回答 (修正了 f-string 反斜杠错误)
        logger.info(f"🌊 [AI Search Stream] Starting final response generation... | TaskID: {task_id}")
        full_answer = ""
        async for chunk in ONLINE_LLM.astream(messages):
            if chunk.content:
                full_answer += chunk.content
                # 修复：先 dumps 变量，避免 yield f-string 中出现复杂转义
                chunk_payload = json.dumps({"content": chunk.content}, ensure_ascii=False)
                yield f"data: {chunk_payload}\n\n"
        
        yield "data: [DONE]\n\n"
        
        duration = time.time() - start_time
        logger.info(f"✅ [AI Search Done] TaskID: {task_id} | Total Time: {duration:.2f}s | Output Length: {len(full_answer)}")

        # 更新对话历史
        history.append(HumanMessage(content=user_query))
        history.append(AIMessage(content=full_answer))
        session_manager.update_session(task_id, history)

    except Exception as e:
        logger.error(f"❌ [AI Search Error] TaskID: {task_id} | Error: {str(e)}", exc_info=True)
        # 构造错误消息 payload
        error_str = str(e).lower()
        if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
            err_msg = "⚠️ 在线服务繁忙（429 Too Many Requests），正在为您切换至备用通道或请稍后再试..."
        elif "401" in error_str or "auth" in error_str:
            err_msg = "⚠️ 鉴权失败，请检查 API Key 配置。"
        elif "timeout" in error_str:
            err_msg = "⚠️ 网络请求超时，请检查网络连接。"
        else:
            err_msg = f"❌ 在线服务调用失败: {str(e)}"
            
        err_payload = json.dumps({"content": err_msg}, ensure_ascii=False)
        yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"

# =========================
# 本地调试 (已适配异步)
# =========================
if __name__ == "__main__":
    TEST_TASK_ID = "search_debug_001"
    # --- 在这里修改配置 ---
    MODEL_NAME = "kimi-k2-turbo-preview" # 或者是你截图中看到的模型名
    BASE_URL = "https://api.moonshot.cn/v1"
    API_KEY = "sk-3xjbiepAHiU219dDIemODxQdsBem1aAv2hdDb7HlpWKE908c" 
    async def main_async():
        # 在进程启动时异步初始化模型
        await asyncio.gather(
            async_init_online_llm(MODEL_NAME, BASE_URL, API_KEY),
            async_init_local_llm()
        )

        # 等待模型初始化完成
        while MODEL_STATUS["online"] != "READY" and MODEL_STATUS["local"] != "READY":
            await asyncio.sleep(0.1)

        await run_round_async("2026年我国节能降碳工作的主要政策规划是什么？")

    async def run_round_async(query: str):
        print("\n" + "=" * 30)
        print(f"用户问题: {query}")
        print("=" * 30 + "\n")

        start_time = time.time()
        first_token_time = None
        total_content = ""

        # 获取异步生成器
        generator = Search_Chat_Generator_Stream(
            user_query=query,
            model_name=MODEL_NAME,
            base_url=BASE_URL,
            api_key=API_KEY,
            task_id=TEST_TASK_ID,
        )

        # 关键：使用 async for 遍历异步生成器
        async for event in generator:
            if "[DONE]" in event:
                break
            if "data:" not in event:
                continue

            try:
                json_str = event.replace("data:", "").strip()
                if not json_str:
                    continue
                payload = json.loads(json_str)

                if first_token_time is None and "content" in payload:
                    first_token_time = time.time()
                    print(f"💡 首字耗时: {first_token_time - start_time:.2f}s\n" + "-" * 30)

                if "content" in payload:
                    print(payload["content"], end="", flush=True)
                    total_content += payload["content"]

                if "error" in payload:
                    print(f"\n❌ Error: {payload['error']}")

            except Exception:
                pass

        print("\n\n" + "-" * 30)
        print(f"⏱️ 总耗时: {time.time() - start_time:.2f}s")
        print(f"📄 输出字数: {len(total_content)}")

    # 使用 asyncio.run() 正确地运行异步主函数
    asyncio.run(main_async())
