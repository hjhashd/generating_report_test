import os
import sys
import json
import re
import logging
import time
from datetime import datetime
from typing import List

# 数据库与加密相关
import pymysql
import pdfplumber
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from docx import Document
from cryptography.fernet import Fernet

# LangChain 相关库
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, messages_to_dict, messages_from_dict
from utils.redis_client import get_redis_client
from utils.chat_session_manager import ChatSessionManager

# ==========================================
# 0. 基础配置 & 密钥管理
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 添加 generate_report_test 到 sys.path 以导入 server_config
generate_report_root = os.path.dirname(project_root)
if generate_report_root not in sys.path:
    sys.path.append(generate_report_root)
import server_config

from zzp import sql_config as config

BASE_DIR = server_config.INFERRENCE_DIR
ENCRYPTION_KEY = b'8P_Gk9wz9qKj-4t8z9qKj-4t8z9qKj-4t8z9qKj-4t8=' 
cipher_suite = Fernet(ENCRYPTION_KEY)
logger = logging.getLogger(__name__)

# ==========================================
# 1. 全局会话管理 (Redis + Memory)
# ==========================================
# Initialize Manager (using default 'chat_session' type to match verified state)
session_manager = ChatSessionManager(session_type="chat_session")

# ==========================================
# 2. 数据库与工具函数
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
        # Fallback: if it looks like a raw key (starts with "sk-"), return it directly
        if encrypted_str.startswith("sk-"):
            return encrypted_str
        return ""

def get_llm_config_by_id(model_id, user_id=None):
    engine = get_db_connection()
    # 增加 user_id 校验：只能查到 公用模型(user_id IS NULL) 或 自己的模型
    sql_str = "SELECT llm_type, model_name, api_key, base_url FROM llm_config WHERE id = :id"
    if user_id is not None:
        sql_str += " AND (user_id IS NULL OR user_id = :user_id)"
    
    sql = text(sql_str)
    try:
        with engine.connect() as conn:
            params = {"id": model_id}
            if user_id is not None:
                params["user_id"] = user_id
                
            result = conn.execute(sql, params).fetchone()
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

def get_default_llm_config():
    """获取默认的 LLM 配置 (用于未指定 ID 时)"""
    engine = get_db_connection()
    # 优先获取最新的配置 (假设 ID 越大越新)
    sql = text("SELECT llm_type, model_name, api_key, base_url FROM llm_config ORDER BY id DESC LIMIT 1")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql).fetchone()
            if result:
                llm_type, model_name, encrypted_key, base_url = result
                api_key = decrypt_text(encrypted_key) if encrypted_key else ""
                return {
                    "llm_type": llm_type, "model_name": model_name,
                    "api_key": api_key, "base_url": base_url
                }
    except Exception as e:
        logger.error(f"读取默认配置失败: {e}")
    return None

def get_files_by_material_names(material_name_list, user_id=None):
    if not material_name_list: return {}
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            # 增加 user_id 校验：只能查到自己的文件 (假设 file_item 关联的 file_structure 有 user_id，或者 file_item 本身有 user_id)
            # 根据之前的 queryAll.py，file_item 通过 folder_id 关联 file_structure，file_structure 有 user_id
            # 这里简化处理，先只查 file_item，假设后续会完善文件隔离。
            # 为了严谨，我们应该 JOIN file_structure 并校验 user_id
            sql_str = """
                SELECT f.file_name, f.file_path 
                FROM file_item f
                JOIN file_structure s ON f.folder_id = s.id
                WHERE f.file_name IN :names
            """
            if user_id is not None:
                sql_str += " AND s.user_id = :user_id"
            
            sql = text(sql_str)
            params = {"names": tuple(material_name_list)}
            if user_id is not None:
                params["user_id"] = user_id

            result = conn.execute(sql, params).fetchall()
            return {row[0]: row[1] for row in result}
    except Exception as e:
        logger.error(f"文件查询失败: {e}")
        return {}

def read_file_content(file_path):
    full_path = os.path.join(BASE_DIR, file_path.lstrip('/'))
    if not os.path.exists(full_path): return ""
    try:
        if full_path.endswith('.docx'):
            doc = Document(full_path)
            return "\n".join([para.text for para in doc.paragraphs]).strip()
        elif full_path.endswith('.pdf'):
            with pdfplumber.open(full_path) as pdf:
                return "\n".join([page.extract_text() or "" for page in pdf.pages]).strip()
        else:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except Exception:
        return ""

