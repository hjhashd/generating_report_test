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

# ==============================
# 0. 基础配置 & 密钥管理
# ==============================
# 确保可以引入同级或上级模块
# 1. 将 utils 目录加入 sys.path (为了 from zzp import ...)
utils_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if utils_path not in sys.path:
    sys.path.append(utils_path)

# 2. 将项目根目录 (generate_report_test) 加入 sys.path (为了 from utils.xxx import ...)
project_root = os.path.dirname(utils_path)
if project_root not in sys.path:
    sys.path.append(project_root)

from zzp import sql_config as config
# [表情] 新增：引入旧版数据库连接工具
from utils.lyf.db_session import get_engine
from utils.chat_session_manager import ChatSessionManager

ENCRYPTION_KEY = b'8P_Gk9wz9qKj-4t8z9qKj-4t8z9qKj-4t8z9qKj-4t8=' 
cipher_suite = Fernet(ENCRYPTION_KEY)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LangChainOptimizer")

# ==============================
# 1. 数据库工具函数
# ==============================

# --- 原有的主业务库连接 (用于获取 LLM 配置) ---
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# --- [表情] 新增：提示词库连接 (用于获取 Prompt Content) ---
def get_agent_db_connection():
    """获取旧版提示词库的连接 (agent_db)"""
    return get_engine("agent_db")

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

