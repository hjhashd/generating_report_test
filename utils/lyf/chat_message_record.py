import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .db_async_config import engine

class ChatMessageRecord:
    @staticmethod
    async def save_message(session_id: int, round_index: int, role: str, content: str):
        """清洗并持久化消息"""
        # 清除 DeepSeek 的思考过程标签
        clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        async with AsyncSession(engine) as session:
            sql = text("""
                INSERT INTO ai_chat_messages (session_id, round_index, role, content)
                VALUES (:sid, :idx, :role, :content)
            """)
            await session.execute(sql, {
                "sid": session_id, "idx": round_index, 
                "role": role, "content": clean_content
            })
            await session.commit()

    @staticmethod
    async def get_history_for_display(session_id: int):
        """用于前端加载历史对话"""
        async with AsyncSession(engine) as session:
            sql = text("""
                SELECT role, content, create_time 
                FROM ai_chat_messages 
                WHERE session_id = :sid 
                ORDER BY id ASC
            """)
            result = await session.execute(sql, {"sid": session_id})
            return [dict(row) for row in result.mappings().all()]
