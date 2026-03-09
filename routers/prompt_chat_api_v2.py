import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from routers.dependencies import require_user
from utils.lyf.prompt_chat_async import prompt_chat_service
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no"
}

class ChatRequest(BaseModel):
    query: str
    user_id: Optional[int] = None # 如果 require_user 没给，可以手动传
    session_id: Optional[int] = None # 必填：会话ID，若不填则视为新会话
    ref_prompt_id: Optional[int] = None

class CreateSessionRequest(BaseModel):
    title: Optional[str] = None

class RenameSessionRequest(BaseModel):
    title: str

class ForkSessionRequest(BaseModel):
    upto_message_id: int
    title: Optional[str] = None

class RegenerateRequest(BaseModel):
    query: str

def _normalize_query(query: str) -> str:
    return (query or "").strip()

@router.post("/prompt_chat/stream")
async def chat_stream_endpoint(request: ChatRequest, current_user: dict = Depends(require_user)):
    """
    【多轮对话】流式接口：支持上下文摘要与用户隔离
    """
    # 获取用户 ID
    user_id = current_user.id 

    query = _normalize_query(request.query)
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    
    # 核心修复：处理 Session ID
    # 1. 如果前端传了 session_id，则使用它
    # 2. 如果没传，则创建一个新会话
    session_id = request.session_id
    is_new_session = False
    
    if not session_id:
        is_new_session = True
        session_id = await prompt_chat_service.create_session(
            user_id,
            title=query[:10] or "新对话",
            ref_prompt_id=request.ref_prompt_id,
        )
        logger.info(f"🆕 [Chat] Created new session: {session_id} for User: {user_id}")
    else:
        meta = await prompt_chat_service.get_session_meta(int(session_id), int(user_id))
        if not meta:
            raise HTTPException(status_code=404, detail="session 不存在或无权限")
        logger.info(f"🔄 [Chat] Resuming session: {session_id} for User: {user_id}")

    logger.info(f"💬 [Chat] User: {user_id} | Session: {session_id} | Query: {query[:20]}...")

    async def event_generator():
        try:
            # 第一帧：发送元数据（包含 session_id），以便前端保存
            if is_new_session:
                yield f"data: {json.dumps({'meta': {'session_id': session_id, 'is_new': True}}, ensure_ascii=False)}\n\n"
            
            # 后续帧：发送内容
            async for chunk in prompt_chat_service.chat_stream(int(session_id), query):
                # 模仿 SSE 格式包装
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.warning(f"[chat_stream_endpoint] Client disconnected or error: {e}")
            # Client disconnected, stream will be closed automatically

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)

