"""
用户个人中心路由
包含用户统计、活动记录、提示词列表等功能
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from routers.dependencies import require_user, CurrentUser
from routers.prompt_service import PromptUserService
from utils.lyf.db_async_config import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Prompt-User"])


@router.get("/user/stats", response_model=dict)
async def get_user_stats(
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取用户统计数据
    
    包括：总提示词数、收藏数、获赞总数、分享次数等
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        service = PromptUserService(session)
        stats = await service.get_user_stats(user_id)
        
        return {
            "code": 0,
            "message": "success",
            "data": stats
        }


@router.get("/user/activities", response_model=dict)
async def get_user_activities(
    limit: int = Query(10, ge=1, le=50, description="返回条数限制"),
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取用户最近活动记录
    
    基于用户交互记录(ai_user_interactions)和提示词创建记录生成活动流
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        service = PromptUserService(session)
        activities = await service.get_user_activities(user_id, limit)
        
        return {
            "code": 0,
            "message": "success",
            "data": activities
        }


@router.get("/user/prompts", response_model=dict)
async def get_user_prompts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    status: Optional[int] = Query(None, description="状态筛选: 1-启用, 0-禁用"),
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取用户创建的提示词列表
    
    支持分页和状态筛选
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        service = PromptUserService(session)
        result = await service.get_user_prompts(user_id, page, page_size, status)
        
        return {
            "code": 0,
            "message": "success",
            "data": result
        }


@router.get("/sessions/{session_id}/save_info")
async def get_session_save_info(
    session_id: int,
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取会话的保存相关信息
    
    用于前端判断是否可以继续对话、是否已保存等
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, user_id, title, status, origin_prompt_id, final_content
                FROM ai_chat_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id}
        )
        session_meta = result.mappings().fetchone()
        
        if not session_meta:
            return {
                "code": 404,
                "message": "会话不存在",
                "data": None
            }
        
        if int(session_meta["user_id"]) != user_id:
            return {
                "code": 403,
                "message": "无权限访问此会话",
                "data": None
            }
        
        prompt_info = None
        if session_meta.get("origin_prompt_id"):
            result = await session.execute(
                text("""
                    SELECT id, title, content, user_id, department_id, status
                    FROM ai_prompts
                    WHERE id = :prompt_id
                """),
                {"prompt_id": session_meta["origin_prompt_id"]}
            )
            row = result.mappings().fetchone()
            if row:
                prompt_info = dict(row)
        
        result = await session.execute(
            text("""
                SELECT id, role, content, create_time
                FROM ai_chat_messages
                WHERE session_id = :session_id
                ORDER BY id DESC
                LIMIT 50
            """),
            {"session_id": session_id}
        )
        messages = [dict(row) for row in result.mappings().all()]
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "session": dict(session_meta),
                "prompt": prompt_info,
                "messages": messages,
                "can_continue_chat": session_meta.get("status") != 1 or session_meta.get("user_id") == user_id,
            }
        }


@router.get("/{prompt_id}/detail")
async def get_prompt_detail(
    prompt_id: int,
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取提示词详情
    
    权限控制：
    - 私有提示词：只有所有者可以查看
    - 公开提示词：所有人可以查看
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, uuid, title, content, description, user_input_example,
                       variables_json, model_config_json, user_id, user_name,
                       department_id, status, icon_code, view_count, like_count,
                       favorite_count, create_time, update_time
                FROM ai_prompts
                WHERE id = :prompt_id
            """),
            {"prompt_id": prompt_id}
        )
        row = result.mappings().fetchone()
        
        if not row:
            return {
                "code": 404,
                "message": "提示词不存在",
                "data": None
            }
        
        prompt = dict(row)
        
        if prompt["status"] == 1 and int(prompt["user_id"]) != user_id:
            return {
                "code": 403,
                "message": "无权查看此提示词",
                "data": None
            }
        
        result = await session.execute(
            text("""
                SELECT t.id, t.tag_name, t.type, t.icon_code, t.color
                FROM ai_prompt_tag_relation r
                JOIN ai_prompt_tags t ON r.tag_id = t.id
                WHERE r.prompt_id = :prompt_id
            """),
            {"prompt_id": prompt_id}
        )
        tags = [dict(row) for row in result.mappings().all()]
        prompt["tags"] = tags
        
        await session.execute(
            text("UPDATE ai_prompts SET view_count = view_count + 1 WHERE id = :prompt_id"),
            {"prompt_id": prompt_id}
        )
        await session.commit()
        
        return {
            "code": 0,
            "message": "success",
            "data": prompt
        }


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    delete_session: bool = Query(False, description="是否同步删除关联的会话记录"),
    current_user: CurrentUser = Depends(require_user),
):
    """
    删除提示词
    
    权限：只能删除自己创建的提示词
    实现：采用软删除，将status更新为0（禁用）
    可选：同步删除关联的会话记录（ai_chat_sessions表）
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, user_id, title
                FROM ai_prompts
                WHERE id = :prompt_id
            """),
            {"prompt_id": prompt_id}
        )
        prompt = result.mappings().fetchone()
        
        if not prompt:
            return {
                "code": 404,
                "message": "提示词不存在",
                "data": None
            }
        
        if int(prompt["user_id"]) != user_id:
            return {
                "code": 403,
                "message": "无权删除该提示词",
                "data": None
            }
        
        await session.execute(
            text("""
                UPDATE ai_prompts
                SET status = 0, update_time = NOW()
                WHERE id = :prompt_id
            """),
            {"prompt_id": prompt_id}
        )
        
        await session.execute(
            text("DELETE FROM ai_prompt_tag_relation WHERE prompt_id = :prompt_id"),
            {"prompt_id": prompt_id}
        )
        
        deleted_sessions = 0
        if delete_session:
            result = await session.execute(
                text("""
                    SELECT id FROM ai_chat_sessions
                    WHERE origin_prompt_id = :prompt_id AND user_id = :user_id
                """),
                {"prompt_id": prompt_id, "user_id": user_id}
            )
            session_ids = [row["id"] for row in result.mappings().all()]
            
            if session_ids:
                await session.execute(
                    text("""
                        DELETE FROM ai_chat_messages
                        WHERE session_id IN :session_ids
                    """),
                    {"session_ids": tuple(session_ids)}
                )
                
                result = await session.execute(
                    text("""
                        DELETE FROM ai_chat_sessions
                        WHERE id IN :session_ids
                    """),
                    {"session_ids": tuple(session_ids)}
                )
                deleted_sessions = result.rowcount
                
                logger.info(f"[PromptUser] Deleted {deleted_sessions} associated sessions for prompt {prompt_id}")
        
        await session.commit()
        
        logger.info(f"[PromptUser] Soft-deleted prompt {prompt_id} by user {user_id}, delete_session={delete_session}")

        return {
            "code": 0,
            "message": "删除成功",
            "data": {
                "prompt_id": prompt_id,
                "deleted_sessions": deleted_sessions
            }
        }


