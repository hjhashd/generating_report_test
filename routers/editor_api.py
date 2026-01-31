import logging
import os
import shutil
import uuid
import datetime
from urllib.parse import quote
from routers.dependencies import require_user, CurrentUser
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends

from pydantic import BaseModel
from typing import Optional
from utils.zzp.html_to_docx import convert_html_to_docx
from utils.zzp.image_cleaner import clean_orphaned_images
from utils.zzp.docx_to_html import convert_docx_to_html

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_config

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 请求模型
class EditorRequest(BaseModel):
    task_id: Optional[str] = None
    status: Optional[int] = 0
    agentUserId: Optional[int] = 0
    type_name: str
    report_name: str
    file_name: str  # 具体的 Word 文件名，例如 "1.1 项目背景.docx"
    source_type: str = "report" # "report" 或 "merge"，默认为 "report"

class SaveContentRequest(BaseModel):
    task_id: Optional[str] = None
    status: Optional[int] = 0
    agentUserId: Optional[int] = 0
    type_name: str
    report_name: str
    file_name: str  # 具体的 Word 文件名
    source_type: str = "report" # "report" 或 "merge"
    html_content: str # 前端传回的 HTML 内容

def get_file_path(type_name, report_name, file_name, source_type="report", user_id=None):
    """
    根据 source_type 和 user_id 精准查找文件路径
    
    逻辑说明：
    1. 严格遵循 user_path_refactor_plan.md 的路径隔离定义。
    2. 增加对前端参数的智能纠错：当前端在 Merge 视图请求源文件时（source_type='merge' 但 file_name != report_name.docx），
       自动重定向到 Report 目录查找。
    """
    user_merge_dir = server_config.get_user_merge_dir(user_id)
    user_report_dir = server_config.get_user_report_dir(user_id)
    public_merge_dir = server_config.get_user_merge_dir(None)
    public_report_dir = server_config.get_user_report_dir(None)

    # 1. 尝试定位 Merge 资源
    # 只有当 source_type 为 merge 且 请求的文件名正是合并后的文件名时，才去 merge 目录找
    expected_merged_filename = f"{report_name}.docx"
    
    if source_type == "merge" and file_name == expected_merged_filename:
        # 查找顺序：用户私有 -> 公共兜底
        # 路径结构：.../report_merge/{uid}/{Type}/{Name}.docx (扁平结构)
        paths = [
            os.path.join(user_merge_dir, type_name, file_name),
            os.path.join(public_merge_dir, type_name, file_name)
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        # 如果没找到，默认返回用户私有路径（用于新建/保存）
        return paths[0]

    # 2. 尝试定位 Report 资源 (源文件)
    # 无论是 source_type='report'，还是 source_type='merge' 但请求的是章节文件（前端行为纠错）
    # 都应该去 report 目录找
    
    # 查找顺序：用户私有 -> 公共兜底
    # 路径结构：.../report/{uid}/{Type}/{Name}/{File} (层级结构)
    paths = [
        os.path.join(user_report_dir, type_name, report_name, file_name),
        os.path.join(public_report_dir, type_name, report_name, file_name)
    ]
    for p in paths:
        if os.path.exists(p):
            return p

    # 3. 默认返回用户私有 Report 路径
    return paths[0]

def get_image_context(type_name, report_name, source_type, user_id):
    source_key = "report_merge" if source_type in ["report_merge", "merge"] else "report"
    images_dir = os.path.join(
        server_config.EDITOR_IMAGE_DIR,
        source_key,
        str(user_id),
        type_name,
        report_name
    )
    url_prefix = f"/python-api/editor_images/{source_key}/{user_id}/{quote(type_name)}/{quote(report_name)}/"
    return images_dir, url_prefix

@router.post("/upload_editor_image/")
async def upload_editor_image(
    file: UploadFile = File(...),
    folder_name: str = Form("inferrence"),
    report_type: Optional[str] = Form(None),
    report_name: Optional[str] = Form(None),
    source_type: str = Form("report"),
    current_user: CurrentUser = Depends(require_user) # [MODIFIED] Add Auth
):
    """
    处理富文本编辑器图片上传
    """
    user_id = current_user.id
    try:
        source_key = "report_merge" if source_type in ["report_merge", "merge"] else "report"
        use_context = report_type and report_name
        if use_context:
            if any(seg in ["..", "/", "\\"] for seg in [report_type, report_name]):
                return {
                    "status_code": -1,
                    "message": "非法的报告参数"
                }
            save_dir = os.path.join(
                server_config.EDITOR_IMAGE_DIR,
                source_key,
                str(user_id),
                report_type,
                report_name
            )
            relative_dir = os.path.join(source_key, str(user_id), report_type, report_name)
        else:
            save_dir = server_config.get_user_editor_image_dir(user_id)
            relative_dir = str(user_id) if user_id else ""
        
        # 确保目录存在
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        # 生成新文件名
        ext = os.path.splitext(file.filename)[1]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        new_filename = f"{timestamp}_{unique_id}{ext}"
        
        file_path = os.path.join(save_dir, new_filename)
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # [CRITICAL] 返回相对路径包含 user_id，以便前端拼接正确的 URL
        # 前端通常拼接逻辑为: URL_PREFIX + file_name
        # URL_PREFIX 指向 editor_image 根目录
        # 所以我们需要返回 "user_id/filename"
        relative_path_for_frontend = os.path.join(relative_dir, new_filename) if relative_dir else new_filename
            
        return {
            "status_code": 0,
            "message": "上传成功",
            "data": {
                "file_name": relative_path_for_frontend
            }
        }
        
    except Exception as e:
        logger.error(f"上传图片失败: {e}")
        return {
            "status_code": -1,
            "message": f"上传失败：{str(e)}"
        }

@router.post("/Get_Content/")
def Get_Content_endpoint(req: EditorRequest, current_user: CurrentUser = Depends(require_user)):
    """
    获取指定 Word 文件对应的 HTML 内容。
    根据 source_type 精准定位。
    """
    logger.info(f"接收到获取内容请求: {req}")
    user_id = current_user.id
    
    try:
        docx_path = get_file_path(req.type_name, req.report_name, req.file_name, req.source_type, user_id=user_id)
        
        if not docx_path:
            logger.warning(f"文件不存在: {req.file_name} (source_type={req.source_type})")
            return {
                "report_generation_status": 1,
                "report_generation_condition": "文件不存在",
                "status": req.status,
                "html_content": ""
            }

        # 对应的 HTML 路径
        html_path = os.path.splitext(docx_path)[0] + ".html"
        
        images_dir, url_prefix = get_image_context(req.type_name, req.report_name, req.source_type, user_id)

        if os.path.exists(html_path):
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                legacy_prefix = "/python-api/editor_images/"
                expected_prefix = f"/python-api/editor_images/{'report_merge' if req.source_type in ['report_merge', 'merge'] else 'report'}/"
                needs_regen = legacy_prefix in content and expected_prefix not in content
                if needs_regen:
                    if not os.path.exists(images_dir):
                        os.makedirs(images_dir)
                    convert_docx_to_html(
                        docx_path,
                        user_id=user_id,
                        image_output_dir=images_dir,
                        image_url_prefix=url_prefix
                    )
                    with open(html_path, "r", encoding="utf-8") as f:
                        content = f.read()
                logger.info("✅ 成功读取现有 HTML 文件")
                return {
                    "report_generation_status": 0,
                    "report_generation_condition": "获取成功",
                    "status": req.status,
                    "html_content": content
                }
            except Exception as e:
                logger.error(f"读取 HTML 文件失败: {e}")
        
        logger.info("HTML 文件不存在，尝试从 Docx 实时转换...")
        try:
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            success = convert_docx_to_html(
                docx_path,
                user_id=user_id,
                image_output_dir=images_dir,
                image_url_prefix=url_prefix
            )
            if not success:
                raise RuntimeError("docx 转换失败")
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            logger.info("✅ 实时转换并保存成功")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "获取成功(实时生成)",
                "status": req.status,
                "html_content": html_content
            }
        except Exception as e:
            logger.error(f"Word 转 HTML 失败: {e}")
            return {
                "report_generation_status": 1,
                "report_generation_condition": f"转换失败: {str(e)}",
                "status": req.status,
                "html_content": ""
            }

    except Exception as e:
        logger.error(f"系统异常: {e}", exc_info=True)
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"系统异常: {str(e)}",
            "status": req.status,
            "html_content": ""
        }