@router.post("/sessions")
async def create_session_endpoint(
    request: CreateSessionRequest,
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    user_id = int(current_user.id)
    title = (request.title or "").strip() or "新对话"
    session_id = await prompt_chat_service.create_session(user_id, title=title)
    meta = await prompt_chat_service.get_session_meta(session_id, user_id)
    return meta or {"session_id": session_id, "title": title}

@router.get("/sessions")
async def list_sessions_endpoint(
    current_user: dict = Depends(require_user),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    user_id = int(current_user.id)
    logger.info(f"[list_sessions_endpoint] User {user_id} requesting sessions with status={status}")
    return await prompt_chat_service.list_sessions(user_id=user_id, limit=limit, status=status)

@router.get("/sessions/by-prompt/{prompt_id}")
async def get_session_by_prompt_endpoint(
    prompt_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    """
    根据 prompt_id 查找关联的会话
    
    用于前端判断：当用户从外部进入提示词编辑区时，
    如果存在关联的会话（origin_prompt_id === prompt_id），
    可以直接跳转到该会话而不是创建新的草稿会话
    """
    user_id = int(current_user.id)
    session = await prompt_chat_service.get_session_by_origin_prompt_id(user_id=user_id, prompt_id=prompt_id)
    if session:
        return {"found": True, "session": session}
    return {"found": False, "session": None}

@router.get("/sessions/{session_id}/messages")
async def get_messages_endpoint(
    session_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
    limit: int = Query(200, ge=1, le=500),
) -> Dict[str, Any]:
    user_id = int(current_user.id)
    # 获取会话元数据（包含 final_content）
    meta = await prompt_chat_service.get_session_meta(session_id, user_id)
    if not meta:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")

    messages = await prompt_chat_service.get_messages(session_id=session_id, user_id=user_id, limit=limit)

    return {
        "session": meta,
        "messages": messages
    }

@router.patch("/sessions/{session_id}")
async def rename_session_endpoint(
    request: RenameSessionRequest,
    session_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    user_id = int(current_user.id)
    ok = await prompt_chat_service.rename_session(session_id=session_id, user_id=user_id, title=request.title)
    if not ok:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")
    meta = await prompt_chat_service.get_session_meta(session_id, user_id)
    return meta or {"session_id": session_id, "title": request.title.strip()}

@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(
    session_id: int = Path(..., ge=1),
    delete_prompt: bool = Query(True, description="是否同步删除关联的提示词"),
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    """
    删除会话
    
    默认会同步删除关联的提示词（通过 origin_prompt_id 关联）
    如果 delete_prompt=false，则只删除会话，保留提示词
    """
    user_id = int(current_user.id)
    
    # 1. 获取会话信息，检查是否存在及是否有 origin_prompt_id
    session_meta = await prompt_chat_service.get_session_meta(session_id, user_id)
    if not session_meta:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")
    
    origin_prompt_id = session_meta.get("origin_prompt_id")
    
    # 2. 删除会话
    ok = await prompt_chat_service.delete_session(session_id=session_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")
    
    # 3. 如果有关联的提示词且需要删除
    deleted_prompt = False
    if delete_prompt and origin_prompt_id:
        from sqlalchemy.ext.asyncio import AsyncSession
        from utils.lyf.prompt_chat_async import engine
        from sqlalchemy import text
        
        async with AsyncSession(engine) as db_session:
            # 软删除提示词
            result = await db_session.execute(
                text("""
                    UPDATE ai_prompts
                    SET status = 0, update_time = NOW()
                    WHERE id = :prompt_id AND user_id = :user_id
                """),
                {"prompt_id": origin_prompt_id, "user_id": user_id}
            )
            await db_session.commit()
            deleted_prompt = (result.rowcount or 0) > 0
            if deleted_prompt:
                logger.info(f"[delete_session_endpoint] Deleted associated prompt {origin_prompt_id} for session {session_id}")
    
    return {
        "ok": True, 
        "session_id": session_id,
        "deleted_prompt": deleted_prompt,
        "prompt_id": origin_prompt_id if delete_prompt else None
    }

@router.post("/sessions/{session_id}/fork")
async def fork_session_endpoint(
    request: ForkSessionRequest,
    session_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    user_id = int(current_user.id)
    try:
        return await prompt_chat_service.fork_session(
            session_id=session_id,
            user_id=user_id,
            upto_message_id=int(request.upto_message_id),
            title=request.title,
        )
    except ValueError as e:
        code = str(e)
        if code == "session_not_found":
            raise HTTPException(status_code=404, detail="session 不存在或无权限")
        if code == "message_not_found":
            raise HTTPException(status_code=404, detail="message 不存在")
        if code == "message_not_user":
            raise HTTPException(status_code=400, detail="只能从用户消息开始重发")
        raise

@router.post("/sessions/{session_id}/messages/{message_id}/regenerate/stream")
async def regenerate_message_endpoint(
    request: RegenerateRequest,
    session_id: int = Path(..., ge=1),
    message_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
):
    user_id = int(current_user.id)
    query = _normalize_query(request.query)
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    meta = await prompt_chat_service.get_session_meta(int(session_id), int(user_id))
    if not meta:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")

    async def event_generator():
        try:
            async for chunk in prompt_chat_service.regenerate_stream(
                session_id=int(session_id),
                user_id=user_id,
                user_message_id=int(message_id),
                query=query,
            ):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            code = str(e)
            detail = "regenerate_failed"
            if code == "message_not_found":
                detail = "message_not_found"
            elif code == "message_not_user":
                detail = "message_not_user"
            elif code == "empty_query":
                detail = "empty_query"
            elif code == "session_not_found":
                detail = "session_not_found"
            yield f"data: {json.dumps({'content': f'[Error: {detail}]'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.warning(f"[regenerate_message_endpoint] Client disconnected or error: {e}")
            # Client disconnected, stream will be closed automatically

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)

@router.post("/sessions/{session_id}/messages/{message_id}/optimize-inplace/stream")
async def optimize_inplace_endpoint(
    session_id: int = Path(..., ge=1),
    message_id: int = Path(..., ge=1),
    current_user: dict = Depends(require_user),
):
    """
    针对指定的 AI 消息，直接在原记录上进行“优化重写”，并在生成完成后更新 ai_chat_messages 的 content
    """
    user_id = int(current_user.id)
    meta = await prompt_chat_service.get_session_meta(int(session_id), int(user_id))
    if not meta:
        raise HTTPException(status_code=404, detail="session 不存在或无权限")

    async def event_generator():
        try:
            async for chunk in prompt_chat_service.optimize_inplace_stream(
                session_id=int(session_id),
                user_id=user_id,
                target_message_id=int(message_id),
            ):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            code = str(e)
            detail = "optimize_failed"
            if code == "message_not_found":
                detail = "message_not_found"
            elif code == "message_not_assistant":
                detail = "message_not_assistant"
            elif code == "session_not_found":
                detail = "session_not_found"
            yield f"data: {json.dumps({'content': f'[Error: {detail}]'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.warning(f"[optimize_inplace_endpoint] Client disconnected or error: {e}")

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=STREAM_HEADERS)
