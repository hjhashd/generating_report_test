import asyncio
import re
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .lyf.db_async_config import engine, Config

class SessionTitleGenerator:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=Config.LOCAL_API_KEY,
            base_url=Config.LOCAL_LLM_URL
        )

    def _fallback_title(self, text_content: str) -> str:
        text_content = (text_content or "").strip()
        if not text_content:
            return "新对话"

        m = re.search(r"(?:^|\n)\s*(?:User|用户)\s*[:：]?\s*(.+)", text_content, flags=re.IGNORECASE)
        if m:
            text_content = m.group(1).strip()

        text_content = text_content.split("\n", 1)[0].strip()
        text_content = re.sub(r"\s+", " ", text_content).strip()
        text_content = re.sub(r"^(?:User|用户)\s*[:：]?\s*", "", text_content, flags=re.IGNORECASE).strip()
        text_content = re.sub(r"<(?:think|analysis|reasoning)[^>]*>.*?</(?:think|analysis|reasoning)>", "", text_content, flags=re.DOTALL | re.IGNORECASE).strip()

        parts = re.split(r"[。！？!?]", text_content, maxsplit=1)
        candidate = (parts[0] if parts else text_content).strip()
        candidate = re.sub(r"\s+", " ", candidate).strip()
        candidate = candidate[:15].strip()
        return candidate or "新对话"

    def _clean_title(self, raw_title: str, fallback_source: str) -> str:
        raw_title = (raw_title or "").strip()
        if not raw_title:
            return self._fallback_title(fallback_source)

        raw_lower = raw_title.lower()
        if ("<think" in raw_lower and "</think>" not in raw_lower) or ("<analysis" in raw_lower and "</analysis>" not in raw_lower) or ("<reasoning" in raw_lower and "</reasoning>" not in raw_lower):
            return self._fallback_title(fallback_source)

        cleaned = re.sub(r"<(?:think|analysis|reasoning)[^>]*>.*?</(?:think|analysis|reasoning)>", "", raw_title, flags=re.DOTALL | re.IGNORECASE).strip()
        cleaned = re.sub(r"</?\s*(?:think|analysis|reasoning)\s*>", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:标题|title)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.strip('"').strip("'").strip()

        if "<think" in raw_lower or "<analysis" in raw_lower or "<reasoning" in raw_lower:
            cleaned = cleaned.strip()
        if re.search(r"(我现在|需要|任务|输出|下面|要求)", cleaned) or cleaned.startswith(("嗯", "好，", "好,", "好的", "Okay", "OK")):
            return self._fallback_title(fallback_source)
        if cleaned.startswith("<") or not cleaned:
            return self._fallback_title(fallback_source)

        return cleaned[:15].strip() or self._fallback_title(fallback_source)

    async def generate_and_update(self, session_id: int, first_input: str):
        """
        核心业务逻辑：
        1. 构造 Prompt
        2. 请求本地小模型 (Llama 3.2 等)
        3. 清洗数据
        4. 写入数据库
        """
        truncated_input = (first_input or "")[:300]
        prompt = (
            "任务：为下面对话内容生成一个5-15字的中文标题。\n"
            "要求：只输出标题本身，不要解释，不要输出<think>等思考过程标签。\n"
            f"内容：{truncated_input}\n"
            "标题："
        )

        try:
            resp = await self.client.chat.completions.create(
                model=Config.TITLE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.0,
            )
            
            title = self._clean_title(resp.choices[0].message.content, first_input)
            
            if title:
                async with AsyncSession(engine) as session:
                    await session.execute(
                        text("UPDATE ai_chat_sessions SET title = :t WHERE id = :sid"),
                        {"t": title, "sid": session_id}
                    )
                    await session.commit()

        except Exception as e:
            print(f"[Title Generator Error] Session {session_id}: {e}")