@router.post("/Save_Content/")
def Save_Content_endpoint(req: SaveContentRequest, current_user: CurrentUser = Depends(require_user)):
    """
    保存前端编辑后的 HTML 内容。
    注意：目前只覆盖 HTML 文件，暂未实现 HTML -> Word 的反向转换。
    """
    logger.info(f"接收到保存请求: {req.file_name}")
    user_id = current_user.id
    
    try:
        docx_path = get_file_path(req.type_name, req.report_name, req.file_name, req.source_type, user_id=user_id)
        
        if not docx_path:
            logger.warning(f"目标文件不存在，无法保存: {req.file_name} (source_type={req.source_type})")
            return {
                "report_generation_status": 1,
                "report_generation_condition": "原文件不存在，无法定位保存路径",
                "status": req.status
            }

        # 对应的 HTML 路径
        html_path = os.path.splitext(docx_path)[0] + ".html"
        
        # 覆盖写入 HTML
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(req.html_content)
            logger.info(f"✅ HTML 内容已更新: {html_path}")
            
            # 2. 执行转换并覆盖
            # 注意：这会直接覆盖磁盘上的 .docx 文件
            success = convert_html_to_docx(req.html_content, docx_path)

            if success:
                logger.info(f"✅ Word 文件已覆盖更新: {docx_path}")
                return {
                    "report_generation_status": 0,
                    "report_generation_condition": "保存成功 (HTML 与 Word 已同步更新)",
                    "status": req.status
                }
            else:
                logger.error(f"❌ HTML 保存成功，但 Word 转换失败: {docx_path}")
                return {
                    "report_generation_status": 1, # 这里返回1，因为转换失败了，虽然HTML保存了
                    "report_generation_condition": "HTML保存成功，但Word转换失败，请查看日志",
                    "status": req.status
                }
            
        except Exception as e:
            logger.error(f"写入 HTML 失败: {e}")
            return {
                "report_generation_status": 1,
                "report_generation_condition": f"写入失败: {str(e)}",
                "status": req.status
            }

    except Exception as e:
        logger.error(f"系统异常: {e}", exc_info=True)
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"系统异常: {str(e)}",
            "status": req.status
        }

