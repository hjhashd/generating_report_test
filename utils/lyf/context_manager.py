from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .db_async_config import engine, Config
from typing import Dict, Tuple

class ContextManager:
    def __init__(self, main_llm_client):
        self.client = main_llm_client
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
            except Exception:
                self._column_cache[cache_key] = False
                return False

    async def get_active_payload(self, session_id: int) -> list:
        """组装：长期摘要 + 窗口内消息"""
        async with AsyncSession(engine) as session:
            # 1. 获取当前上下文状态
            state_res = await session.execute(
                text("SELECT * FROM ai_chat_context_state WHERE session_id = :sid"),
                {"sid": session_id}
            )
            state = state_res.mappings().fetchone()
            if not state: return []

            messages = []
            # 2. 注入摘要（长期记忆）
            if state['history_content']:
                messages.append({"role": "system", "content": f"历史摘要：{state['history_content']}"})

            # 3. 注入窗口内消息（短期记忆）
            has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
            msg_res = await session.execute(
                text(
                    """
                    SELECT role, content
                    FROM ai_chat_messages
                    WHERE session_id = :sid
                      AND round_index >= :start
                      AND (:has_is_deleted = 0 OR is_deleted IS NULL OR is_deleted = 0)
                    ORDER BY id ASC
                    """
                ),
                {"sid": session_id, "start": state['window_start_round'], "has_is_deleted": 1 if has_is_deleted else 0},
            )
            for row in msg_res.mappings():
                content = row["content"]
                if isinstance(content, str) and content.startswith("__PROMPT_REF__"):
                    body = content[len("__PROMPT_REF__") :]
                    nl = body.find("\n")
                    content = "" if nl == -1 else body[nl:].lstrip("\n")
                messages.append({"role": row["role"], "content": content})
            
            return messages

    async def compress_if_needed(self, session_id: int, current_round: int):
        """异步触发：如果轮次过多，则压缩前半部分"""
        async with AsyncSession(engine) as session:
            state_res = await session.execute(
                text("SELECT * FROM ai_chat_context_state WHERE session_id = :sid"),
                {"sid": session_id}
            )
            state = state_res.mappings().fetchone()
            
            # 逻辑：如果(当前轮次 - 窗口起始轮次) > 阈值
            if current_round - state['window_start_round'] >= Config.SUMMARY_THRESHOLD:
                # 设定压缩终点（例如保留最近的 WINDOW_SIZE 轮）
                compress_end = current_round - Config.WINDOW_SIZE
                
                # 获取待压缩内容
                has_is_deleted = await self._column_exists("ai_chat_messages", "is_deleted")
                rows = await session.execute(
                    text(
                        """
                        SELECT role, content
                        FROM ai_chat_messages
                        WHERE session_id = :sid
                          AND round_index <= :end
                          AND (:has_is_deleted = 0 OR is_deleted IS NULL OR is_deleted = 0)
                        ORDER BY id ASC
                        """
                    ),
                    {"sid": session_id, "end": compress_end, "has_is_deleted": 1 if has_is_deleted else 0},
                )
                parts = []
                for r in rows.mappings():
                    content = r["content"]
                    if isinstance(content, str) and content.startswith("__PROMPT_REF__"):
                        body = content[len("__PROMPT_REF__") :]
                        nl = body.find("\n")
                        content = "" if nl == -1 else body[nl:].lstrip("\n")
                    parts.append(f"{r['role']}: {content}")
                text_to_sum = "\n".join(parts)
                
                # 调用 LLM 生成新摘要
                new_summary = await self._generate_summary(state['history_content'], text_to_sum)
                
                # 更新状态：滑动窗口起点后移，摘要更新
                await session.execute(
                    text("""
                        UPDATE ai_chat_context_state 
                        SET history_content = :hc, window_start_round = :wsr 
                        WHERE session_id = :sid
                    """),
                    {"hc": new_summary, "wsr": compress_end + 1, "sid": session_id}
                )
                await session.commit()

    async def _generate_summary(self, old_sum, new_text):
        prompt = f"请整合对话摘要。旧摘要：{old_sum}\n新对话：{new_text}\n要求：保持连贯性，500字内。"
        resp = await self.client.chat.completions.create(
            model=Config.MAIN_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content.strip()
