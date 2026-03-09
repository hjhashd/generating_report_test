import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no"
}

class TestRequest(BaseModel):
    system_prompt: str
    user_input: Optional[str] = None  # 可选，如果不提供则只根据 system_prompt 测试
    session_id: Optional[int] = None

@router.post("/prompt_test/stream")
async def test_stream_endpoint(request: TestRequest, current_user: dict = Depends(require_user)):
    """
    【快速测试】流式接口：实时输出（包括推理过程），支持会话隔离
    """
    try:
        if isinstance(current_user, dict):
            user_id = current_user.get("id")
        else:
            user_id = getattr(current_user, "id", None)

        try:
            user_id = int(user_id)
        except Exception:
            raise HTTPException(status_code=401, detail="unauthorized")
            
        logger.info(f"🚀 [Test] User: {user_id} 正在测试 Prompt")

        async def event_generator():
            from utils.lyf.prompt_test import PromptTest
            test_service = PromptTest()
            
            try:
                logger.info(f"开始生成测试流... User: {user_id}")
                for chunk in test_service.run_test_stream(request.system_prompt, request.user_input):
                    yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                
                logger.info(f"测试流生成完成. User: {user_id}")
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Test stream generation error: {e}", exc_info=True)
                yield f"data: {json.dumps({'content': f'[Error: {str(e)}]'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
    except Exception as e:
        logger.error(f"Test endpoint error: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise
        return {"error": str(e)}