# def init_llm_instance(config_data):
#     if not config_data: raise ValueError("配置数据为空")
#     llm_type = config_data['llm_type']
#     model_name = config_data['model_name']
#     base_url = config_data['base_url']
#     api_key = config_data['api_key']

#     if llm_type == "local":
#         return ChatOllama(model=model_name, base_url=base_url, temperature=0.2, num_ctx=8192)
#     elif llm_type in ["online", "custom"]:
#         return ChatOpenAI(api_key=api_key, base_url=base_url, model=model_name, temperature=0.2, streaming=True)
#     else:
#         raise ValueError(f"不支持的模型类型: {llm_type}")

def init_llm_instance(config_data):
    if not config_data: raise ValueError("配置数据为空")

    llm_type = config_data['llm_type']
    model_name = config_data['model_name']
    base_url = config_data['base_url']
    api_key = config_data['api_key']

    # ================= 调试代码开始 =================
    print(f"\n🔍 [调试信息] 模型类型: {llm_type}")
    print(f"🔍 [调试信息] 模型名称: {model_name}")
    print(f"🔍 [调试信息] Base URL: '{base_url}'") # 注意看有没有空格，或者是否缺了 /v1
    
    if api_key:
        # 只打印前5位和后5位，防止泄露，确认解密是否成功
        masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
        print(f"🔍 [调试信息] API Key (解密后): {masked_key}")
        print(f"🔍 [调试信息] API Key 长度: {len(api_key)}")
    else:
        print(f"🔍 [调试信息] API Key 为空!")
    # ================= 调试代码结束 =================

    print(f"🚀 初始化模型: [{llm_type}] {model_name}")
    
    if llm_type == "local":
        return ChatOllama(model=model_name, base_url=base_url, temperature=0.2, num_ctx=8192, timeout=60)
    elif llm_type in ["online", "custom"]:
        return ChatOpenAI(
            api_key=api_key, 
            base_url=base_url, 
            model=model_name, 
            temperature=0.2, 
            streaming=True,
            timeout=60
        )
    else:
        raise ValueError(f"不支持的模型类型: {llm_type}")

# ==========================================
# 3. 核心导出函数 (Chat_generator_stream)
# ==========================================
def Chat_generator_stream(folder_name, material_name_list, instruction, model_id, task_id, user_id=None):
    """
    流式生成器核心逻辑
    参数 task_id: 用于区分不同用户的历史记录
    参数 user_id: 用于数据权限隔离
    """
    # global CHAT_SESSIONS (Removed)

    # 1. 验证配置
    llm_config = get_llm_config_by_id(model_id, user_id=user_id)
    if not llm_config:
        yield f"data: {json.dumps({'error': 'Model config not found'})}\n\n"
        return

    # 2. 初始化或获取历史记录
    current_history = session_manager.get_session(task_id)
    if not current_history:
        current_history = []

    # 3. 准备材料上下文
    full_materials_text = ""
    has_materials = False
    if material_name_list and len(material_name_list) > 0:
        file_map = get_files_by_material_names(material_name_list, user_id=user_id)
        if file_map:
            content_parts = []
            for name, path in file_map.items():
                text_content = read_file_content(path)
                if text_content:
                    content_parts.append(f"【参考材料：{name}】\n{text_content}\n")
            full_materials_text = "\n".join(content_parts)
            if full_materials_text:
                has_materials = True

    # 4. 构建 System Prompt
    current_date = datetime.now().strftime('%Y-%m-%d')
    if has_materials:
        system_content = f"""
今天日期：{current_date}
你是一个政务材料撰写辅助AI。

【参考材料】
{full_materials_text}

【任务指令】
请基于上述材料，完成以下任务：
1. 严格基于材料内容，不编造。
2. 语言正式、严谨。
3. 如果用户要求生成表格、列表等特定格式，请务必满足。
4. 输出内容使用 Markdown 格式渲染（支持表格、粗体等）。
5. 直接输出正文内容，不需要JSON格式。
"""
    else:
        system_content = f"""
今天日期：{current_date}
你是一个政务材料撰写辅助AI。

【任务指令】
请根据目录名称“{folder_name}”和用户指令进行逻辑创作。
1. 语言正式、结构清晰。
2. 如果用户要求生成表格、列表等特定格式，请务必满足。
3. 输出内容使用 Markdown 格式渲染（支持表格、粗体等）。
4. 直接输出正文内容，不需要JSON格式。
"""

    # 5. 执行流式生成
    try:
        llm = init_llm_instance(llm_config)
        
        # 组装消息链：System -> History -> Current Human
        messages = [SystemMessage(content=system_content)]
        messages.extend(current_history)
        messages.append(HumanMessage(content=instruction))
        
        full_response_content = ""

        # 流式返回
        for chunk in llm.stream(messages):
            text_chunk = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if text_chunk:
                full_response_content += text_chunk
                yield f"data: {json.dumps({'content': text_chunk}, ensure_ascii=False)}\n\n"
        
        # 结束标记
        yield "data: [DONE]\n\n"

        # 6. 更新历史记录 (存入 Redis/Memory)
        current_history.append(HumanMessage(content=instruction))
        current_history.append(AIMessage(content=full_response_content))
        session_manager.update_session(task_id, current_history)
        logger.info(f"Task {task_id} 历史记录已更新")

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

