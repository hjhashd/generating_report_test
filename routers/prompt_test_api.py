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
def test_stream_endpoint(request: TestRequest, current_user: dict = Depends(require_user)):
    """
    【快速测试】流式接口：实时输出（包括推理过程）
    """
    try:
        # 兼容性处理：如果 current_user 是字典则用字典访问，如果是对象则用属性访问
        if isinstance(current_user, dict):
            user_id = str(current_user.get("id"))
        else:
            user_id = str(current_user.id)
            
        logger.info(f"🚀 [Test] User: {user_id} 正在测试 Prompt")

        def event_generator():
            # 动态实例化服务类，确保线程安全并与 Chat 接口模式一致
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
        return {"error": str(e)}
