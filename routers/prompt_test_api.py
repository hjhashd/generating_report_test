import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from utils.lyf.prompt_test import prompt_test_service

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
    user_input: str

@router.post("/prompt_test/stream")
async def test_stream_endpoint(request: TestRequest, current_user: dict = Depends(require_user)):
    """
    【快速测试】流式接口：不显式展示推理链，直接返回结果
    """
    logger.info(f"🚀 [Test] User: {current_user.id} 正在测试 Prompt")

    async def event_generator():
        # 调用测试服务的流式方法（带过滤 <think> 功能）
        for chunk in prompt_test_service.run_test_stream(request.system_prompt, request.user_input):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
