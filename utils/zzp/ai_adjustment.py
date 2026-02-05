import os
import sys
import json
import re
import time
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

# 数据库与加密相关
import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from cryptography.fernet import Fernet

# LangChain 相关库
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from utils.chat_session_manager import ChatSessionManager

# ==============================
# 0. 基础配置 & 密钥管理
# ==============================
# 确保可以引入同级或上级模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

ENCRYPTION_KEY = b'8P_Gk9wz9qKj-4t8z9qKj-4t8z9qKj-4t8z9qKj-4t8=' 
cipher_suite = Fernet(ENCRYPTION_KEY)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LangChainOptimizer")

# ==============================
# 1. 数据库工具函数
# ==============================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def decrypt_text(encrypted_str):
    if not encrypted_str: return ""
    try:
        return cipher_suite.decrypt(encrypted_str.encode()).decode()
    except Exception:
        # Fallback: if it looks like a raw key (starts with "sk-"), return it directly
        if encrypted_str.startswith("sk-"):
            return encrypted_str
        return ""

def get_llm_config_by_id(model_id):
    """从数据库获取模型配置"""
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

# ==============================
# 2. 会话管理 (Redis + Memory)
# ==============================
# Initialize Manager with 'chat:optimize' session type
session_manager = ChatSessionManager(session_type="chat:optimize") 

# ==============================
# 3. 工具函数：Prompt 构建与 LLM 初始化
# ==============================

def build_optimization_prompt(text: str, requirements: List[str]) -> str:
    """
    根据前端传来的中文需求列表构建 Prompt
    """
    if not requirements:
        req_str = "无特殊要求，请优化语言，使其更加通顺、专业。"
    else:
        # 将列表转换为带序号的字符串
        req_str = "\n".join([f"{i+1}. {req}" for i, req in enumerate(requirements)])

    # 构建最终提示词
    prompt = (
        f"请根据以下【润色要求】对【原始内容】进行重写。\n\n"
        f"【润色要求】\n{req_str}\n\n"
        f"【原始内容】\n{text}\n\n"
        f"【输出要求】\n"
        f"1. 直接输出润色后的正文，不要包含“好的”、“以下是修改后的内容”等寒暄语。\n"
        f"2. 保持原意不变，但提升表达质量。"
    )
    return prompt

def init_llm_instance(model_id: int):
    """根据 model_id 初始化 LangChain LLM 实例"""
    config_data = get_llm_config_by_id(model_id)
    if not config_data:
        # 兜底方案：如果找不到配置，默认使用本地 Ollama
        logger.warning(f"⚠️ 未找到 model_id={model_id} 的配置，使用默认本地模型")
        return ChatOllama(
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            temperature=0.3,
        )

    llm_type = config_data["llm_type"]
    model_name = config_data["model_name"]
    api_key = config_data["api_key"]
    base_url = config_data["base_url"]

    logger.info(f"🚀 初始化模型: [{llm_type}] - {model_name}")
    
    if llm_type == "local":
        return ChatOllama(
            model=model_name,
            base_url=base_url if base_url else "http://localhost:11434",
            temperature=0.3,
            timeout=60, # 增加超时设置
        )
    elif llm_type == "custom":
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.3,
            streaming=True,
            timeout=60, # 增加超时设置
        )
    else:
        # 兼容其他 OpenAI 格式
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.3,
            streaming=True,
            timeout=60, # 增加超时设置
        )

# ==============================
# 4. 核心流式生成逻辑
# ==============================

