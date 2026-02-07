import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from routers.dependencies import require_user

# 引入核心函数
from utils.zzp.ai_generate_langchain import Chat_generator_stream
# 确保这里引入了我们新写的 get_prompt_list_by_folder
from utils.zzp.ai_adjustment import optimize_text_stream, get_prompt_list_by_folder
from utils.zzp.ai_summary import ai_summary_stream

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# ==========================================
# 通用响应头
# ==========================================
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no"
}

# ==========================================
# 数据模型 (Request Models)
# ==========================================

class GenerateSummaryRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    id: int                       # 模型ID
    folder_name: str              
    material_name_list: List[str] 
    instruction: str              

class OptimizeTextRequest(BaseModel):
    task_id: str                
    status: int
    agentUserId: int
    id: int                     # 模型ID
    text: str                   
    prompt_ids: List[int]       # 前端选中的 ID 列表

class SummaryRequest(BaseModel):
    task_id: str                
    status: int
    agentUserId: int
    id: int                     
    text: str
    instruction: Optional[str] = None

# ==========================================
# 1. 提示词管理接口 (新增)
# ==========================================

@router.get("/Prompts_List/")
async def get_prompts_endpoint(
    folder_id: int = Query(..., description="文件夹ID"),
    current_user: dict = Depends(require_user)
):
    """
    【获取提示词列表】
    功能：前端渲染下拉列表前，先调用此接口获取当前文件夹下的所有提示词 (ID 和 标题)
    """
    # [修改] 强制写死为用户 7 和 文件夹 402，因为只有该配置下有公开的提示词数据
    user_id = 7 
    target_folder_id = 402
    logger.info(f"🔍 [列表] 用户 {current_user.id} 请求文件夹 {folder_id} 的提示词列表 (强制使用用户7和文件夹402的数据)")
    
    # 调用 utils 里的查询函数
    prompts = get_prompt_list_by_folder(target_folder_id, user_id)
    
    return {
        "code": 200,
        "data": prompts,  # 返回示例: [{"id": 591, "title": "商务润色"}, {"id": 592, "title": "去口语化"}]
        "msg": "success"
    }

# ==========================================
# 2. 核心流式业务接口
# ==========================================

@router.post("/Optimize_Text_Stream/")
async def Optimize_Text_Stream_endpoint(request: OptimizeTextRequest, current_user: dict = Depends(require_user)):
    """
    【润色优化】流式接口
    """
    # [修改] 强制写死为用户 7，以使用该用户的公开提示词模板进行润色
    user_id = 7
    logger.info(f'✨ [润色] 接收任务: {request.task_id} | 真实用户: {current_user.username} (强制使用用户7的权限)')
    logger.info(f'    原文长度: {len(request.text)}, Prompt IDs: {request.prompt_ids}')

    return StreamingResponse(
        optimize_text_stream(
            text=request.text,
            prompt_ids=request.prompt_ids,
            model_id=request.id,
            task_id=request.task_id,
            user_id=user_id
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS
    )

@router.post("/Generate_Summary_Stream/")
async def Generate_Summary_Stream_endpoint(request: GenerateSummaryRequest, current_user: dict = Depends(require_user)):
    """
    【写作生成】流式接口
    """
    user_id = current_user.id
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

@router.post("/ai_summary/stream")
async def api_summary(req: SummaryRequest, current_user: dict = Depends(require_user)):
    """
    【文本总结】流式接口
    """
    return StreamingResponse(
        ai_summary_stream(req.text, req.id, req.instruction, current_user.id),
        media_type="text/event-stream",
        headers=STREAM_HEADERS
    )

# ==========================================
# 3. 系统检查
# ==========================================
@router.get("/health")
def health_check():
    return {"status": "healthy"}