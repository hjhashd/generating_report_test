import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from routers.dependencies import require_user
# 确保导入路径正确，根据你的实际项目结构调整
from utils.zzp.insert_llm_config import save_custom_config

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 1. 修正 Pydantic 模型
class InsertLLMRequest(BaseModel):
    # 这些是业务流转参数，根据需要保留
    task_id: str
    status: int
    agentUserId: int

    # 这些是需要存入数据库的 LLM 参数
    # 注意：这里使用类型注解 (: str)，不要写死默认值，除非你真的想默认
    model_name: str
    api_key: str 
    base_url: str

@router.post("/insert_llm_config/") # 建议修改 URL 路径使其更具可读性
def insert_llm_endpoint(request: InsertLLMRequest, current_user: dict = Depends(require_user)):
    logger.info(f'接收到的配置请求 - TaskID: {request.task_id}, Model: {request.model_name}, User: {current_user.username}')

    try:
        # 2. 调用工具函数并接收返回值 (True/False)
        is_success = save_custom_config(
            model_name=request.model_name, 
            api_key=request.api_key, 
            base_url=request.base_url,
            user_id=current_user.id
        )

        # 3. 根据返回值构建响应
        if is_success:
            logger.info(f"✅ 配置插入/更新成功")
            return {
                "code": 200,                  # 标准状态码
                "message": "LLM配置保存成功",   # 明确的提示信息
                "task_id": request.task_id,   # 返回任务ID方便前端追踪
                "status": request.status      # 保持原样返回
            }
        else:
            logger.warning("⚠️ 配置保存失败 (数据库操作返回 False)")
            return {
                "code": 500,
                "message": "配置保存失败，请检查服务端日志",
                "task_id": request.task_id,
                "status": request.status
            }

    except Exception as e:
        logger.error(f"❌ 接口异常: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"服务器内部错误: {str(e)}",
            "task_id": request.task_id,
            "status": request.status
        }

@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}