@router.get("/{prompt_id}/session")
async def get_prompt_session(
    prompt_id: int,
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取提示词关联的会话
    
    用于：点击提示词卡片时，找到对应的会话并跳转
    返回会话ID，如果没有关联的会话则返回空
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        # 先检查提示词是否存在且用户有权限查看
        result = await session.execute(
            text("""
                SELECT id, user_id, status
                FROM ai_prompts
                WHERE id = :prompt_id
            """),
            {"prompt_id": prompt_id}
        )
        prompt = result.mappings().fetchone()
        
        if not prompt:
            return {
                "code": 404,
                "message": "提示词不存在",
                "data": None
            }
        
        # 私有提示词只能由所有者查看
        if prompt["status"] == 1 and int(prompt["user_id"]) != user_id:
            return {
                "code": 403,
                "message": "无权查看此提示词",
                "data": None
            }
        
        # 查找关联的会话
        result = await session.execute(
            text("""
                SELECT id, title, status, create_time, update_time
                FROM ai_chat_sessions
                WHERE origin_prompt_id = :prompt_id AND user_id = :user_id
                ORDER BY update_time DESC
                LIMIT 1
            """),
            {"prompt_id": prompt_id, "user_id": user_id}
        )
        session_row = result.mappings().fetchone()
        
        if session_row:
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "session_id": session_row["id"],
                    "title": session_row["title"],
                    "status": session_row["status"],
                    "create_time": str(session_row["create_time"]) if session_row["create_time"] else None,
                    "update_time": str(session_row["update_time"]) if session_row["update_time"] else None,
                }
            }
        else:
            return {
                "code": 0,
                "message": "该提示词暂无关联的会话",
                "data": None
            }