def optimize_text_stream(text: str, requirements: List[str], model_id: int, task_id: str, user_id: int = None):
    """
    流式润色生成器
    :param text: 原文
    :param requirements: 前端需求列表
    :param model_id: 模型ID
    :param task_id: 会话ID，用于隔离上下文
    :param user_id: 用户ID，用于权限校验
    """
    global session_manager

    # 1. 获取或初始化历史记录
    current_history = session_manager.get_session(task_id)
    if not current_history:
        current_history = []
    
    # 2. 构建 System Prompt (如果是新会话)
    #    如果是多轮对话，我们只追加用户的后续指令，不再重复发 System Prompt
    messages = []
    
    if len(current_history) == 0:
        system_content = "你是一个专业的文档润色专家，擅长逻辑重组、术语校对和商务写作。请严格遵循用户的指令进行修改。"
        messages.append(SystemMessage(content=system_content))
    
    # 3. 载入历史记录
    messages.extend(current_history)

    # 4. 构建本次请求的 Prompt
    #    如果是第一轮，我们需要把原文和要求组合起来
    #    如果是后续轮次（比如用户说“再改短一点”），我们直接把这个指令发给 AI
    if len(current_history) == 0:
        user_prompt_content = build_optimization_prompt(text, requirements)
    else:
        # 假设这里 text 是用户的后续指令，或者我们需要重新组合
        # 简单起见，我们假设每次调用都是一次新的润色请求，或者是对上一次的补充
        # 这里演示作为一次新的强指令
        user_prompt_content = build_optimization_prompt(text, requirements)

    messages.append(HumanMessage(content=user_prompt_content))

    # 5. 执行流式生成
    try:
        llm = init_llm_instance(model_id)
        
        full_response_content = ""
        
        print(f"⏳ (Task: {task_id}) 正在生成...")

        # LangChain 的 stream 方法
        for chunk in llm.stream(messages):
            text_chunk = chunk.content
            if text_chunk:
                full_response_content += text_chunk
                # 构造 SSE 格式数据
                yield f"data: {json.dumps({'content': text_chunk}, ensure_ascii=False)}\n\n"
        
        # 发送结束标记
        yield "data: [DONE]\n\n"

        # 6. 更新历史记录 (存入 Redis/Memory，支持多轮)
        current_history.append(HumanMessage(content=user_prompt_content))
        current_history.append(AIMessage(content=full_response_content))
        session_manager.update_session(task_id, current_history)
        logger.info(f"Task {task_id} 历史记录已更新，当前轮数: {len(current_history)//2}")

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

# ==============================
# 5. 主函数测试 (模拟前端交互)
# ==============================
async def main():
    print(f"🚀 启动 LangChain 流式润色测试")
    
    # 模拟数据
    test_task_id = "session_12345"
    test_model_id = 2  # 假设数据库中有 ID 为 1 的模型
    input_text = """
    我们这个AI项目其实挺难搞的，主要是数据不太行，脏数据太多了。
    然后那个算法也就是用了个开源的，效果一般般吧。
    另外服务器经常崩，并发一高就挂。
    反正现在就是先把功能跑通，后面的以后再说。
    """
    frontend_requirements = [
        "优化逻辑结构",
        "专业术语优化",
        "总-分-总 表述"
    ]

    print("-" * 50)
    print("📝 原文内容:")
    print(input_text.strip())
    print("-" * 50)
    print("⏳ 开始流式接收...")

    # 调用流式生成器
    # 注意：这里不是 async 调用，因为 generator 是同步的迭代器，
    # 如果是在 FastAPI 中使用 StreamingResponse，它会在线程池中运行。
    generator = optimize_text_stream(input_text, frontend_requirements, test_model_id, test_task_id)
    
    full_content = ""
    
    for event in generator:
        # 模拟前端处理 SSE
        if "[DONE]" in event:
            print("\n\n✅ 流式传输结束")
            break
        
        try:
            # 去掉 "data: " 前缀
            if event.startswith("data: "):
                json_str = event[6:].strip()
                data = json.loads(json_str)
                
                if "content" in data:
                    chunk = data["content"]
                    print(chunk, end="", flush=True) # 实时打印效果
                    full_content += chunk
                
                if "error" in data:
                    print(f"\n❌ Error: {data['error']}")
        except Exception as e:
            print(f"解析错误: {e}")

    # (可选) 简单的后处理展示，如果需要去除非文本内容
    # Qwen 通常不需要像 DeepSeek R1 那样去除 <think> 标签
    print("-" * 50)
    print(f"📊 最终统计: 长度 {len(full_content)} 字")

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试已中断")