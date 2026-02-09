import logging
import os
from fastapi import APIRouter, Depends
from routers.dependencies import require_user, CurrentUser
from pydantic import BaseModel
from typing import List
from urllib.parse import quote
import os
import server_config # Import server_config
TARGET_ROOT_DIR = server_config.MERGE_DIR# 1. 导入核心函数 和 根路径变量
from utils.zzp.report_merge import process_report_merge, get_sorted_source_files
from utils.zzp.query_merged_report import get_merged_reports_list
from utils.zzp.delete_merged_report import delete_merged_report_task
from utils.zzp.docx_to_html import convert_docx_to_html, convert_docx_list_to_merged_html

# ==========================
# 日志配置
# ==========================
logger = logging.getLogger(__name__)

router = APIRouter()

# ==========================
# 1. 定义请求数据模型
# ==========================
class MergeReportRequest(BaseModel):
    # 业务上下文参数
    task_id: str
    status: int
    agentUserId: int

    # 核心参数：用于定位需要合并的报告
    type_name: str    # 如: "资产报告"
    report_name: str  # 如: "通用资产报告"


# 新增：查询已合并报告列表请求模型
class QueryMergedReportRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: int


# 新增：批量删除已合并报告请求模型
class DeleteMergedReportRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    delete_list: List[int]  # 传入已合并报告的 ID 列表


# ==========================
# 2. 报告合并接口
# ==========================
@router.post("/merge_report_file/")
def merge_report_endpoint(request: MergeReportRequest, current_user: CurrentUser = Depends(require_user)):
    """
    合并报告接口
    功能：将指定报告下的所有子文件合并为一个 Word 文档
    返回：固定返回服务器上的存储根路径 (TARGET_ROOT_DIR)
    """
    task_id = request.task_id
    t_type = request.type_name
    t_name = request.report_name
    user_id = current_user.id

    logger.info(f"接收到合并请求 | task_id={task_id} | 目标={t_type}-{t_name} | User={user_id}")

    try:
        # 调用核心逻辑
        # process_report_merge 返回 (True/False, "详细消息")
        is_success, msg = process_report_merge(t_type, t_name, user_id=user_id)

        if is_success:
            logger.info(f"合并成功: {msg}")
            
            # --- 新增：生成 HTML 文件 ---
            # 构造合并后的 DOCX 文件路径 (逻辑需与 report_merge.py 保持一致)
            base_merge_dir = server_config.get_user_merge_dir(user_id)
            save_dir = os.path.join(base_merge_dir, t_type)
            final_file_name = f"{t_name}.docx"
            merged_docx_path = os.path.join(save_dir, final_file_name)
            
            logger.info(f"开始生成对应的 HTML 文件: {merged_docx_path}")
            
            images_dir = os.path.join(
                server_config.EDITOR_IMAGE_DIR,
                "report_merge",
                str(user_id),
                t_type,
                t_name
            )
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            
            url_prefix = f"/python-api/editor_images/report_merge/{user_id}/{quote(t_type)}/{quote(t_name)}/"

            html_success = convert_docx_to_html(
                merged_docx_path, 
                user_id=user_id,
                image_output_dir=images_dir,
                image_url_prefix=url_prefix
            )
            merged_html_path = os.path.join(save_dir, f"{t_name}.html")
            source_list = get_sorted_source_files(t_type, t_name, user_id=user_id)
            html_merge_success = False
            if source_list:
                html_merge_success = convert_docx_list_to_merged_html(
                    source_list, 
                    merged_html_path, 
                    user_id=user_id,
                    image_output_dir=images_dir,
                    image_url_prefix=url_prefix
                )
            
            if html_success or html_merge_success:
                logger.info("HTML 文件生成完成")
            else:
                logger.warning("HTML 文件生成失败")
            # --------------------------

            # 构造返回数据
            return {
                "code": 200,
                "message": "合并成功",
                "task_id": task_id,
                "status": request.status,
                "data": {
                    # 按照您的要求，返回配置的根路径
                    "merge_root_dir": base_merge_dir,
                    
                    # 建议：同时也返回具体合并后的文件名或完整路径，方便前端拼接
                    # 如果不需要，可以忽略下面这行
                    "detail_msg": msg 
                }
            }
        else:
            logger.warning(f"合并失败: {msg}")
            # [FIX] Use user-specific merge dir to avoid NameError and support multi-user
            base_merge_dir = server_config.get_user_merge_dir(user_id)
            return {
                "code": 500,
                "message": f"合并失败: {msg}",
                "task_id": task_id,
                "status": request.status,
                "data": {
                    "storage_root_dir": base_merge_dir # 即使失败也可以返回根路径供参考
                }
            }

    except Exception as e:
        logger.error(f"合并接口发生异常: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"服务器内部错误: {str(e)}",
            "task_id": task_id,
            "status": request.status
        }