# 占位函数，如果还需要同步接口可保留
def Chat_generator(*args, **kwargs):
    pass


if __name__ == "__main__":
    # --- 1. 测试配置 ---
    TEST_TASK_ID = "local_debug_session_001" 
    INPUT_MODEL_ID = 6   
    INPUT_FOLDER_NAME = "项目概述"
    INPUT_MATERIALS = [
        "李强主持召开国务院常务会议 研究进一步做好节能降碳工作等  广东省人民政府门户网站_20251231144447.pdf",
    ]
    
    print(f"\n🚀 启动本地测试 (Task ID: {TEST_TASK_ID})")
    print(f"📂 加载材料数: {len(INPUT_MATERIALS)}")

    # 定义一个测试函数，减少重复代码
    def run_chat_round(round_num, instruction):
        print(f"\n\n========= 第 {round_num} 轮对话: {instruction[:15]}... =========")
        
        start_time = time.time()  # 记录开始时间
        first_token_time = None   # 用于记录首字返回时间
        
        generator = Chat_generator_stream(
            INPUT_FOLDER_NAME, 
            INPUT_MATERIALS, 
            instruction, 
            INPUT_MODEL_ID, 
            TEST_TASK_ID 
        )
        
        full_content = ""
        for event in generator:
            if "[DONE]" in event:
                break
            
            try:
                # 记录首字到达时间（思考时间）
                if first_token_time is None:
                    first_token_time = time.time()
                    thinking_duration = first_token_time - start_time
                    print(f"💡 思考耗时: {thinking_duration:.2f}s (首字已返回)\n" + "-"*30)

                json_str = event.replace("data: ", "").strip()
                data = json.loads(json_str)
                
                if "content" in data:
                    chunk = data["content"]
                    print(chunk, end="", flush=True) 
                    full_content += chunk
                
                if "error" in data:
                    print(f"\n❌ Error: {data['error']}")
            except Exception:
                pass
        
        end_time = time.time() # 记录结束时间
        total_duration = end_time - start_time
        print(f"\n\n---------------------------------")
        print(f"⏱️ 本轮统计: 总耗时 {total_duration:.2f}s")

    # --- 2. 第一轮对话 ---
    INPUT_INSTRUCTION_1 = """
    请生成一段约500字的材料综述，主题为节能降碳工作推进。
    内容必须包含：背景、重点举措。
    要求：语气正式。
    """
    run_chat_round(1, INPUT_INSTRUCTION_1)

    # --- 3. 第二轮对话 (测试记忆功能) ---
    INPUT_INSTRUCTION_2 = "请根据刚才生成的内容，提炼出3个核心关键词，并解释为什么选它们。"
    run_chat_round(2, INPUT_INSTRUCTION_2)
    
    # --- 4. 验证内存状态 ---
    print("\n✅ 测试结束")
    history = session_manager.get_session(TEST_TASK_ID)
    if history:
        history_len = len(history)
        print(f"📊 当前会话状态: Task [{TEST_TASK_ID}] 包含 {history_len} 条消息记录。")