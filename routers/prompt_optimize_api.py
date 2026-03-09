import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from utils.lyf.prompt_optimize import prompt_optimize_service
from utils.lyf.prompt_chat_async import prompt_chat_service
from typing import Optional

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
    session_id: Optional[int] = None

@router.post("/prompt_optimize/stream")
async def optimize_stream_endpoint(request: OptimizeRequest, current_user: dict = Depends(require_user)):
    """
    【提示词优化】流式接口：将口语化提示词转为结构化指令，支持会话隔离
    """
    if isinstance(current_user, dict):
        user_id = current_user.get("id")
    else:
        user_id = getattr(current_user, "id", None)
    try:
        user_id = int(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="unauthorized")

    logger.info(f"🛠️ [Optimize] User: {user_id} 正在优化提示词")

    session_id = request.session_id
    is_new_session = False
    
    if not session_id:
        is_new_session = True
        raw_prompt = (request.raw_prompt or "").strip()
        title = f"优化:{raw_prompt[:10]}" if raw_prompt else "优化"
        session_id = await prompt_chat_service.create_session(user_id, title=title)
        logger.info(f"🆕 [Optimize] Created new session: {session_id} for User: {user_id}")
    else:
        meta = await prompt_chat_service.get_session_meta(int(session_id), int(user_id))
        if not meta:
            raise HTTPException(status_code=404, detail="session 不存在或无权限")
        logger.info(f"🔄 [Optimize] Resuming session: {session_id} for User: {user_id}")

    async def event_generator():
        if is_new_session:
            yield f"data: {json.dumps({'meta': {'session_id': session_id, 'is_new': True}}, ensure_ascii=False)}\n\n"
        
        for chunk in prompt_optimize_service.optimize_stream(request.raw_prompt, request.target_scene):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