# --- [表情] 新增：获取提示词列表 (仅返回 id 和 title) ---
def get_prompt_list_by_folder(folder_id: int, user_id: int) -> List[Dict[str, Any]]:
    """
    供前端调用：根据文件夹 ID 和用户 ID，返回该文件夹下的提示词列表。
    用于前端下拉框展示。
    """
    engine = get_agent_db_connection()
    
    # SQL 逻辑：只查 id 和 title
    sql = text("""
        SELECT id, title 
        FROM user_prompts 
        WHERE folder_id = :fid AND user_id = :uid
        ORDER BY created_at DESC
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"fid": folder_id, "uid": user_id}).mappings().all()
            
            # 格式化为前端易读的字典列表
            prompts = [{"id": row["id"], "title": row["title"]} for row in result]
            logger.info(f"成功查询到 {len(prompts)} 条提示词 (folder_id={folder_id})")
            return prompts
    except Exception as e:
        logger.error(f"[表情] 查询提示词列表失败: {e}")
        return []

# --- [表情] 新增：根据 ID 列表从 agent_db 获取提示词内容 ---
def get_prompt_contents_by_ids(prompt_ids: List[int], user_id: int) -> List[str]:
    """
    根据前端传来的 Prompt ID 列表，从 user_prompts 表中获取 content。
    同时校验 user_id 确保权限安全。
    """
    if not prompt_ids:
        return []
    
    engine = get_agent_db_connection()
    
    # 使用 IN 语句查询多个 ID 的内容，并校验 user_id
    sql = text("""
        SELECT content FROM user_prompts 
        WHERE id IN :ids AND user_id = :uid
    """)
    
    try:
        with engine.connect() as conn:
            # SQLAlchemy 的 IN 查询需要传入 tuple
            # 如果只有一个 ID，tuple 转换也没问题
            result = conn.execute(sql, {"ids": tuple(prompt_ids), "uid": user_id}).fetchall()
            # 提取结果列表中的 content 字段，过滤空值
            contents = [row[0] for row in result if row[0]]
            
            if not contents:
                logger.warning(f"[表情] 未找到用户 {user_id} 请求的 Prompt IDs: {prompt_ids}")
            
            return contents
    except Exception as e:
        logger.error(f"[表情] 查询 Prompt 内容失败: {e}")
        return []

# ==============================
# 2. 会话管理 (Redis + Memory)
# ==============================
# Initialize Manager with 'chat:optimize' session type
session_manager = ChatSessionManager(session_type="chat:optimize") 

# ==============================
# 3. 工具函数：Prompt 构建与 LLM 初始化
# ==============================

def build_optimization_prompt(text: str, requirement_contents: List[str]) -> str:
    """
    根据查出来的专业 Prompt 内容构建最终提示词
    """
    if not requirement_contents:
        req_str = "无特殊要求，请优化语言，使其更加通顺、专业。"
    else:
        # 将列表转换为带序号的字符串
        req_str = "\n".join([f"{i+1}. {req}" for i, req in enumerate(requirement_contents)])

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
        logger.warning(f"[表情] 未找到 model_id={model_id} 的配置，使用默认本地模型")
        return ChatOllama(
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            temperature=0.9,
        )

    llm_type = config_data["llm_type"]
    model_name = config_data["model_name"]
    api_key = config_data["api_key"]
    base_url = config_data["base_url"]

    logger.info(f"[表情] 初始化模型: [{llm_type}] - {model_name}")
    
    if llm_type == "local":
        return ChatOllama(
            model=model_name,
            base_url=base_url if base_url else "http://localhost:11434",
            temperature=0.9,
            timeout=60, # 增加超时设置
        )
    elif llm_type == "custom":
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.9,
            streaming=True,
            timeout=60, # 增加超时设置
        )
    else:
        # 兼容其他 OpenAI 格式
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.9,
            streaming=True,
            timeout=60, # 增加超时设置
        )

# ==============================
# 4. 核心流式生成逻辑
# ==============================

def optimize_text_stream(text: str, prompt_ids: List[int], model_id: int, task_id: str, user_id: int):
    """
    流式润色生成器
    :param text: 原文
    :param prompt_ids: 前端传来的 Prompt ID 列表 [402, 405]
    :param model_id: 模型ID
    :param task_id: 会话ID，用于隔离上下文
    :param user_id: 用户ID，用于权限校验
    """
    global session_manager

    # 1. [表情] 新增步骤：根据 ID 列表去 agent_db 查出真正的 content
    requirements = get_prompt_contents_by_ids(prompt_ids, user_id)
    
    if prompt_ids and not requirements:
        logger.warning(f"Task {task_id}: 用户 {user_id} 传了 ID {prompt_ids} 但未查到任何内容")

    # 2. 获取或初始化历史记录
    current_history = session_manager.get_session(task_id)
    if not current_history:
        current_history = []
    
    # 3. 构建 System Prompt (如果是新会话)
    messages = []
    if len(current_history) == 0:
        system_content = "你是一个专业的文档润色专家，擅长逻辑重组、术语校对和商务写作。请严格遵循用户的指令进行修改。"
        messages.append(SystemMessage(content=system_content))
    
    # 4. 载入历史记录
    messages.extend(current_history)

    # 5. 构建本次请求的 Prompt
    #    这里传入的是查出来的 requirements (str列表)
    user_prompt_content = build_optimization_prompt(text, requirements)
    messages.append(HumanMessage(content=user_prompt_content))

    # 6. 执行流式生成
    try:
        llm = init_llm_instance(model_id)
        
        full_response_content = ""
        
        print(f"[表情] (Task: {task_id}) 正在生成... 使用了 {len(requirements)} 条自定义Prompt")

        # LangChain 的 stream 方法
        for chunk in llm.stream(messages):
            text_chunk = chunk.content
            if text_chunk:
                full_response_content += text_chunk
                # 构造 SSE 格式数据
                yield f"data: {json.dumps({'content': text_chunk}, ensure_ascii=False)}\n\n"
        
        # 发送结束标记
        yield "data: [DONE]\n\n"

        # 7. 更新历史记录 (存入 Redis/Memory，支持多轮)
        current_history.append(HumanMessage(content=user_prompt_content))
        current_history.append(AIMessage(content=full_response_content))
        session_manager.update_session(task_id, current_history)
        logger.info(f"Task {task_id} 历史记录已更新，当前轮数: {len(current_history)//2}")

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

# ==============================
# 5. 主函数测试（模拟真实前端行为）
# ==============================

async def main():
    """
    用于本地 / 服务器联调测试：
    - 模拟前端只传 Prompt IDs
    - 验证 Prompt 是否正确拼接
    - 验证流式返回是否完整
    """
    print("\n[表情] 启动 LangChain Prompt-ID → 流式润色 完整测试\n")

    # ==========================
    # 1. 模拟前端上下文参数
    # ==========================
    test_task_id = "session_test_001"
    test_user_id = 7
    test_model_id = 2

    input_text = (
        "我们这个AI项目其实挺难搞的，主要是数据不太行，脏数据太多了。\n"
        "然后那个算法也就是用了个开源的，效果一般般吧。"
    )

    # [表情] 前端真实只会传 ID
    test_prompt_ids = [591,592]

    # ==========================
    # 2. 打印测试基本信息
    # ==========================
    print("=" * 60)
    print("【测试信息】")
    print(f"User ID      : {test_user_id}")
    print(f"Task ID      : {test_task_id}")
    print(f"Model ID     : {test_model_id}")
    print(f"Prompt IDs  : {test_prompt_ids}")
    print("-" * 60)
    print("【原始文本】")
    print(input_text)
    print("=" * 60)
    print("【开始流式生成】\n")

    # ==========================
    # 3. 调用核心流式生成器
    # ==========================
    generator = optimize_text_stream(
        text=input_text,
        prompt_ids=test_prompt_ids,
        model_id=test_model_id,
        task_id=test_task_id,
        user_id=test_user_id
    )

    # ==========================
    # 4. 模拟前端 SSE 消费
    # ==========================
    final_output = []
    chunk_count = 0

    for event in generator:
        # 结束信号
        if event.strip() == "data: [DONE]":
            print("\n\n[表情] 流式生成结束")
            break

        if not event.startswith("data:"):
            continue

        try:
            payload = event.replace("data:", "").strip()
            data = json.loads(payload)

            # 正常内容
            if "content" in data:
                chunk = data["content"]
                print(chunk, end="", flush=True)
                final_output.append(chunk)
                chunk_count += 1

            # 错误信息
            elif "error" in data:
                print(f"\n[表情] 模型返回错误: {data['error']}")
                break

        except Exception as e:
            print(f"\n[表情] 流式数据解析失败: {e}")
            print(f"原始数据: {event}")

    # ==========================
    # 5. 输出统计信息
    # ==========================
    full_text = "".join(final_output)

    print("\n" + "=" * 60)
    print("【生成结果统计】")
    print(f"流式分片数 : {chunk_count}")
    print(f"最终字数   : {len(full_text)}")
    print("=" * 60)

    # 方便你后续断点 / 比对
    return full_text


# ==============================
# CLI 入口
# ==============================
if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[表情] 测试被手动中断")
