import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
# 引入你的查询函数
from utils.zzp.query_modul import query_and_print_report_stats
from routers.dependencies import require_user, CurrentUser

#查询模块中的具体报告类型和报告名称进行返回
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 请求参数模型 (保持不变，以免前端报错)
class QueryModul(BaseModel):
    task_id: str
    status: int
    agentUserId: int

@router.post("/Query_modul/")
def Query_modul_endpoint(report: QueryModul, current_user: CurrentUser = Depends(require_user)):
    """
    直接查询并返回结果接口
    注意：这里使用 def 而不是 async def。
    因为 query_and_print_report_stats 是同步数据库操作，
    使用 def 可以让 FastAPI 自动将其放入线程池运行，避免阻塞主线程。
    """
    logger.info(f'接收到的参数：{report}')
    user_id = current_user.id

    try:
        # 1. 直接执行查询函数 (因为耗时很短，直接等待结果)
        # [MODIFIED] Pass user_id
        stats_list = query_and_print_report_stats(user_id=user_id)
        
        # 2. 判断结果
        if stats_list:
            logger.info(f"✅ 查询成功，共 {len(stats_list)} 条数据")
            return {
                "report_generation_status": 0,         # 0 表示成功
                "report_generation_condition": "查询成功",
                "modul_list": stats_list,              # 直接把数据返回给前端
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