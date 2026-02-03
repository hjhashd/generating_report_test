import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from routers.dependencies import require_user, CurrentUser
from pydantic import BaseModel
from typing import List, Optional
from utils.zzp.create_catalogue import generate_merged_report_from_json, generate_html_for_report_background
from utils.zzp.delete_report import delete_report_task

# 创建最终的报告目录。
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 清理目标模型
class CleanupTarget(BaseModel):
    type: str
    name: str

# 请求参数模型
class CatalogueRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    catalogue_json: dict
    # [新增] 可选的清理列表，用于在生成完成后自动删除临时模板
    cleanup_targets: Optional[List[CleanupTarget]] = None

def background_generate_and_cleanup(created_files: list, cleanup_targets: List[CleanupTarget], user_id: int):
    """
    组合后台任务：
    1. 生成 HTML (耗时操作)
    2. 清理临时模板 (确保在生成之后执行)
    """
    # 1. 先生成 HTML
    try:
        generate_html_for_report_background(created_files)
    except Exception as e:
        logger.error(f"后台生成 HTML 流程异常: {e}", exc_info=True)

    # 2. 再执行清理
    if cleanup_targets:
        logger.info(f"开始后台清理临时模板，共 {len(cleanup_targets)} 个任务")
        for target in cleanup_targets:
            try:
                # delete_report_task 返回 bool
                success = delete_report_task(target.type, target.name, user_id=user_id)
                if success:
                    logger.info(f"✅ [后台清理] 删除成功: {target.name}")
                else:
                    logger.warning(f"⚠️ [后台清理] 删除失败: {target.name}")
            except Exception as e:
                logger.error(f"❌ [后台清理] 异常: {target.name} - {e}")

@router.post("/Create_Catalogue/")
def Create_Catalogue_endpoint(report: CatalogueRequest, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(require_user)):
    logger.info(f'接收到的参数任务ID：{report.task_id}')
    user_id = current_user.id

    try:
        # 1. 执行生成逻辑 (内部包含查重)
        # 返回已创建的文件列表，用于后台生成 HTML
        # 使用 Token 解析出的 user_id，而不是请求体中的 agentUserId
        created_files = generate_merged_report_from_json(report.catalogue_json, agent_user_id=user_id)
        
        # 2. 将耗时的 HTML 转换任务及清理任务放入后台
        if created_files:
            # 如果有清理任务，使用组合函数；否则直接调用原函数
            if report.cleanup_targets:
                background_tasks.add_task(background_generate_and_cleanup, created_files, report.cleanup_targets, user_id)
            else:
                background_tasks.add_task(generate_html_for_report_background, created_files)
        
        # 3. 提取返回字段
        r_name = report.catalogue_json.get("reportName", "")
        r_type = report.catalogue_json.get("reportType", "")

        # 3. 成功返回
        logger.info(f"✅ 目录生成及入库成功")
        return {
            "report_generation_status": 0,         # 0 表示成功
            "report_generation_condition": "目录生成及入库成功",
            "status": report.status,
            "reportName": r_name,
            "reportType": r_type
        }

    # [新增] 专门捕获查重异常
    except ValueError as ve:
        error_msg = str(ve)
        if "DUPLICATE_REPORT_NAME" in error_msg:
            r_name = report.catalogue_json.get('reportName', '')
            r_type = report.catalogue_json.get('reportType', '')
            logger.warning(f"⚠️ 拦截到重复报告名: {r_name} (类型: {r_type})")
            return {
                "report_generation_status": 2,     # [关键] 返回状态码 2 (或其他非0/1的约定码) 表示"业务逻辑上的拒绝"
                "report_generation_condition": f"在报告类型【{r_type}】下已存在名为【{r_name}】的报告，请更换名称后重试", # 给前端的具体提示
                "status": report.status
            }
        else:
            # 如果是其他 ValueError，按普通错误处理
            logger.error(f"❌ 值错误: {ve}", exc_info=True)
            return {
                "report_generation_status": 1,
                "report_generation_condition": f"数据错误: {error_msg}",
                "status": report.status
            }

    except Exception as e:
        logger.error(f"❌ 生成报告失败: {e}", exc_info=True)
        # 4. 其他系统级异常返回
        return {
            "report_generation_status": 1,         # 1 表示系统错误
            "report_generation_condition": f"系统生成失败: {str(e)}",
            "status": report.status
        }

@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}