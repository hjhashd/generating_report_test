import logging
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from utils.lyf.prompt_chat import PromptChat

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    query: str

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
}

# 伪造一个 require_user 用于测试（如果需要的话），或者直接用真实的
# 这里我们假设 dependencies.py 里的 require_user 是可用的
# 但为了防止循环依赖或其他问题，我们先确认 import 是否正确

@router.get("/test_ping")
def test_ping():
    return {"message": "pong"}

@router.post("/prompt_chat/clear")
def clear_chat_session(current_user: dict = Depends(require_user)):
    """
    清除当前用户的对话历史，开始新的优化任务
    """
    try:
        if isinstance(current_user, dict):
            user_id = str(current_user.get("id"))
        else:
            user_id = str(current_user.id)
            
        chat_service = PromptChat()
        chat_service.session_mgr.clear_session(user_id)
        logger.info(f"🧹 [Chat] Cleared session for user: {user_id}")
        return {"status": "success", "message": "Session cleared"}
    except Exception as e:
        logger.error(f"Clear session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompt_chat/stream")
def chat_stream_endpoint(request: ChatRequest, current_user: dict = Depends(require_user)):
    """
    【多轮对话】流式接口：支持上下文摘要与用户隔离
    注意：使用同步 def 以利用 FastAPI 的线程池，避免阻塞主循环
    """
    try:
        # 兼容性处理：如果 current_user 是字典则用字典访问，如果是对象则用属性访问
        if isinstance(current_user, dict):
            user_id = str(current_user.get("id"))
        else:
            user_id = str(current_user.id)
            
        logger.info(f"💬 [Chat] User: {user_id} | Query: {request.query[:20]}...")

        def event_generator():
            chat_service = PromptChat()
            try:
                for content in chat_service.chat_stream(user_id, request.query):
                    payload = json.dumps({"content": content}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}", exc_info=True)
                yield f"data: {json.dumps({'content': f'[Error: {str(e)}]'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
    except Exception as e:
        logger.error(f"Endpoint error: {e}", exc_info=True)
        return {"error": str(e)}
