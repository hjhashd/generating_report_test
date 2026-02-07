import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ===========================
# 端口配置
# ===========================
# 优先从环境变量获取端口，默认值为 34521
# Docker 内部建议固定监听此端口，通过端口映射对外暴露不同端口
PORT = int(os.getenv("PORT", 34521))

# ===========================
# AI 模型配置
# ===========================
AI_API_KEY = os.getenv("AI_API_KEY", "EMPTY")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://192.168.3.10:8005/v1")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "casperhansen/deepseek-r1-distill-qwen-32b-awq")

# ===========================
# 路径配置 (自动获取当前路径)
# ===========================
# 获取当前文件所在目录的绝对路径 (即项目根目录)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 定义各业务子目录 (相对于项目根目录)
REPORT_DIR = os.path.join(PROJECT_ROOT, "report")
INFERRENCE_DIR = os.path.join(PROJECT_ROOT, "inferrence")
MERGE_DIR = os.path.join(PROJECT_ROOT, "report_merge")
EDITOR_IMAGE_DIR = os.path.join(PROJECT_ROOT, "editor_image")

# 确保关键目录存在
def ensure_directories():
    for path in [REPORT_DIR, INFERRENCE_DIR, MERGE_DIR, EDITOR_IMAGE_DIR]:
        if not os.path.exists(path):
            os.makedirs(path)

# ===========================
# 3. 用户目录隔离工具函数 (Best Practice)
# ===========================
def get_user_path(base_dir, user_id=None):
    """
    获取带用户隔离的路径
    :param base_dir: 基础目录 (如 REPORT_DIR)
    :param user_id: 用户ID (如果为 None，则返回基础目录，用于公共资源)
    :return: 组合后的路径
    """
    if user_id is not None:
        return os.path.join(base_dir, str(user_id))
    return base_dir

def get_user_report_dir(user_id=None):
    return get_user_path(REPORT_DIR, user_id)

def get_user_merge_dir(user_id=None):
    return get_user_path(MERGE_DIR, user_id)

def get_user_inference_dir(user_id=None):
    return get_user_path(INFERRENCE_DIR, user_id)

def get_user_editor_image_dir(user_id=None):
    return get_user_path(EDITOR_IMAGE_DIR, user_id)

def ensure_user_directories(user_id):
    """确保该用户的所有专属目录都存在"""
    if user_id is None:
        return
    
    paths = [
        get_user_report_dir(user_id),
        get_user_merge_dir(user_id),
        get_user_inference_dir(user_id),
        get_user_editor_image_dir(user_id)
    ]
    
    for path in paths:
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError:
                pass # 忽略并发创建时的错误
