import os
import sys

# 将当前目录添加到 Python 路径，确保能找到 routers 等模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 1. 引入 StaticFiles
from routers import (
    query_modul_api,
    import_modul_api,
    create_catalogue_api,
    query_catalogue_type_api,
    import_catalogueShopping_api,
    query_report_api,
    browse_report_api,
    inferrence_choose_api,
    import_doc_to_db_api,
    ai_generate_api,
    ai_search_api,
    insert_llm_config_api,
    query_prompts_api,
    delete_llm_config_api,
    delete_report_api,
    overwrite_doc_api,
    report_merge_api,
    change_doc_to_md_api,
    editor_api,
    auth_utils_api,
)

import server_config
from routers import lyf_router
from utils.log_config import setup_logging

# 0. 初始化日志系统 (最优先执行)
setup_logging()

app = FastAPI()

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法，包括 OPTIONS
    allow_headers=["*"],  # 允许所有请求头
)

# 1. 从配置获取路径
BASE_DIR = server_config.REPORT_DIR
# 新增：定义预览文件存放的物理路径
INFERRENCE_DIR = server_config.INFERRENCE_DIR
# 编辑器图片存放路径
EDITOR_IMAGE_DIR = server_config.EDITOR_IMAGE_DIR

#最终合并后的路径
MERGE_DIR = server_config.MERGE_DIR

# 2. 确保目录存在
server_config.ensure_directories()

# 3. 挂载目录
# 挂载报告展示目录
app.mount("/report_files", StaticFiles(directory=BASE_DIR), name="report_files")
# 【关键修复】：挂载预览文件目录，匹配前端生成的 /files 路径
app.mount("/files", StaticFiles(directory=INFERRENCE_DIR), name="files")
app.mount("/merge_files", StaticFiles(directory=MERGE_DIR), name="merge_files")
app.mount("/editor_images", StaticFiles(directory=EDITOR_IMAGE_DIR), name="editor_images")



# 注册路由
app.include_router(query_modul_api.router)
app.include_router(import_modul_api.router)
app.include_router(create_catalogue_api.router)
app.include_router(query_catalogue_type_api.router)
app.include_router(import_catalogueShopping_api.router)
app.include_router(query_report_api.router)
app.include_router(browse_report_api.router)
app.include_router(inferrence_choose_api.router)
app.include_router(import_doc_to_db_api.router)
app.include_router(ai_generate_api.router)
app.include_router(ai_search_api.router)
app.include_router(insert_llm_config_api.router)
app.include_router(query_prompts_api.router)
app.include_router(delete_llm_config_api.router)
app.include_router(delete_report_api.router)
app.include_router(overwrite_doc_api.router)
app.include_router(report_merge_api.router)
app.include_router(change_doc_to_md_api.router)
app.include_router(editor_api.router)
app.include_router(auth_utils_api.router)
app.include_router(lyf_router.router, prefix="/api/ai")

if __name__ == "__main__":
    import uvicorn
    # 你的端口是 34521
    uvicorn.run(app, host="0.0.0.0", port=server_config.PORT)