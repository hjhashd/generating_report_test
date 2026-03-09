"""
Prompt 服务类
包含提示词保存、标签管理、用户统计等核心业务逻辑
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from routers.dependencies import CurrentUser
from routers.prompt_models import CreateTagRequest, SavePromptRequest

logger = logging.getLogger(__name__)


def format_time_ago(dt) -> str:
    """格式化时间为'xx前'格式"""
    if not dt:
        return "未知时间"
    
    now = datetime.now(dt.timezone.utc if dt.tzinfo else None)
    diff = now - dt
    
    seconds = int(diff.total_seconds())
    
    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}分钟前"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}小时前"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days}天前"
    elif seconds < 2592000:
        weeks = seconds // 604800
        return f"{weeks}周前"
    elif seconds < 31536000:
        months = seconds // 2592000
        return f"{months}个月前"
    else:
        years = seconds // 31536000
        return f"{years}年前"


class PromptSaveService:
    """提示词保存服务"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._column_cache: Dict[str, bool] = {}

    async def _column_exists(self, table_name: str, column_name: str) -> bool:
        key = f"{table_name}.{column_name}"
        cached = self._column_cache.get(key)
        if cached is not None:
            return cached
        try:
            res = await self.session.execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :t
                      AND COLUMN_NAME = :c
                    """
                ),
                {"t": table_name, "c": column_name},
            )
            exists = (res.scalar() or 0) > 0
            self._column_cache[key] = exists
            return exists
        except Exception:
            self._column_cache[key] = False
            return False
    
    async def get_session_meta(self, session_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """获取会话元数据并验证权限"""
        result = await self.session.execute(
            text("""
                SELECT id, user_id, title, status, origin_prompt_id, final_content
                FROM ai_chat_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id}
        )
        row = result.mappings().fetchone()
        if not row:
            return None
        if int(row["user_id"]) != int(user_id):
            return None
        return dict(row)
    
    async def get_message_content(self, message_id: int, session_id: int) -> Optional[str]:
        """获取指定消息的内容"""
        result = await self.session.execute(
            text("""
                SELECT content, role
                FROM ai_chat_messages
                WHERE id = :message_id AND session_id = :session_id
            """),
            {"message_id": message_id, "session_id": session_id}
        )
        row = result.mappings().fetchone()
        if not row:
            return None
        if row["role"] not in ["assistant", "ai"]:
            raise HTTPException(status_code=400, detail="只能保存AI回复消息")
        return row["content"]
    
    async def get_prompt_by_id(self, prompt_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """获取提示词并验证所有权"""
        has_origin_prompt_id = await self._column_exists("ai_prompts", "origin_prompt_id")
        has_parent_prompt_id = await self._column_exists("ai_prompts", "parent_prompt_id")
        select_cols = ["id", "user_id", "title", "content", "uuid"]
        if has_origin_prompt_id:
            select_cols.append("origin_prompt_id")
        if has_parent_prompt_id:
            select_cols.append("parent_prompt_id")
        result = await self.session.execute(
            text(
                f"""
                SELECT {", ".join(select_cols)}
                FROM ai_prompts
                WHERE id = :prompt_id
                """
            ),
            {"prompt_id": prompt_id}
        )
        row = result.mappings().fetchone()
        if not row:
            return None
        if int(row["user_id"]) != int(user_id):
            return None
        return dict(row)
    
    async def create_or_update_prompt(
        self,
        user: CurrentUser,
        request: SavePromptRequest,
        content: str
    ) -> int:
        """创建或更新提示词，返回prompt_id"""
        
        user_id = int(user.id)
        user_name = user.username
        
        department_id = None
        status = 1
        is_template = 0
        
        if request.visibility == "plaza":
            if not request.department_id:
                raise HTTPException(status_code=400, detail="公开提示词必须选择部门")
            department_id = request.department_id
            status = 2
        
        session_meta = await self.get_session_meta(request.session_id, user_id)
        # 注意：session_meta["origin_prompt_id"] 是会话关联的提示词ID
        # 而 ai_prompts.origin_prompt_id 是提示词的原始模板ID(溯源)
        # 两者含义不同，不要混淆

        origin_prompt_id = None
        if request.prompt_id:
            existing = await self.get_prompt_by_id(request.prompt_id, user_id)
            if existing:
                await self.session.execute(
                    text("""
                        UPDATE ai_prompts
                        SET title = :title,
                            content = :content,
                            description = :description,
                            user_input_example = :user_input_example,
                            variables_json = :variables_json,
                            model_config_json = :model_config_json,
                            department_id = :department_id,
                            status = :status,
                            is_template = :is_template,
                            icon_code = :icon_code,
                            update_time = NOW()
                        WHERE id = :prompt_id
                    """),
                    {
                        "prompt_id": request.prompt_id,
                        "title": request.title,
                        "content": content,
                        "description": request.description,
                        "user_input_example": request.user_input_example,
                        "variables_json": request.variables_json,
                        "model_config_json": request.model_config_json,
                        "department_id": department_id,
                        "status": status,
                        "is_template": is_template,
                        "icon_code": request.icon_code,
                    }
                )
                prompt_id = request.prompt_id
                logger.info(f"[PromptSave] Updated prompt {prompt_id} by user {user_id}")
            else:
                origin_prompt_id = request.prompt_id
                logger.info(f"[PromptSave] Prompt {origin_prompt_id} not owned by user {user_id}, creating new prompt with origin_prompt_id")
        
        if not request.prompt_id or origin_prompt_id:
            new_uuid = str(uuid.uuid4()).replace("-", "")
            
            await self.session.execute(
                text("""
                    INSERT INTO ai_prompts (
                        uuid, title, content, description, user_input_example,
                        variables_json, model_config_json, user_id, user_name,
                        department_id, status, is_template, origin_prompt_id,
                        icon_code, create_time, update_time
                    ) VALUES (
                        :uuid, :title, :content, :description, :user_input_example,
                        :variables_json, :model_config_json, :user_id, :user_name,
                        :department_id, :status, :is_template, :origin_prompt_id,
                        :icon_code, NOW(), NOW()
                    )
                """),
                {
                    "uuid": new_uuid,
                    "title": request.title,
                    "content": content,
                    "description": request.description,
                    "user_input_example": request.user_input_example,
                    "variables_json": request.variables_json,
                    "model_config_json": request.model_config_json,
                    "user_id": user_id,
                    "user_name": user_name,
                    "department_id": department_id,
                    "status": status,
                    "is_template": is_template,
                    "origin_prompt_id": origin_prompt_id,
                    "icon_code": request.icon_code,
                }
            )
            
            result = await self.session.execute(text("SELECT LAST_INSERT_ID()"))
            prompt_id = int(result.scalar() or 0)
            logger.info(f"[PromptSave] Created new prompt {prompt_id} by user {user_id}")
        
        return prompt_id, origin_prompt_id is not None
    
    async def update_tag_relations(self, prompt_id: int, tag_ids: List[int], user_id: int):
        """更新提示词与标签的关联关系"""
        if not tag_ids:
            await self.session.execute(
                text("DELETE FROM ai_prompt_tag_relation WHERE prompt_id = :prompt_id"),
                {"prompt_id": prompt_id}
            )
            return
        
        if tag_ids:
            result = await self.session.execute(
                text("""
                    SELECT id, type, user_id
                    FROM ai_prompt_tags
                    WHERE id IN :tag_ids
                """),
                {"tag_ids": tuple(tag_ids)}
            )
            tags = result.mappings().all()
            
            for tag in tags:
                if tag["type"] == 2 and int(tag["user_id"]) != user_id:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"无权使用个人标签: {tag['id']}"
                    )
        
        await self.session.execute(
            text("DELETE FROM ai_prompt_tag_relation WHERE prompt_id = :prompt_id"),
            {"prompt_id": prompt_id}
        )
        
        for tag_id in set(tag_ids):
            await self.session.execute(
                text("""
                    INSERT INTO ai_prompt_tag_relation (prompt_id, tag_id)
                    VALUES (:prompt_id, :tag_id)
                """),
                {"prompt_id": prompt_id, "tag_id": tag_id}
            )
    
    async def update_directory_relation(self, prompt_id: int, directory_id: Optional[int]):
        """更新提示词与目录的关联关系"""
        await self.session.execute(
            text("DELETE FROM ai_prompt_directory_rel WHERE prompt_id = :prompt_id"),
            {"prompt_id": prompt_id}
        )
        
        if directory_id:
            await self.session.execute(
                text("""
                    INSERT INTO ai_prompt_directory_rel (directory_id, prompt_id)
                    VALUES (:directory_id, :prompt_id)
                """),
                {"directory_id": directory_id, "prompt_id": prompt_id}
            )
    
    async def finalize_session(
        self,
        session_id: int,
        user_id: int,
        prompt_id: int,
        final_content: str,
        message_id: Optional[int] = None,
        source_type: Optional[str] = None
    ):
        """收敛会话：将会话标记为已保存状态，并标记其他消息为已删除

        当 source_type='prompt'（当前编辑器）且没有 message_id 时，
        会创建一条新的助手消息来保存编辑器内容。
        """
        # 简化：不再合并 __PROMPT_REF__ 标记，直接保存最终内容
        combined_content = final_content

        if source_type == "prompt" and not message_id:
            result = await self.session.execute(
                text(
                    """
                    SELECT COALESCE(MAX(round_index), 0) as max_round
                    FROM ai_chat_messages
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            )
            row = result.mappings().fetchone()
            next_round = (row["max_round"] if row else 0) + 1

            result = await self.session.execute(
                text(
                    """
                    INSERT INTO ai_chat_messages (session_id, role, content, create_time, round_index)
                    VALUES (:session_id, 'assistant', :content, NOW(), :round_index)
                    """
                ),
                {
                    "session_id": session_id,
                    "content": combined_content,
                    "round_index": next_round,
                },
            )
            message_id = result.lastrowid
            logger.info(f"[PromptSave] Created assistant message {message_id} for prompt source in session {session_id}")
        elif source_type == "reply" and message_id:
            await self.session.execute(
                text(
                    """
                    UPDATE ai_chat_messages
                    SET content = :content
                    WHERE id = :message_id AND session_id = :session_id
                    """
                ),
                {"content": combined_content, "message_id": message_id, "session_id": session_id},
            )

        # 更新会话状态
        await self.session.execute(
            text("""
                UPDATE ai_chat_sessions
                SET status = 1,
                    origin_prompt_id = :prompt_id,
                    final_content = :final_content,
                    update_time = NOW()
                WHERE id = :session_id AND user_id = :user_id
            """),
            {
                "session_id": session_id,
                "user_id": user_id,
                "prompt_id": prompt_id,
                "final_content": final_content,
            }
        )

        # 如果有message_id，标记其他消息为已删除（保留选中的消息）
        if message_id:
            await self.session.execute(
                text("""
                    UPDATE ai_chat_messages
                    SET is_deleted = 1, deleted_at = NOW()
                    WHERE session_id = :session_id AND id != :message_id
                """),
                {"session_id": session_id, "message_id": message_id}
            )
            logger.info(f"[PromptSave] Marked other messages as deleted in session {session_id}, kept message {message_id}")

        logger.info(f"[PromptSave] Finalized session {session_id} with prompt {prompt_id}")
    
    async def create_personal_tag(
        self, 
        user_id: int, 
        request: CreateTagRequest
    ) -> int:
        """创建个人标签，返回tag_id"""
        result = await self.session.execute(
            text("""
                SELECT id FROM ai_prompt_tags
                WHERE tag_name = :tag_name AND user_id = :user_id AND type = 2
            """),
            {"tag_name": request.tag_name, "user_id": user_id}
        )
        existing = result.scalar()
        if existing:
            return int(existing)
        
        await self.session.execute(
            text("""
                INSERT INTO ai_prompt_tags (
                    tag_name, type, user_id, parent_id, icon_code, color
                ) VALUES (
                    :tag_name, 2, :user_id, :parent_id, :icon_code, :color
                )
            """),
            {
                "tag_name": request.tag_name,
                "user_id": user_id,
                "parent_id": request.parent_id,
                "icon_code": request.icon_code,
                "color": request.color,
            }
        )
        
        result = await self.session.execute(text("SELECT LAST_INSERT_ID()"))
        tag_id = int(result.scalar() or 0)
        logger.info(f"[PromptSave] Created personal tag {tag_id} for user {user_id}")
        return tag_id


class PromptUserService:
    """用户相关服务"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_user_stats(self, user_id: int) -> Dict[str, int]:
        """获取用户统计数据"""
        result = await self.session.execute(
            text("""
                SELECT 
                    COUNT(*) as total_prompts,
                    COALESCE(SUM(like_count), 0) as like_count,
                    COALESCE(SUM(favorite_count), 0) as favorite_count,
                    COALESCE(SUM(share_count), 0) as share_count,
                    COALESCE(SUM(view_count), 0) as view_count,
                    COALESCE(SUM(copy_count), 0) as copy_count
                FROM ai_prompts
                WHERE user_id = :user_id AND status != 0
            """),
            {"user_id": user_id}
        )
        row = result.mappings().fetchone()
        
        if not row:
            return {
                "total_prompts": 0,
                "favorite_count": 0,
                "like_count": 0,
                "share_count": 0,
                "view_count": 0,
                "copy_count": 0,
            }
        
        return {
            "total_prompts": int(row["total_prompts"] or 0),
            "favorite_count": int(row["favorite_count"] or 0),
            "like_count": int(row["like_count"] or 0),
            "share_count": int(row["share_count"] or 0),
            "view_count": int(row["view_count"] or 0),
            "copy_count": int(row["copy_count"] or 0),
        }
    
    async def get_user_activities(self, user_id: int, limit: int) -> List[Dict[str, Any]]:
        """获取用户活动记录"""
        activities = []
        
        result = await self.session.execute(
            text("""
                SELECT 
                    i.id,
                    i.target_id,
                    i.action_type,
                    i.create_time,
                    p.title
                FROM ai_user_interactions i
                LEFT JOIN ai_prompts p ON i.target_id = p.id
                WHERE i.user_id = :user_id AND i.target_type = 1
                ORDER BY i.create_time DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit}
        )
        interactions = result.mappings().all()
        
        action_map = {
            1: {"type": "like", "text": "点赞了提示词：", "icon": "ThumbsUp"},
            2: {"type": "favorite", "text": "收藏了提示词：", "icon": "Heart"},
            3: {"type": "share", "text": "分享了提示词：", "icon": "Share2"},
            4: {"type": "copy", "text": "复制了提示词：", "icon": "Copy"},
        }
        
        for interaction in interactions:
            action_info = action_map.get(interaction["action_type"], {"type": "unknown", "text": "操作了提示词：", "icon": "Activity"})
            activities.append({
                "id": int(interaction["id"]),
                "type": action_info["type"],
                "text": action_info["text"],
                "highlight": interaction["title"] or f"提示词#{interaction['target_id']}",
                "time": format_time_ago(interaction["create_time"]),
                "icon": action_info["icon"],
            })
        
        result = await self.session.execute(
            text("""
                SELECT id, title, create_time
                FROM ai_prompts
                WHERE user_id = :user_id AND status != 0
                ORDER BY create_time DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit}
        )
        created_prompts = result.mappings().all()
        
        for prompt in created_prompts:
            activities.append({
                "id": int(prompt["id"]) * -1,
                "type": "create",
                "text": "创建了新的提示词：",
                "highlight": prompt["title"],
                "time": format_time_ago(prompt["create_time"]),
                "icon": "Plus",
            })
        
        activities.sort(key=lambda x: x["time"], reverse=True)
        return activities[:limit]
    
    async def get_user_prompts(
        self, 
        user_id: int, 
        page: int, 
        page_size: int,
        status: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取用户提示词列表"""
        where_clause = "WHERE user_id = :user_id"
        params = {"user_id": user_id}
        
        if status is not None:
            where_clause += " AND status = :status"
            params["status"] = status
        else:
            where_clause += " AND status != 0"
        
        count_result = await self.session.execute(
            text(f"SELECT COUNT(*) as total FROM ai_prompts {where_clause}"),
            params
        )
        total = int(count_result.scalar() or 0)
        
        offset = (page - 1) * page_size
        params["offset"] = offset
        params["limit"] = page_size
        
        result = await self.session.execute(
            text(f"""
                SELECT 
                    id, title, like_count, favorite_count, copy_count,
                    view_count, create_time, update_time, status, is_template
                FROM ai_prompts
                {where_clause}
                ORDER BY create_time DESC
                LIMIT :limit OFFSET :offset
            """),
            params
        )
        prompts = []
        for row in result.mappings().all():
            prompts.append({
                "id": int(row["id"]),
                "title": row["title"],
                "like_count": int(row["like_count"] or 0),
                "favorite_count": int(row["favorite_count"] or 0),
                "copy_count": int(row["copy_count"] or 0),
                "view_count": int(row["view_count"] or 0),
                "create_time": row["create_time"].strftime("%Y-%m-%d %H:%M") if row["create_time"] else "",
                "update_time": row["update_time"].strftime("%Y-%m-%d %H:%M") if row["update_time"] else "",
                "status": int(row["status"]),
                "is_template": int(row["is_template"]),
            })
        
        return {
            "list": prompts,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
