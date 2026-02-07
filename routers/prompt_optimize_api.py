import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from utils.lyf.prompt_optimize import prompt_optimize_service

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no"
}

class OptimizeRequest(BaseModel):
    raw_prompt: str
    target_scene: str  # 目标场景，如“公文写作”、“代码生成”

@router.post("/prompt_optimize/stream")
async def optimize_stream_endpoint(request: OptimizeRequest, current_user: dict = Depends(require_user)):
    """
    【提示词优化】流式接口：将口语化提示词转为结构化指令
    """
    logger.info(f"🛠️ [Optimize] User: {current_user.id} 正在优化提示词")

    async def event_generator():
        # 调用优化服务的流式方法
        for chunk in prompt_optimize_service.optimize_stream(request.raw_prompt, request.target_scene):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
