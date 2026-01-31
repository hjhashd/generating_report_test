import logging
import json
import time
import traceback
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

# 核心逻辑文件
from utils.lyf.ai_search import Search_Chat_Generator_Stream
from utils.zzp.ai_generate_langchain import get_llm_config_by_id

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no" 
}

class SearchRequest(BaseModel):
    task_id: str
    user_query: str
    id: int
    model_name: str
    base_url: str
    api_key: str
    status: Optional[int] = 1
    agentUserId: Optional[int] = None

@router.post("/ai_search/stream")
async def ai_search_endpoint(req: SearchRequest):
    """
    【联网搜索】流式接口 - 增强日志版
    """
    # 0. 尝试从数据库补充配置 (如果请求中的配置不完整)
    model_name = req.model_name
    base_url = req.base_url
    api_key = req.api_key
    
    if req.id and (not model_name or not api_key or model_name.strip() == ""):
        logger.info(f"🔍 尝试从数据库获取模型配置 | ID: {req.id}")
        db_config = get_llm_config_by_id(req.id)
        if db_config:
            model_name = db_config.get("model_name", model_name).strip()
            base_url = db_config.get("base_url", base_url)
            api_key = db_config.get("api_key", api_key)
            logger.info(f"✅ 已从数据库加载配置: '{model_name}'")

    # 1. 记录请求进入的详细元数据
    start_time = time.time()
    log_context = {
        "task_id": req.task_id,
        "model": model_name,
        "query_len": len(req.user_query),
        "user_id": req.agentUserId
    }
    
    logger.info(f"🚀 [AI Search] 收到新请求 | Context: {json.dumps(log_context, ensure_ascii=False)}")
    logger.debug(f"📝 [AI Search] 完整问题: {req.user_query}")

    # 2. 包装生成器以捕获流式传输中的异常
    async def wrapped_generator():
        try:
            # 记录流开始
            logger.info(f"🌊 [AI Search] 流输出开始 | TaskID: {req.task_id}")
            
            chunk_count = 0
            async for chunk in Search_Chat_Generator_Stream(
                user_query=req.user_query,
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
                task_id=req.task_id
            ):
                yield chunk
                chunk_count += 1
            
            # 3. 记录流正常结束
            duration = round(time.time() - start_time, 2)
            logger.info(f"✅ [AI Search] 流输出完成 | TaskID: {req.task_id} | 总耗时: {duration}s | 数据块数量: {chunk_count}")

        except Exception as e:
            # 4. 关键：捕获生成器内部的异常并记录堆栈
            duration = round(time.time() - start_time, 2)
            error_msg = traceback.format_exc()
            logger.error(f"❌ [AI Search] 流输出中断 | TaskID: {req.task_id} | 耗时: {duration}s | 错误: {str(e)}\n{error_msg}")
            
            # 向前端推送一个符合 SSE 格式的错误消息
            # 改为 content 字段，确保前端能显示
            error_payload = json.dumps({"content": f"\n\n❌ [系统错误] 接口处理中断: {str(e)}", "task_id": req.task_id}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"

    try:
        return StreamingResponse(
            wrapped_generator(),
            media_type="text/event-stream",
            headers=STREAM_HEADERS
        )
    except Exception as e:
        # 这里捕获的是初始化 StreamingResponse 之前的错误
        logger.error(f"🚨 [AI Search] 接口启动失败 | TaskID: {req.task_id} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
def health_check():
    return {"status": "healthy"}