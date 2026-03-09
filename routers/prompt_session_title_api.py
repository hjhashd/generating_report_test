import logging
from typing import Any, Dict
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Path, Body
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 导入基础配置和引擎
from utils.lyf.db_async_config import engine, Config
# 导入你的权限校验依赖
from routers.dependencies import require_user
# 导入你刚刚拆分出来的标题生成服务类
from utils.lyf.prompt_session_title import SessionTitleGenerator

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化服务实例 (单例模式)
title_generator_service = SessionTitleGenerator()

# --- Pydantic Models ---
class GenerateTitleRequest(BaseModel):
    # 允许前端手动传一段文本让 AI 总结，或者传空（如果传空，后续逻辑可以扩展为查库）
    context_text: str 

# --- Helper Functions ---
async def _verify_session_owner(session_id: int, user_id: int) -> bool:
    """
    辅助函数：校验 session 是否属于当前用户
    防止 User A 修改 User B 的会话标题
    """
    async with AsyncSession(engine) as session:
        # 假设你的 ai_chat_sessions 表里有 user_id 字段
        res = await session.execute(
            text("SELECT 1 FROM ai_chat_sessions WHERE id = :sid AND user_id = :uid LIMIT 1"),
            {"sid": session_id, "uid": user_id}
        )
        return res.scalar() is not None

async def _get_current_title(session_id: int) -> str:
    """辅助函数：获取当前标题"""
    async with AsyncSession(engine) as session:
        res = await session.execute(
            text("SELECT title FROM ai_chat_sessions WHERE id = :sid"),
            {"sid": session_id}
        )
        return res.scalar() or ""

# --- Endpoints ---

@router.post("/sessions/{session_id}/auto-title")
async def generate_session_title_endpoint(
    request: GenerateTitleRequest,
    session_id: int = Path(..., ge=1, description="会话ID"),
    current_user: dict = Depends(require_user),
) -> Dict[str, Any]:
    """
    【手动触发】调用本地小模型为指定会话生成标题。
    通常用于：
    1. 前端觉得标题不准，用户点击“重新生成标题”按钮。
    2. 首轮对话因网络原因生成失败，前端重试。
    """
    user_id = int(current_user.id)
    
    # 1. 安全校验：确认会话属于当前用户
    is_owner = await _verify_session_owner(session_id, user_id)
    if not is_owner:
        logger.warning(f"⚠️ [Title] Access denied. User {user_id} tried to update Session {session_id}")
        raise HTTPException(status_code=404, detail="session 不存在或无权限")

    # 2. 参数校验
    context_text = (request.context_text or "").strip()
    if not context_text:
         raise HTTPException(status_code=400, detail="context_text 不能为空，请提供用于总结的对话内容")

    logger.info(f"🤖 [Title] User {user_id} manually triggering title generation for Session {session_id}")

    # 3. 调用业务服务 (异步生成并更新 DB)
    # 注意：generate_and_update 内部捕获了异常，所以这里一般不会崩，但为了接口友好，我们最好能确认是否更新成功
    await title_generator_service.generate_and_update(session_id, context_text)

    # 4. 获取更新后的标题并返回
    # 因为 generate_and_update 是直接改库的，我们需要查一次库返回给前端最新状态
    new_title = await _get_current_title(session_id)

    return {
        "ok": True,
        "session_id": session_id,
        "new_title": new_title
    }