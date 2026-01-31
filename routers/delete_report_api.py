import logging
from fastapi import APIRouter, Depends
from routers.dependencies import require_user, CurrentUser
from pydantic import BaseModel
from typing import List

# 引入之前写好的核心删除函数
from utils.zzp.delete_report import delete_report_task

# ==========================
# 日志配置
# ==========================
logger = logging.getLogger(__name__)

router = APIRouter()

# ==========================
# 1. 定义请求数据模型
# ==========================
"""
{
  "task_id": "task_999",
  "status": 1,
  "agentUserId": 1001,
  "delete_list": [
    {
      "type": "资产报告",
      "name": "通用资产报告"
    },
    {
      "type": "可行性研究报告",
      "name": "AI项目一期"
    },
    {
      "type": "不存在的类型",
      "name": "测试一下容错"
    }
  ]
}
"""
# 定义单个删除目标的数据结构 (对应 BATCH_TASKS 里的每一项)
class ReportTargetItem(BaseModel):
    type: str  # 对应 report_type.type_name (如: "资产报告")
    name: str  # 对应 report_name.report_name (如: "通用资产报告")

# 定义主请求模型
class DeleteReportRequest(BaseModel):
    # 业务流转参数（透传）
    task_id: str
    status: int
    agentUserId: int

    # 核心业务参数：要删除的列表
    # 这是一个列表，里面包含多个 type 和 name
    delete_list: List[ReportTargetItem]


# ==========================
# 2. 批量删除接口
# ==========================
@router.post("/delete_report_batch/")
def delete_report_batch_endpoint(request: DeleteReportRequest, current_user: CurrentUser = Depends(require_user)):
    """
    批量删除报告接口
    功能：根据传入的列表，级联删除数据库记录及物理文件/文件夹
    """
    task_id = request.task_id
    targets = request.delete_list
    total_count = len(targets)
    user_id = current_user.id

    logger.info(f"接收到批量删除任务 | task_id={task_id} | 待删除数量={total_count} | User={user_id}")

    success_count = 0
    fail_count = 0
    failed_items = [] # 记录失败的项目以便排查

    try:
        # 遍历列表，逐个执行删除
        for index, item in enumerate(targets):
            # 调用核心逻辑
            # 注意：delete_report_task 返回 True 或 False
            is_deleted = delete_report_task(item.type, item.name, user_id=user_id)

            if is_deleted:
                success_count += 1
                logger.info(f"[{index+1}/{total_count}] 删除成功: {item.type} - {item.name}")
            else:
                fail_count += 1
                failed_items.append(f"{item.type}-{item.name}")
                logger.warning(f"[{index+1}/{total_count}] 删除失败: {item.type} - {item.name}")

        # 构造返回结果
        result_msg = f"批量删除完成。成功: {success_count}, 失败: {fail_count}"
        
        response_data = {
            "code": 200,
            "message": result_msg,
            "task_id": task_id,
            "status": request.status,
            "data": {
                "total": total_count,
                "success": success_count,
                "fail": fail_count,
                "failed_list": failed_items # 返回失败的具体名单
            }
        }
        
        logger.info(f"任务结束 | {result_msg}")
        return response_data

    except Exception as e:
        logger.error(f"批量删除接口发生异常: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"服务器内部错误: {str(e)}",
            "task_id": task_id,
            "status": request.status
        }


# ==========================
# 健康检查
# ==========================
@router.get("/report_health")
def health_check():
    return {"status": "healthy", "module": "delete_report"}