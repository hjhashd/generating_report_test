import logging
import os
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form
from utils.lyf.change_doc_to_md import convert_docx_dir_to_md

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/convert_docx_to_md/")
def convert_docx_to_md_endpoint(
    type: str = Form(...),               # ✅ 报告类型，如：环境评估报告
    folder_name: str = Form(...),        # ✅ 子目录，如：test3
    file: UploadFile = File(None),       # ⚠️ 保留但不强制
    overwrite: Optional[bool] = Form(True),
    reportId: Optional[int] = Form(None)
):
    logger.info(
        f"🚀 [转换启动] reportId={reportId}, type={type}, folder={folder_name}, overwrite={overwrite}"
    )

    try:
        # 🚫 你当前并不需要处理上传文件，直接转换已有目录
        convert_docx_dir_to_md(type, folder_name)

        logger.info("✅ Word → Markdown 转换完成")
        return {
            "status": "success",
            "message": "转换成功",
            "type": type,
            "folder_name": folder_name
        }

    except Exception as e:
        logger.error(f"❌ 转换失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/health")
def health_check():
    return {"status": "healthy"}
