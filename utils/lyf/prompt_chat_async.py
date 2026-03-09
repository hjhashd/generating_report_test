import asyncio
import json
import logging
import re
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional, Tuple

from .db_async_config import engine, Config
from .chat_message_record import ChatMessageRecord
from .context_manager import ContextManager

logger = logging.getLogger(__name__)

class PromptChat:
    def __init__(self):
        # 初始化两个模型的客户端
        self.main_client = AsyncOpenAI(api_key=Config.MAIN_API_KEY, base_url=Config.MAIN_LLM_URL)
        self.local_client = AsyncOpenAI(api_key=Config.LOCAL_API_KEY, base_url=Config.LOCAL_LLM_URL)
        
        self.recorder = ChatMessageRecord()
        self.context_mgr = ContextManager(self.main_client)
        self.semaphore = asyncio.Semaphore(Config.MAX_CONCURRENCY)
        self._column_cache: Dict[Tuple[str, str], bool] = {}

    async def _column_exists(self, table_name: str, column_name: str) -> bool:
        cache_key = (table_name, column_name)
        cached = self._column_cache.get(cache_key)
        if cached is not None:
            return cached

        async with AsyncSession(engine) as session:
            try:
                res = await session.execute(
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
                self._column_cache[cache_key] = exists
                return exists
            except Exception as e:
                logger.warning("Column check failed for %s.%s: %s", table_name, column_name, e)
                self._column_cache[cache_key] = False
                return False

    # 状态映射常量
    STATUS_MAP = {
        "active": 0,
        "completed": 1,
        "archived": 2,
        "deleted": -1
    }

    async def create_session(self, user_id: int, title: str = "新对话", ref_prompt_id: Optional[int] = None):
        """创建新会话并返回 session_id"""
        has_ref_prompt_id = False
        if ref_prompt_id is not None:
            has_ref_prompt_id = await self._column_exists("ai_chat_sessions", "ref_prompt_id")

        if has_ref_prompt_id:
            insert_sql = "INSERT INTO ai_chat_sessions (user_id, title, status, ref_prompt_id) VALUES (:uid, :title, :status, :ref_prompt_id)"
            insert_params = {
                "uid": user_id,
                "title": title,
                "status": self.STATUS_MAP["active"],
                "ref_prompt_id": int(ref_prompt_id),
            }
        else:
            insert_sql = "INSERT INTO ai_chat_sessions (user_id, title, status) VALUES (:uid, :title, :status)"
            insert_params = {"uid": user_id, "title": title, "status": self.STATUS_MAP["active"]}

        async with AsyncSession(engine) as session:
            try:
                await session.execute(
                    text(insert_sql),
                    insert_params,
                )
            except Exception:
                await session.rollback()
                await session.execute(
                    text(insert_sql),
                    insert_params,
                )

            sid_res = await session.execute(text("SELECT LAST_INSERT_ID()"))
            session_id = int(sid_res.scalar() or 0)

            await session.execute(
                text(
                    "INSERT IGNORE INTO ai_chat_context_state (session_id, window_start_round) VALUES (:sid, 1)"
                ),
                {"sid": session_id},
            )

            # 简化：不再插入 __PROMPT_REF__ 标记消息，引用内容通过上下文注入给模型即可
            # 保留 ref_prompt_id 在会话元数据中用于溯源
            await session.commit()
            return session_id

    async def get_session_meta(self, session_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        has_origin_prompt_id = await self._column_exists("ai_chat_sessions", "origin_prompt_id")
        has_ref_prompt_id = await self._column_exists("ai_chat_sessions", "ref_prompt_id")
        has_final_content = await self._column_exists("ai_chat_sessions", "final_content")
        has_status = await self._column_exists("ai_chat_sessions", "status")

        select_cols = ["id AS session_id", "user_id", "title"]
        if has_origin_prompt_id:
            select_cols.append("origin_prompt_id")
        if has_ref_prompt_id:
            select_cols.append("ref_prompt_id")
        if has_final_content:
            select_cols.append("final_content")
        if has_status:
            select_cols.append("status")

        async with AsyncSession(engine) as session:
            res = await session.execute(
                text(
                    """
                    SELECT {cols}
                    FROM ai_chat_sessions
                    WHERE id = :sid
                    """
                    .format(cols=", ".join(select_cols))
                ),
                {"sid": session_id},
            )
            row = res.mappings().fetchone()
            if not row:
                return None
            if int(row["user_id"]) != int(user_id):
                return None
            return dict(row)

    async def get_session_by_origin_prompt_id(self, user_id: int, prompt_id: int) -> Optional[Dict[str, Any]]:
        """
        根据 origin_prompt_id 查找用户的会话
        返回最新的一个匹配会话
        """
        has_origin_prompt_id = await self._column_exists("ai_chat_sessions", "origin_prompt_id")
        if not has_origin_prompt_id:
            return None

        has_update_time = await self._column_exists("ai_chat_sessions", "update_time")
        has_create_time = await self._column_exists("ai_chat_sessions", "create_time")
        has_status = await self._column_exists("ai_chat_sessions", "status")
        has_ref_prompt_id = await self._column_exists("ai_chat_sessions", "ref_prompt_id")

        select_cols = ["id AS session_id", "title", "origin_prompt_id"]
        if has_create_time:
            select_cols.append("create_time")
        if has_update_time:
            select_cols.append("update_time")
        if has_status:
            select_cols.append("status")
        if has_ref_prompt_id:
            select_cols.append("ref_prompt_id")

        order_col = "update_time" if has_update_time else "id"

        async with AsyncSession(engine) as session:
            res = await session.execute(
                text(
                    f"""
                    SELECT {", ".join(select_cols)}
                    FROM ai_chat_sessions
                    WHERE user_id = :uid AND origin_prompt_id = :prompt_id
                    ORDER BY {order_col} DESC
                    LIMIT 1
                    """
                ),
                {"uid": user_id, "prompt_id": prompt_id},
            )
            row = res.mappings().fetchone()
            return dict(row) if row else None

    async def list_sessions(self, user_id: int, limit: int = 50, status: Optional[str] = "active") -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        has_update_time = await self._column_exists("ai_chat_sessions", "update_time")
        has_create_time = await self._column_exists("ai_chat_sessions", "create_time")
        has_status = await self._column_exists("ai_chat_sessions", "status")
        has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
        has_origin_prompt_id = await self._column_exists("ai_chat_sessions", "origin_prompt_id")
        has_ref_prompt_id = await self._column_exists("ai_chat_sessions", "ref_prompt_id")

        select_cols = ["id AS session_id", "title"]
        if has_create_time:
            select_cols.append("create_time")
        if has_update_time:
            select_cols.append("update_time")
        if has_status:
            select_cols.append("status")
        if has_origin_prompt_id:
            select_cols.append("origin_prompt_id")
        if has_ref_prompt_id:
            select_cols.append("ref_prompt_id")

        where_sql = "WHERE user_id = :uid"
        params: Dict[str, Any] = {"uid": user_id, "limit": limit}

        if status and has_status:
            # 将字符串状态转换为数据库整数状态
            db_status = self.STATUS_MAP.get(status)
            # 如果映射失败但传了值，尝试直接转换（容错），或者忽略
            if db_status is None and str(status).isdigit():
                db_status = int(status)

            if db_status is not None:
                where_sql += " AND status = :status"
                params["status"] = db_status
                logger.info(f"[list_sessions] Filtering by status: {status} -> {db_status}")
            else:
                logger.warning(f"[list_sessions] Unknown status: {status}, returning all sessions")
        elif has_status:
            # 不传status时，返回所有非删除状态的会话
            where_sql += " AND status != :deleted_status"
            params["deleted_status"] = self.STATUS_MAP["deleted"]
            logger.info(f"[list_sessions] Returning all non-deleted sessions")

        order_col = "update_time" if has_update_time else "id"
        msg_deleted_clause = " AND (m.is_deleted IS NULL OR m.is_deleted = 0)" if has_is_deleted else ""
        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM ai_chat_sessions
            {where_sql}
              AND NOT (
                title LIKE '测试%%'
                AND NOT EXISTS (
                  SELECT 1 FROM ai_chat_messages m
                  WHERE m.session_id = ai_chat_sessions.id{msg_deleted_clause}
                )
              )
            ORDER BY {order_col} DESC
            LIMIT :limit
        """

        logger.info(f"[list_sessions] SQL: {sql}")
        logger.info(f"[list_sessions] Params: {params}")

        async with AsyncSession(engine) as session:
            res = await session.execute(text(sql), params)
            result = [dict(r) for r in res.mappings().all()]
            logger.info(f"[list_sessions] Found {len(result)} sessions for user {user_id}")
            for r in result:
                logger.info(f"[list_sessions] Session: id={r.get('session_id')}, title={r.get('title')}, status={r.get('status')}")
            return result

    async def rename_session(self, session_id: int, user_id: int, title: str) -> bool:
        title = (title or "").strip()
        if not title:
            return False

        async with AsyncSession(engine) as session:
            res = await session.execute(
                text(
                    """
                    UPDATE ai_chat_sessions
                    SET title = :title
                    WHERE id = :sid AND user_id = :uid
                    """
                ),
                {"title": title, "sid": session_id, "uid": user_id},
            )
            await session.commit()
            return (res.rowcount or 0) > 0

    async def delete_session(self, session_id: int, user_id: int) -> bool:
        has_status = await self._column_exists("ai_chat_sessions", "status")
        async with AsyncSession(engine) as session:
            if has_status:
                res = await session.execute(
                    text(
                        """
                        UPDATE ai_chat_sessions
                        SET status = :status
                        WHERE id = :sid AND user_id = :uid
                        """
                    ),
                    {"status": self.STATUS_MAP["deleted"], "sid": session_id, "uid": user_id},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

            res = await session.execute(
                text("SELECT id FROM ai_chat_sessions WHERE id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user_id},
            )
            if not res.scalar():
                return False

            await session.execute(text("DELETE FROM ai_chat_messages WHERE session_id = :sid"), {"sid": session_id})
            await session.execute(text("DELETE FROM ai_chat_context_state WHERE session_id = :sid"), {"sid": session_id})
            await session.execute(text("DELETE FROM ai_chat_sessions WHERE id = :sid"), {"sid": session_id})
            await session.commit()
            return True

    def _extract_content_from_prompt_ref(self, content: str) -> str:
        """从 __PROMPT_REF__ 标记中提取实际内容"""
        prefix = "__PROMPT_REF__"
        if not content.startswith(prefix):
            return content
        body = content[len(prefix):]
        newline_idx = body.find('\n')
        if newline_idx == -1:
            return ""
        return body[newline_idx + 1:]

    async def get_messages(self, session_id: int, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        meta = await self.get_session_meta(session_id, user_id)
        if not meta:
            return []

        has_create_time = await self._column_exists("ai_chat_messages", "create_time")
        has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
        select_cols = ["id", "role", "content"]
        if has_create_time:
            select_cols.append("create_time")

        where_clause = "WHERE session_id = :sid"
        if has_is_deleted:
            where_clause += " AND (is_deleted IS NULL OR is_deleted = 0)"

        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM ai_chat_messages
            {where_clause}
            ORDER BY id ASC
            LIMIT :limit
        """
        async with AsyncSession(engine) as session:
            res = await session.execute(text(sql), {"sid": session_id, "limit": limit})
            rows = [dict(r) for r in res.mappings().all()]
            # 处理 __PROMPT_REF__ 标记，返回纯内容
            for row in rows:
                if row.get("content"):
                    row["content"] = self._extract_content_from_prompt_ref(row["content"])
            return rows

    async def fork_session(self, session_id: int, user_id: int, upto_message_id: int, title: Optional[str] = None) -> Dict[str, Any]:
        meta = await self.get_session_meta(session_id, user_id)
        if not meta:
            raise ValueError("session_not_found")

        has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
        deleted_clause = " AND (is_deleted IS NULL OR is_deleted = 0)" if has_is_deleted else ""

        async with AsyncSession(engine) as session:
            target_res = await session.execute(
                text(
                    f"""
                    SELECT id, role, round_index
                    FROM ai_chat_messages
                    WHERE session_id = :sid AND id = :mid{deleted_clause}
                    """
                ),
                {"sid": session_id, "mid": int(upto_message_id)},
            )
            target = target_res.mappings().fetchone()
            if not target:
                raise ValueError("message_not_found")
            if str(target.get("role")) != "user":
                raise ValueError("message_not_user")

            target_round = int(target.get("round_index") or 0)
            history_res = await session.execute(
                text(
                    f"""
                    SELECT round_index, role, content
                    FROM ai_chat_messages
                    WHERE session_id = :sid 
                      AND (round_index < :target_round OR (round_index = :target_round AND id <= :mid))
                      {deleted_clause}
                    ORDER BY id ASC
                    """
                ),
                {"sid": session_id, "target_round": target_round, "mid": int(upto_message_id)},
            )
            history_rows = list(history_res.mappings().all())

            new_title = (title or meta.get("title") or "新对话").strip() or "新对话"
            await session.execute(
                text("INSERT INTO ai_chat_sessions (user_id, title, status) VALUES (:uid, :title, :status)"),
                {"uid": user_id, "title": new_title, "status": self.STATUS_MAP["active"]},
            )
            sid_res = await session.execute(text("SELECT LAST_INSERT_ID()"))
            new_session_id = int(sid_res.scalar() or 0)

            await session.execute(
                text("INSERT IGNORE INTO ai_chat_context_state (session_id, window_start_round) VALUES (:sid, 1)"),
                {"sid": new_session_id},
            )

            for row in history_rows:
                await session.execute(
                    text(
                        """
                        INSERT INTO ai_chat_messages (session_id, round_index, role, content)
                        VALUES (:sid, :idx, :role, :content)
                        """
                    ),
                    {
                        "sid": new_session_id,
                        "idx": int(row.get("round_index") or 0),
                        "role": row.get("role"),
                        "content": (row.get("content") or ""),
                    },
                )

            await session.commit()

        new_meta = await self.get_session_meta(new_session_id, user_id)
        return new_meta or {"session_id": new_session_id, "title": new_title}

    async def regenerate_stream(self, session_id: int, user_id: int, user_message_id: int, query: str):
        meta = await self.get_session_meta(session_id, user_id)
        if not meta:
            raise ValueError("session_not_found")

        query = (query or "").strip()
        if not query:
            raise ValueError("empty_query")

        has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
        has_deleted_at = await self._column_exists("ai_chat_messages", "deleted_at")

        async with AsyncSession(engine) as session:
            await session.execute(
                text("INSERT IGNORE INTO ai_chat_context_state (session_id, window_start_round) VALUES (:sid, 1)"),
                {"sid": session_id},
            )

            deleted_clause = " AND (is_deleted IS NULL OR is_deleted = 0)" if has_is_deleted else ""
            target_res = await session.execute(
                text(
                    f"""
                    SELECT id, role, round_index
                    FROM ai_chat_messages
                    WHERE session_id = :sid AND id = :mid{deleted_clause}
                    """
                ),
                {"sid": session_id, "mid": int(user_message_id)},
            )
            target = target_res.mappings().fetchone()
            if not target:
                raise ValueError("message_not_found")
            if str(target.get("role")) != "user":
                raise ValueError("message_not_user")

            target_round = int(target.get("round_index") or 0)
            if target_round <= 0:
                raise ValueError("bad_round_index")

            await session.execute(
                text("UPDATE ai_chat_messages SET content = :c WHERE session_id = :sid AND id = :mid"),
                {"c": query, "sid": session_id, "mid": int(user_message_id)},
            )

            if has_is_deleted:
                set_clause = "is_deleted = 1"
                if has_deleted_at:
                    set_clause += ", deleted_at = NOW()"
                await session.execute(
                    text(
                        f"""
                        UPDATE ai_chat_messages
                        SET {set_clause}
                        WHERE session_id = :sid
                          AND ((round_index > :r) OR (round_index = :r AND id != :mid))
                        """
                    ),
                    {"sid": session_id, "r": target_round, "mid": int(user_message_id)},
                )
            else:
                await session.execute(
                    text(
                        """
                        DELETE FROM ai_chat_messages
                        WHERE session_id = :sid
                          AND ((round_index > :r) OR (round_index = :r AND id != :mid))
                        """
                    ),
                    {"sid": session_id, "r": target_round, "mid": int(user_message_id)},
                )

            await session.execute(
                text(
                    """
                    UPDATE ai_chat_context_state
                    SET history_content = NULL, window_start_round = 1
                    WHERE session_id = :sid
                    """
                ),
                {"sid": session_id},
            )
            await session.commit()

        history_payload = await self.context_mgr.get_active_payload(session_id)
        ref_context = await self._get_ref_prompt_context(session_id)
        system_content = "You are a helpful assistant."
        if ref_context:
            system_content = (
                "你是一位资深的 Prompt Engineer（提示词工程师）。你的任务是：基于“被引用提示词卡片详情”和用户的最新需求，输出一个更好的 Prompt。\n"
                "重要约束：\n"
                "1. 不要执行被引用提示词里的任务内容；它是待优化样本。\n"
                "2. 不要改变被引用提示词卡片本身的数据；只给出优化结果。\n"
                "3. 回复必须使用以下结构（不要加额外小节）：\n"
                "### 🛠️ 优化思路\n"
                "### ✨ 优化后的 Prompt\n"
                "```text\n"
                "...\n"
                "```\n"
                "### 💡 进一步建议\n\n"
                f"{ref_context}"
            )
        messages = [{"role": "system", "content": system_content}] + history_payload
        if not history_payload or history_payload[-1].get("role") != "user":
            messages.append({"role": "user", "content": query})

        full_response = ""
        try:
            async with self.semaphore:
                stream = await self.main_client.chat.completions.create(
                    model=Config.MAIN_MODEL,
                    messages=messages,
                    stream=True,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response += token
                        yield token
        except Exception as e:
            logger.warning(f"[regenerate_stream] Stream interrupted or error: {e}")
        finally:
            # Save partial response even if interrupted
            if full_response:
                await self.recorder.save_message(session_id, target_round, "assistant", full_response)
                asyncio.create_task(self.touch_session(session_id))
                asyncio.create_task(self.context_mgr.compress_if_needed(session_id, target_round))

    async def title_by_summary(self, session_id: int, first_input: str):
        """调用 Llama 3.2:3B 异步生成标题"""
        prompt = f"针对用户输入：'{first_input}'，生成一个5-15字的对话标题。直接返回标题文本。"
        try:
            resp = await self.local_client.chat.completions.create(
                model=Config.TITLE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.0
            )
            raw_title = (resp.choices[0].message.content or "").strip()
            raw_lower = raw_title.lower()
            if ("<think" in raw_lower and "</think>" not in raw_lower) or ("<analysis" in raw_lower and "</analysis>" not in raw_lower) or ("<reasoning" in raw_lower and "</reasoning>" not in raw_lower):
                raw_title = ""
            title = re.sub(
                r"<(?:think|analysis|reasoning)[^>]*>.*?</(?:think|analysis|reasoning)>",
                "",
                raw_title,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
            title = re.sub(r"</?\s*(?:think|analysis|reasoning)\s*>", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"^(?:标题|title)\s*[:：]\s*", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\s+", " ", title).strip().strip('"').strip("'").strip()

            if re.search(r"(我现在|需要|任务|输出|下面|要求)", title) or title.startswith(("嗯", "好，", "好,", "好的", "Okay", "OK")):
                title = ""
            if not title or "<think" in title.lower() or title.startswith("<"):
                candidate = (first_input or "").strip().split("\n", 1)[0].strip()
                candidate = re.sub(r"^(?:User|用户)\s*[:：]?\s*", "", candidate, flags=re.IGNORECASE).strip()
                parts = re.split(r"[。！？!?]", candidate, maxsplit=1)
                title = ((parts[0] if parts else candidate).strip() or "新对话")[:15].strip() or "新对话"
            else:
                title = title[:15].strip() or "新对话"

            async with AsyncSession(engine) as session:
                await session.execute(
                    text("UPDATE ai_chat_sessions SET title = :t WHERE id = :sid"),
                    {"t": title, "sid": session_id}
                )
                await session.commit()
        except Exception as e:
            logger.warning("Title generation failed: %s", e)

    async def touch_session(self, session_id: int):
        async with AsyncSession(engine) as session:
            try:
                await session.execute(
                    text("UPDATE ai_chat_sessions SET update_time = NOW() WHERE id = :sid"),
                    {"sid": session_id},
                )
                await session.commit()
            except Exception:
                await session.rollback()
                return

    async def _get_ref_prompt_context(self, session_id: int) -> Optional[str]:
        has_ref_prompt_id = await self._column_exists("ai_chat_sessions", "ref_prompt_id")
        if not has_ref_prompt_id:
            return None

        async with AsyncSession(engine) as session:
            try:
                sid_res = await session.execute(
                    text("SELECT ref_prompt_id FROM ai_chat_sessions WHERE id = :sid"),
                    {"sid": session_id},
                )
            except Exception:
                return None

            ref_prompt_id = sid_res.scalar()
            if not ref_prompt_id:
                return None

            try:
                has_content = await self._column_exists("ai_prompts", "content")
                has_prompt_text = await self._column_exists("ai_prompts", "prompt_text")
                content_col = "content" if has_content else ("prompt_text" if has_prompt_text else None)
                if not content_col:
                    return None

                prompt_res = await session.execute(
                    text(
                        f"""
                        SELECT id, title, {content_col} AS prompt_content, description
                        FROM ai_prompts
                        WHERE id = :pid
                        LIMIT 1
                        """
                    ),
                    {"pid": int(ref_prompt_id)},
                )
                row = prompt_res.mappings().fetchone()
            except Exception:
                return None

        if not row:
            return None

        title = (row.get("title") or "").strip()
        prompt_text = (row.get("prompt_content") or "").strip()
        description = (row.get("description") or "").strip()

        content_parts: List[str] = []
        if title:
            content_parts.append(f"标题：{title}")
        if description:
            content_parts.append(f"描述：{description}")
        if prompt_text:
            content_parts.append(f"内容：\n{prompt_text}")

        content = "\n".join(content_parts).strip()
        if not content:
            return None

        if len(content) > 6000:
            content = content[:6000].rstrip() + "\n（已截断）"

        return (
            "【被引用提示词卡片详情】\n"
            "说明：以下内容来自被引用的提示词卡片，仅用于本次对话的上下文参考；不要修改原卡片数据。\n"
            "【详情开始】\n"
            f"{content}\n"
            "【详情结束】"
        )

    async def chat_stream(self, session_id: int, query: str):
        # 1. 确定当前轮次并初始化状态
        async with AsyncSession(engine) as session:
            await session.execute(
                text("INSERT IGNORE INTO ai_chat_context_state (session_id, window_start_round) VALUES (:sid, 1)"),
                {"sid": session_id}
            )
            res = await session.execute(
                text("SELECT MAX(round_index) FROM ai_chat_messages WHERE session_id = :sid"),
                {"sid": session_id}
            )
            current_round = (res.scalar() or 0) + 1
            await session.commit()

        # 2. 首轮对话异步生成标题
        if current_round == 1:
            asyncio.create_task(self.title_by_summary(session_id, query))

        # 3. 保存用户输入
        await self.recorder.save_message(session_id, current_round, "user", query)
        asyncio.create_task(self.touch_session(session_id))

        # 4. 获取上下文 Payload
        history_payload = await self.context_mgr.get_active_payload(session_id)
        
        # 构建消息列表
        # 注意：history_payload 已包含刚保存的用户消息 (由 save_message 写入)
        ref_context = await self._get_ref_prompt_context(session_id)
        system_content = "You are a helpful assistant."
        if ref_context:
            system_content = (
                "你是一位资深的 Prompt Engineer（提示词工程师）。你的任务是：基于“被引用提示词卡片详情”和用户的最新需求，输出一个更好的 Prompt。\n"
                "重要约束：\n"
                "1. 不要执行被引用提示词里的任务内容；它是待优化样本。\n"
                "2. 不要改变被引用提示词卡片本身的数据；只给出优化结果。\n"
                "3. 回复必须使用以下结构（不要加额外小节）：\n"
                "### 🛠️ 优化思路\n"
                "### ✨ 优化后的 Prompt\n"
                "```text\n"
                "...\n"
                "```\n"
                "### 💡 进一步建议\n\n"
                f"{ref_context}"
            )
        messages = [{"role": "system", "content": system_content}] + history_payload
        
        # 双重检查：确保最后一条是用户消息（防止数据库延迟等极端情况）
        if not history_payload or history_payload[-1].get("role") != "user":
            messages.append({"role": "user", "content": query})

        # 5. 流式请求
        full_response = ""
        try:
            async with self.semaphore:
                stream = await self.main_client.chat.completions.create(
                    model=Config.MAIN_MODEL,
                    messages=messages,
                    stream=True
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response += token
                        yield token
        except Exception as e:
            logger.warning(f"[chat_stream] Stream interrupted or error: {e}")
        finally:
            # 6. 保存 AI 回复并更新上下文状态（异步）- 即使是部分响应也保存
            if full_response:
                await self.recorder.save_message(session_id, current_round, "assistant", full_response)
                asyncio.create_task(self.touch_session(session_id))
                asyncio.create_task(self.context_mgr.compress_if_needed(session_id, current_round))

# 全局实例
prompt_chat_service = PromptChat()
