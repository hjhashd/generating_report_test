import os
import sys
import time
import json
from datetime import datetime
import requests
import pymysql
import pdfplumber  # ✅ 新增：引入 pdf 库
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from docx import Document
from langchain_ollama import ChatOllama
# from langchain_community import ConversationTokenBufferMemory  # Not available in this version
from langchain_core.callbacks import StreamingStdOutCallbackHandler
from langchain_core.messages import SystemMessage, HumanMessage

# ==========================================
# 0. 基础配置
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

import server_config

# 正确导入配置文件
try:
    # 尝试直接导入，用于模块导入场景
    from . import sql_config as config
    from .. import db_session as db_session
except ImportError:
    # 如果直接运行脚本，使用绝对导入
    try:
        from generate_report.utils.lyf import sql_config as config
        from generate_report.utils import db_session as db_session
    except ImportError:
        # 如果仍失败，使用相对路径导入
        import generate_report.utils.lyf.sql_config as config
        import generate_report.utils.db_session as db_session

# Ollama 配置
# OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b"
BASE_DIR = server_config.INFERRENCE_DIR

# 重试配置
MAX_RETRIES = 3
REQUEST_TIMEOUT = 300
RETRY_DELAY = 10

# ==========================================
# 1. 数据库连接
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)
# ==========================================
# 2. 核心功能函数
# ==========================================

def get_files_by_material_names(material_name_list):
    """根据材料名称列表查文件路径"""
    if not material_name_list:
        return {}
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            sql = text("SELECT file_name, file_path FROM file_item WHERE file_name IN :names")
            result = conn.execute(sql, {"names": tuple(material_name_list)}).fetchall()
            return {row[0]: row[1] for row in result}
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return {}

def read_file_content(file_path):
    """
    读取文件内容 (支持 .docx, .pdf, .txt)
    """
    full_path = os.path.join(BASE_DIR, file_path.lstrip('/'))
    
    if not os.path.exists(full_path):
        print(f"⚠️ 文件路径不存在: {full_path}")
        return ""

    try:
        content = ""
        file_ext = full_path.lower()

        # ✅ 情况1：处理 Word 文档
        if file_ext.endswith('.docx'):
            doc = Document(full_path)
            content = "\n".join([para.text for para in doc.paragraphs])
        
        # ✅ 情况2：处理 PDF 文档 (新增)
        elif file_ext.endswith('.pdf'):
            try:
                with pdfplumber.open(full_path) as pdf:
                    pages_content = []
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            pages_content.append(text)
                    content = "\n".join(pages_content)
            except Exception as pdf_err:
                print(f"⚠️ PDF解析出错: {pdf_err}")
                return ""

        # ✅ 情况3：默认为文本文件
        else:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

        return content.strip()
        
    except Exception as e:
        print(f"❌ 读取文件失败 {file_path}: {e}")
        return ""

# =============================
# 简易上下文记忆（模块级）
# =============================
CHAT_HISTORY = []
MAX_HISTORY_CHARS = 6000        # 上下文裁剪
STREAM_TIMEOUT = 10             # 秒：软超时 watchdog


def _trim_history(history):
    """按字符长度裁剪历史上下文（近似 token）"""
    total = 0
    trimmed = []
    for msg in reversed(history):
        total += len(msg.content)
        if total > MAX_HISTORY_CHARS:
            break
        trimmed.insert(0, msg)
    return trimmed


def Chat_generator(folder_name, material_name_list, instruction):
    global CHAT_HISTORY  # 使用全局历史记录来维护上下文
    print(f"--- 任务启动 ---")
    print(f"目录定义: {folder_name}")
    print(f"关联材料: {len(material_name_list)}个")

    # 1. 查库找文件
    file_map = get_files_by_material_names(material_name_list)
    if not file_map:
        print("❌ 未找到任何文件记录。")
        return {"content": "", "confidence": "unknown", "error": "未找到文件"}

    # 2. 读取文件内容
    content_parts = []
    for name, path in file_map.items():
        text_content = read_file_content(path)
        if text_content:
            content_parts.append(f"【参考材料：{name}】\n{text_content}\n")
            print(f"✅ 已加载: {name} (字数: {len(text_content)})")
        else:
            print(f"⚠️ 内容为空: {name}")

    full_materials_text = "\n".join(content_parts)
    if not full_materials_text:
        print("有效内容为空，无法生成。")
        return {"content": "", "confidence": "unknown", "error": "材料内容为空"}

    # 3. 构建系统消息
    system_message = SystemMessage(content=f"""
今天日期：{datetime.now().strftime('%Y-%m-%d')}

你是一个政务材料撰写辅助AI。

【写作要求】
1. 语言正式、严谨、克制
2. 符合政府公文写作风格
3. 不编造、不夸张
4. 内容仅基于给定材料

【材料信息】
目录名称：{folder_name}

材料内容：
{full_materials_text}

【输出要求】
- 只能输出 JSON
- 禁止输出解释性文字
- JSON 格式如下：
{{
  "content": "正文内容",
  "confidence": "high"
}}

请只输出 JSON，不要额外文字。
""")

    user_message = HumanMessage(content=instruction)
    
    # 添加之前裁剪过的聊天历史到当前消息
    trimmed_history = _trim_history(CHAT_HISTORY)
    messages = [system_message] + trimmed_history + [user_message]

    # 4. 初始化 LLM
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.2,
        top_p=0.2,
        repeat_penalty=1.2,
        num_ctx=8192,
        stop=["\n\n", "###"]
    )

    # 5. 流式接收
    acc = ""
    start_time = time.time()
    timeout_s = 150  # 超时秒数
    try:
        for chunk in llm.stream(messages):
            text = getattr(chunk, "content", None) or getattr(chunk, "text", None) or (chunk if isinstance(chunk, str) else "")
            if text:
                acc += text
                print(acc[:200], end="\r", flush=True)  # 实时打印前200字符
                start_time = time.time()  # 收到增量重置计时
            elif (time.time() - start_time) > timeout_s:
                print("\n⚠️ 生成超时，停止流式")
                break
    except Exception as e:
        print(f"⚠️ 生成异常: {e}")

    print("\n==================== 模型生成结果 ====================")

    # 6. JSON 解析
    try:
        data = json.loads(acc)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", acc, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                data = {"content": acc, "confidence": "unknown", "error": "JSON解析失败"}
        else:
            data = {"content": acc, "confidence": "unknown", "error": "非标准JSON"}

    print(data)
    print("==================================================")
    
    # 更新聊天历史，包含当前对话
    CHAT_HISTORY.append(user_message)
    CHAT_HISTORY.append(HumanMessage(content=f"{data.get('content', acc)}"))
    
    return data


# ==========================================
# 3. 运行入口
# ==========================================

if __name__ == "__main__":
    # 1. 目录名称
    TARGET_FOLDER_NAME = "项目概述" 
    
    # 2. 材料名称列表 (注意：这里用你报错日志里的真实文件名)
    TARGET_MATERIALS = [
        "李强主持召开国务院常务会议 研究进一步做好节能降碳工作等  广东省人民政府门户网站_20251231144447.pdf"
    ]
    
    # 3. 指令
    TARGET_INSTRUCTION = """
    请生成一段大于900字的材料综述，主题为节能降碳工作推进。
    内容必须包含：背景、重点举措、预期成效。
    要求：语气正式、结构清晰、逻辑严密。
    """

    Chat_generator(TARGET_FOLDER_NAME, TARGET_MATERIALS, TARGET_INSTRUCTION)