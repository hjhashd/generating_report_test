import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from routers.dependencies import require_user

# 引入两个核心流式生成函数
# 1. 写作生成 (Chat_generator_stream)
from utils.zzp.ai_generate_langchain import Chat_generator_stream
# 2. 润色优化 (optimize_text_stream)
from utils.zzp.ai_adjustment import optimize_text_stream
from utils.zzp.ai_summary import ai_summary_stream

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# ==========================================
# 通用响应头 (防止 Nginx/浏览器缓存流数据)
# ==========================================
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no" # Nginx 专用头，禁止缓冲
}

# ==========================================
# 1. 写作生成相关 (Generate_Summary)
# ==========================================
class GenerateSummaryRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    # 业务参数
    id: int                       # 模型ID (数据库中的配置ID)
    folder_name: str              # 目录名称 (Prompt上下文定义)
    material_name_list: List[str] # 材料名称列表 (用于查库找文件)
    instruction: str              # 具体指令 (如"生成200字综述...")

# ==========================================
# 2. 润色优化相关 (Optimize_Text) - 新增部分
# ==========================================
class OptimizeTextRequest(BaseModel):
    task_id: str                # 任务ID，用于上下文隔离
    status: int
    agentUserId: int
    id: int                       # 模型ID (数据库中的配置ID)
    text: str                   # 待润色的原文
    requirements: List[str]     # 前端勾选的需求列表，如 ["优化逻辑", "专业术语"]

class SummaryRequest(BaseModel):
    task_id: str                # 任务ID，用于上下文隔离
    status: int
    agentUserId: int
    id: int                       # 模型ID (数据库中的配置ID)
    text: str
    instruction: Optional[str] = None  # 新增：自定义总结指令


@router.post("/Generate_Summary_Stream/")
async def Generate_Summary_Stream_endpoint(request: GenerateSummaryRequest, current_user: dict = Depends(require_user)):
    """
    【写作生成】流式接口
    功能：根据材料或目录生成新文本
    """
    user_id = current_user.id
    logger.info(f'📝 [写作] 接收任务: {request.task_id} | User: {current_user.username}')
    logger.info(f'    目录: {request.folder_name}, 材料数: {len(request.material_name_list)}')

    return StreamingResponse(
        Chat_generator_stream(
            folder_name=request.folder_name,
            material_name_list=request.material_name_list,
            instruction=request.instruction,
            model_id=request.id,    
            task_id=request.task_id,
            user_id=user_id
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS
    )


@router.post("/Optimize_Text_Stream/")
async def Optimize_Text_Stream_endpoint(request: OptimizeTextRequest, current_user: dict = Depends(require_user)):
    """
    【润色优化】流式接口
    功能：根据前端的需求列表，对输入文本进行修改
    """
    user_id = current_user.id
    logger.info(f'✨ [润色] 接收任务: {request.task_id} | User: {current_user.username}')
    logger.info(f'    原文长度: {len(request.text)}, 需求项: {request.requirements}')

    return StreamingResponse(
        optimize_text_stream(
            text=request.text,
            requirements=request.requirements,
            model_id=request.id,
            task_id=request.task_id,
            user_id=user_id
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS
    )
    
@router.post("/ai_summary/stream")
async def api_summary(req: SummaryRequest):
    return StreamingResponse(
        ai_summary_stream(req.text, req.id, req.instruction, req.agentUserId),
        media_type="text/event-stream",
        headers=STREAM_HEADERS
    )
# ==========================================
# 3. 系统检查
# ==========================================
@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}