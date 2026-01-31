import logging
import os
import tempfile
import httpx
from urllib.parse import unquote
from fastapi import APIRouter, UploadFile, File, Form, Request
from typing import Optional

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_config

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 定义允许操作的基准路径列表
ALLOWED_DIRS = [
    server_config.REPORT_DIR,
    server_config.MERGE_DIR
]

async def save_file_atomically(abs_path: str, content_source, is_async_gen: bool = True):
    """
    通用原子保存逻辑
    :param abs_path: 目标绝对路径
    :param content_source: 内容源，支持 async iterator 或 bytes
    :param is_async_gen: 是否为异步生成器
    """
    # 1. 中文兼容：对 abs_path 做 URL 解码与规范化
    decoded_path = unquote(abs_path)
    # 规范化路径，处理 ../ 等路径穿越字符
    normalized_path = os.path.normpath(os.path.abspath(decoded_path))

    # 2. 路径约束：校验 abs_path 必须在允许的目录下
    is_allowed = False
    for base_dir in ALLOWED_DIRS:
        abs_base_dir = os.path.normpath(os.path.abspath(base_dir))
        if normalized_path.startswith(abs_base_dir):
            is_allowed = True
            break
    
    if not is_allowed:
        logger.error(f"越权路径尝试: {normalized_path} 不在允许的目录列表中")
        return {"status_code": 1, "message": "Permission denied: path outside of allowed directories"}

    # 3. 目录保障
    parent_dir = os.path.dirname(normalized_path)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    # 4. 原子覆盖
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=parent_dir, delete=False, suffix=".tmp") as tmp_file:
            temp_file_path = tmp_file.name
            if is_async_gen:
                async for chunk in content_source:
                    tmp_file.write(chunk)
            else:
                tmp_file.write(content_source)
            
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        os.replace(temp_file_path, normalized_path)
        return {"status_code": 0, "message": "ok"}
    except Exception as e:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise e

@router.post("/overwrite_doc/")
async def overwrite_doc_endpoint(
    file: UploadFile = File(...),
    abs_path: str = Form(...),
    overwrite: Optional[bool] = Form(True),
    reportId: Optional[int] = Form(None)
):
    """
    接收二进制文件与目标绝对路径，直接覆盖落盘。
    """
    logger.info(f"接收到覆盖请求: abs_path={abs_path}, reportId={reportId}, filename={file.filename}")
    try:
        async def file_generator():
            file.file.seek(0)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

        result = await save_file_atomically(abs_path, file_generator())
        if result["status_code"] == 0:
            logger.info(f"文件成功覆盖到: {abs_path}")
        return result
    except Exception as e:
        logger.error(f"❌ 覆盖文档失败: {e}", exc_info=True)
        return {"status_code": 1, "message": f"Internal server error: {str(e)}"}

@router.post("/onlyoffice_callback/")
async def onlyoffice_callback(
    request: Request,
    abs_path: str,
    reportId: Optional[int] = None
):
    """
    OnlyOffice 回调处理接口
    """
    try:
        data = await request.json()
        status = data.get("status")
        logger.info(f"OnlyOffice 回调: status={status}, abs_path={abs_path}, reportId={reportId}")

        # status 2: 准备保存, status 6: 强制保存完成
        if status in [2, 6]:
            download_url = data.get("url")
            if not download_url:
                logger.error("OnlyOffice 回调数据中缺少 url")
                return {"error": 0} # 即使出错也返回 error 0 以满足 OnlyOffice 要求

            # 修正 URL：将 localhost 或 127.0.0.1 替换为可配置的内网地址
            # 建议实际生产中使用环境变量
            internal_host = os.getenv("ONLYOFFICE_INTERNAL_HOST", "192.168.3.10")
            download_url = download_url.replace("localhost", internal_host).replace("127.0.0.1", internal_host)
            
            logger.info(f"正在从 OnlyOffice 下载文件: {download_url}")
            
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", download_url) as resp:
                    if resp.status_code == 200:
                        # 使用流式写入
                        result = await save_file_atomically(abs_path, resp.aiter_bytes())
                        if result["status_code"] == 0:
                            logger.info(f"OnlyOffice 回调保存成功: {abs_path}")
                        else:
                            logger.error(f"OnlyOffice 回调保存失败: {result['message']}")
                    else:
                        logger.error(f"下载 OnlyOffice 文件失败: HTTP {resp.status_code}")
        
        return {"error": 0}
    except Exception as e:
        logger.error(f"❌ OnlyOffice 回调处理失败: {e}", exc_info=True)
        return {"error": 0} # OnlyOffice 要求始终返回 error: 0
