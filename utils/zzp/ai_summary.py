import os
import sys
import json
import logging
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from cryptography.fernet import Fernet

# LangChain 相关库
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# ==========================================
# 0. 基础配置
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

# 🔐 密钥 (保持与原项目一致)
ENCRYPTION_KEY = b'8P_Gk9wz9qKj-4t8z9qKj-4t8z9qKj-4t8z9qKj-4t8=' 
cipher_suite = Fernet(ENCRYPTION_KEY)
logger = logging.getLogger(__name__)

# ==========================================
# 1. 工具函数 (复用原逻辑)
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def decrypt_text(encrypted_str):
    if not encrypted_str: return None
    try:
        return cipher_suite.decrypt(encrypted_str.encode()).decode()
    except Exception:
        return ""

def get_llm_config_by_id(model_id):
    """根据ID从数据库获取模型配置"""
    engine = get_db_connection()
    sql = text("SELECT llm_type, model_name, api_key, base_url FROM llm_config WHERE id = :id")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"id": model_id}).fetchone()
            if result:
                llm_type, model_name, encrypted_key, base_url = result
                api_key = decrypt_text(encrypted_key) if encrypted_key else ""
                return {
                    "llm_type": llm_type, "model_name": model_name,
                    "api_key": api_key, "base_url": base_url
                }
    except Exception as e:
        logger.error(f"读取配置失败: {e}")
    return None

def init_llm_instance(config_data):
    """初始化 LLM 实例"""
    if not config_data: raise ValueError("配置数据为空")

    llm_type = config_data['llm_type']
    model_name = config_data['model_name']
    base_url = config_data['base_url']
    api_key = config_data['api_key']

    print(f"🚀 初始化总结模型: [{llm_type}] {model_name}")
    
    if llm_type == "local":
        return ChatOllama(model=model_name, base_url=base_url, temperature=0.3, num_ctx=8192)
    elif llm_type in ["online", "custom"]:
        return ChatOpenAI(
            api_key=api_key, 
            base_url=base_url, 
            model=model_name, 
            temperature=0.3, # 总结任务稍微增加一点确定性
            streaming=True
        )
    else:
        raise ValueError(f"不支持的模型类型: {llm_type}")

# ==========================================
# 2. 核心总结功能函数
# ==========================================

def ai_summary_stream(input_text, model_id, custom_instruction=None, user_id=None):
    """
    对输入文本进行 AI 总结
    :param input_text: 前端传入的待总结文本
    :param model_id: 数据库中的模型 ID
    :param custom_instruction: (可选) 自定义总结要求，如'扩写'、'翻译'等，默认为'总结'
    :param user_id: (可选) 当前操作的用户 ID，用于权限校验或获取私有配置
    """
    
    # 1. 验证输入
    if not input_text or len(input_text.strip()) == 0:
        yield f"data: {json.dumps({'error': 'Input text is empty'})}\n\n"
        return

    # 2. 获取模型配置
    llm_config = get_llm_config_by_id(model_id)
    if not llm_config:
        yield f"data: {json.dumps({'error': 'Model config not found'})}\n\n"
        return

    # 3. 构建 Prompt
    # 如果没有特定的自定义指令，默认使用总结指令
    if not custom_instruction:
        custom_instruction = "请对以下内容进行精炼的总结，提取核心观点，语言通顺、逻辑清晰。"

    system_prompt = f"""
你是一个专业的文本分析与总结助手。
任务目标：{custom_instruction}
要求：
1. 保持客观，不添加原文不存在的信息。
2. 输出格式直接为纯文本，不要Markdown代码块包裹。
"""

    try:
        # 4. 初始化模型
        llm = init_llm_instance(llm_config)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"【待处理文本】：\n{input_text}")
        ]

        # 5. 流式生成
        full_response = ""
        for chunk in llm.stream(messages):
            text_chunk = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if text_chunk:
                full_response += text_chunk
                # SSE 格式返回
                yield f"data: {json.dumps({'content': text_chunk}, ensure_ascii=False)}\n\n"
        
        # 结束标记
        yield "data: [DONE]\n\n"
        logger.info("总结任务完成")

    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

# ==========================================
# 3. 测试入口
# ==========================================
if __name__ == "__main__":
    # --- 模拟前端输入 ---
    TEST_MODEL_ID = 6  # 确保数据库里有这个ID
    
    # 模拟一段长文本
    TEST_TEXT = """
    近年来，随着全球气候变化问题日益严峻，各国纷纷提出了碳达峰、碳中和的目标。节能降碳不仅是应对气候变化的必然选择，也是推动经济高质量发展的内在要求。
    我们需要在工业、建筑、交通等重点领域实施节能改造，推广绿色低碳技术。同时，要倡导绿色低碳的生活方式，鼓励公众参与节能减排。
    政府应出台相关政策，完善能源价格机制，加大对新能源产业的扶持力度。企业要积极承担社会责任，加强能源管理，降低生产过程中的碳排放。
    通过全社会的共同努力，我们一定能够实现节能降碳的目标，建设美丽家园。
    """
    
    print(f"📝 待总结字数: {len(TEST_TEXT)}")
    print("-" * 30)

    # 调用生成器
    generator = ai_summary_stream(TEST_TEXT, TEST_MODEL_ID)

    print("🤖 AI 正在总结中...\n")
    final_result = ""
    
    for event in generator:
        if "[DONE]" in event:
            break
        
        try:
            # 解析 SSE 数据
            json_str = event.replace("data: ", "").strip()
            data = json.loads(json_str)
            
            if "content" in data:
                chunk = data["content"]
                print(chunk, end="", flush=True)
                final_result += chunk
            
            if "error" in data:
                print(f"\n❌ Error: {data['error']}")
        except Exception as e:
            pass

    print("\n\n✅ 结束")