# ==========================
# 3. 查询已合并报告列表接口
# ==========================
@router.post("/Query_Merged_Reports/")
def query_merged_reports_endpoint(request: QueryMergedReportRequest, current_user: CurrentUser = Depends(require_user)):
    """
    查询已合并报告列表接口
    功能：从数据库中获取所有已完成合并的报告记录 (仅返回当前用户的报告)
    """
    task_id = request.task_id
    user_id = current_user.id
    logger.info(f"接收到查询已合并报告列表请求 | task_id={task_id} | User={user_id}")

    try:
        # 调用工具类获取数据 (传入 user_id 进行过滤)
        report_list = get_merged_reports_list(user_id=user_id)

        if report_list:
            logger.info(f"✅ 查询成功，共 {len(report_list)} 条数据")
            return {
                "report_generation_status": 0,         # 0 表示成功
                "report_generation_condition": "查询成功",
                "modul_list": report_list,              # 保持与参考接口一致的字段名
                "status": request.status
            }
        else:
            logger.info("⚠️ 未获取到任何已合并报告数据")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "数据库中暂时没有已合并报告数据",
                "modul_list": [],
                "status": request.status
            }

    except Exception as e:
        logger.error(f"❌ 查询已合并报告列表失败: {e}", exc_info=True)
        return {
            "report_generation_status": 1,             # 1 表示失败
            "report_generation_condition": f"查询失败: {str(e)}",
            "modul_list": [],
            "status": request.status
        }


# ==========================
# 4. 批量删除已合并报告接口
# ==========================
@router.post("/Delete_Merged_Reports_Batch/")
def delete_merged_reports_batch_endpoint(request: DeleteMergedReportRequest, current_user: CurrentUser = Depends(require_user)):
    """
    批量删除已合并报告接口
    功能：根据传入的 ID 列表，删除数据库记录及物理文件 (强制校验归属权)
    """
    task_id = request.task_id
    ids_to_delete = request.delete_list
    total_count = len(ids_to_delete)
    user_id = current_user.id

    logger.info(f"接收到批量删除已合并报告请求 | task_id={task_id} | 数量={total_count} | User={user_id}")

    success_count = 0
    fail_count = 0

    try:
        for mid in ids_to_delete:
            # 传入 user_id 进行归属权校验
            is_deleted = delete_merged_report_task(mid, user_id=user_id)
            if is_deleted:
                success_count += 1
            else:
                fail_count += 1

        result_msg = f"批量删除完成。成功: {success_count}, 失败: {fail_count}"
        logger.info(f"✅ {result_msg}")

        return {
            "code": 200,
            "message": result_msg,
            "task_id": task_id,
            "status": request.status,
            "data": {
                "total": total_count,
                "success": success_count,
                "fail": fail_count
            }
        }

    except Exception as e:
        logger.error(f"❌ 批量删除接口发生异常: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"服务器内部错误: {str(e)}",
            "task_id": task_id,
            "status": request.status
        }


# ==========================
# 健康检查
# ==========================
@router.get("/merge_health")
def health_check():
    return {"status": "healthy", "module": "merge_report"}