class DeleteImageRequest(BaseModel):
    file_path: str # 前端传来的图片路径 (可能是 URL 或 相对路径)

@router.post("/delete_editor_image/")
def delete_editor_image_endpoint(req: DeleteImageRequest, current_user: CurrentUser = Depends(require_user)):
    """
    删除编辑器图片接口
    供前端在保存时调用，删除那些被用户移除的图片。
    """
    user_id = current_user.id
    raw_path = req.file_path
    
    # 1. 过滤 Base64 图片 (Word 原生图片)
    if raw_path.startswith("data:"):
        return {
            "status_code": 0,
            "message": "Base64 图片无需删除",
            "data": {"deleted": False}
        }

    try:
        relative_path = raw_path
        if "editor_images/" in relative_path:
            relative_path = relative_path.split("editor_images/", 1)[1]
        relative_path = relative_path.split("?", 1)[0].split("#", 1)[0]
        relative_path = relative_path.lstrip("/")
        if not relative_path:
            return {
                "status_code": -1,
                "message": "非法的文件路径",
                "data": {"deleted": False}
            }
        relative_path = os.path.normpath(relative_path)
        if os.path.isabs(relative_path) or relative_path.startswith("..") or ".." in relative_path.split(os.sep):
            return {
                "status_code": -1,
                "message": "非法的文件路径",
                "data": {"deleted": False}
            }
        parts = relative_path.split(os.sep)
        if len(parts) == 1:
            relative_path = os.path.join(str(user_id), parts[0])
            parts = relative_path.split(os.sep)
        if parts[0] in ["report", "report_merge"]:
            if len(parts) < 3 or parts[1] != str(user_id):
                return {
                    "status_code": -1,
                    "message": "非法的文件路径",
                    "data": {"deleted": False}
                }
        elif parts[0] != str(user_id):
            return {
                "status_code": -1,
                "message": "非法的文件路径",
                "data": {"deleted": False}
            }
        file_path = os.path.join(server_config.EDITOR_IMAGE_DIR, relative_path)
        
        # 4. 执行删除
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"图片已删除: {file_path}")
            return {
                "status_code": 0,
                "message": "删除成功",
                    "data": {"deleted": True, "file": relative_path}
            }
        else:
            logger.warning(f"删除失败，文件不存在: {file_path} (raw: {raw_path})")
            return {
                "status_code": 0, # 幂等性，不存在也算成功
                "message": "文件不存在或已删除",
                "data": {"deleted": False}
            }
            
    except Exception as e:
        logger.error(f"删除图片异常: {e}", exc_info=True)
        return {
            "status_code": -1,
            "message": f"删除失败: {str(e)}",
            "data": {"deleted": False}
        }

@router.post("/clean_images/")
def clean_images_endpoint(dry_run: bool = False, current_user: CurrentUser = Depends(require_user)):
    """
    清理当前用户下未被任何报告引用的孤儿图片。
    :param dry_run: 如果为 true，仅列出将要删除的文件但不执行删除。
    """
    user_id = current_user.id
    logger.info(f"接收到图片清理请求: User={user_id}, DryRun={dry_run}")
    
    result = clean_orphaned_images(user_id, dry_run=dry_run)
    return {
        "status_code": 0,
        "message": result.get("message", "执行完毕"),
        "data": result
    }
