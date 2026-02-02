import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from utils.zzp.query_report import get_all_reports_list
from routers.dependencies import require_user, CurrentUser

#返回所有的报告在前端进行展示
# logging.basicConfig(level=logging.INFO,
#                     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 请求参数模型 (保持不变，以免前端报错)
class QueryReport(BaseModel):
    task_id: str
    status: int
    agentUserId: int

@router.post("/Query_report/")
def Query_report_endpoint(report: QueryReport, current_user: CurrentUser = Depends(require_user)):
    logger.info(f'接收到的参数：{report}')
    user_id = current_user.id
    logger.info(f"Current User ID: {user_id}")

    try:
        # 1. 直接执行查询函数 (因为耗时很短，直接等待结果)
        report_list = get_all_reports_list(user_id=user_id)
        
        # 2. 判断结果
        if report_list:
            logger.info(f"✅ 查询成功，共 {len(report_list)} 条数据")
            return {
                "report_generation_status": 0,         # 0 表示成功
                "report_generation_condition": "查询成功",
                "modul_list": report_list,              # 直接把数据返回给前端
                "status": report.status                # 原样返回状态
            }
        else:
            logger.info("⚠️ 未获取到任何数据")
            return {
                "report_generation_status": 0,         # 没查到数据通常不算接口报错，依然返回 0
                "report_generation_condition": "数据库中暂时没有报告数据",
                "modul_list": [],                      # 返回空列表
                "status": report.status
            }

    except Exception as e:
        logger.error(f"❌ 查询模块失败: {e}", exc_info=True)
        # 3. 发生异常时的返回
        return {
            "report_generation_status": 1,             # 1 表示失败
            "report_generation_condition": f"读取模块失败: {str(e)}",
            "status": report.status,
            "modul_list": []
        }

@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}