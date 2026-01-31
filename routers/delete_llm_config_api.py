import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from routers.dependencies import require_user

# 正确导入删除方法（按你前面写的）
from utils.lyf.del_model import delete_config

# ==========================
# 日志（路由级，不配置 basicConfig）
# ==========================
logger = logging.getLogger(__name__)

router = APIRouter()

# ==========================
# 请求模型（名称与使用保持一致）
# ==========================
class DeleteLLMRequest(BaseModel):
    # 业务流转参数（透传）
    task_id: str
    status: int
    agentUserId: int

    # 实际删除所需参数
    config_id: int


# ==========================
# 删除配置接口
# ==========================
@router.post("/delete_llm_config/")
def delete_llm_endpoint(request: DeleteLLMRequest, current_user: dict = Depends(require_user)):
    """
    删除指定 ID 的 LLM 配置
    """
    user_id = current_user.id
    logger.info(
        f"接收到删除配置请求 | task_id={request.task_id} | "
        f"user_id={user_id} | config_id={request.config_id}"
    )

    try:
        # 调用底层删除逻辑
        is_success = delete_config(request.config_id, user_id=user_id)

        if is_success:
            logger.info(f"配置删除成功 | config_id={request.config_id}")
            return {
                "code": 200,
                "message": "LLM 配置删除成功",
                "task_id": request.task_id,
                "status": request.status
            }
        else:
            logger.warning(f"配置删除失败（可能不存在） | config_id={request.config_id}")
            return {
                "code": 404,
                "message": "配置不存在或已被删除",
                "task_id": request.task_id,
                "status": request.status
            }

    except Exception as e:
        logger.error(f"删除配置接口异常: {e}", exc_info=True)
        return {
            "code": 500,
            "message": "服务器内部错误",
            "task_id": request.task_id,
            "status": request.status
        }


# ==========================
# 健康检查
# ==========================
@router.get("/health")
def health_check():
    return {"status": "healthy"}
