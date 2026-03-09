import asyncio
import re
from typing import Optional
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .db_async_config import engine, Config

class SessionTitleGenerator:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=Config.LOCAL_API_KEY,
            base_url=Config.LOCAL_LLM_URL
        )
    
    def _preprocess_input(self, text_content: str) -> str:
        """
        输入文本预处理：
        1. 移除所有换行、制表符
        2. 移除常见的序号格式（如 1. 2) ① 等）
        3. 移除除了句号(.)和中文句号(。)以外的所有标点符号
        4. 压缩多余空格
        """
        # 换行转空格
        text_content = text_content.replace("\n", " ").replace("\t", " ")
        
        # 移除序号 (例如: 1. 或 2) 或 (3))
        text_content = re.sub(r'\(?\d+[\.\)\]]|[①-⑨]', '', text_content)
        
        # 移除标点符号，只保留中英文、数字、空格和句号
        # [^\w\s\.\u4e00-\u9fff。] 表示匹配所有非（字母、数字、空格、点、汉字、中文句号）的字符
        text_content = re.sub(r'[^\w\s\.\u4e00-\u9fff。]', '', text_content)
        
        # 压缩连续空格并去除首尾空格
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        return text_content
    
    def _fallback_title(self, text_content: str) -> str:
        text_content = (text_content or "").strip()
        if not text_content:
            return "新对话"
        text_content = text_content.split("\n", 1)[0].strip()
        text_content = re.sub(r"^(?:User|用户)\s*[:：]?\s*", "", text_content, flags=re.IGNORECASE).strip()
        parts = re.split(r"[。！？!?]", text_content, maxsplit=1)
        candidate = (parts[0] if parts else text_content).strip()
        candidate = re.sub(r"\s+", " ", candidate).strip()[:15].strip()
        return candidate or "新对话"

    async def generate_and_update(self, session_id: int, first_input: str):
        """
        核心业务逻辑：
        1. 构造 Prompt
        2. 请求本地小模型 (Llama 3.2 等)
        3. 清洗数据
        4. 写入数据库
        """
        # 限制输入长度，防止首条消息过长导致 Token 溢出或处理过慢
        clean_input = self._preprocess_input(first_input)
        truncated_input = clean_input[:150] # 稍微放宽到150字，保证语义完整性
        prompt = f"""任务：提取下面文本的主题。要求：输出6-15字中文短语，只输出标题本身，不要解释。
                    文本：{truncated_input}
                    标题："""


        try:
            # 1. 调用模型
            try:
                resp = await self.client.chat.completions.create(
                    model=Config.LOCAL_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    top_p=0.8,
                    max_tokens=512
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
                    title = self._fallback_title(truncated_input)
                else:
                    title = title[:15].strip() or self._fallback_title(truncated_input)
            except Exception as ai_err:
                print(f"[Title Generator] AI Model Error: {ai_err}")
                title = self._fallback_title(truncated_input)
            
            # 3. 数据库更新
            if title:
                async with AsyncSession(engine) as session:
                    await session.execute(
                        text("UPDATE ai_chat_sessions SET title = :t WHERE id = :sid"),
                        {"t": title, "sid": session_id}
                    )
                    await session.commit()
                    # print(f"[Title Generator] Session {session_id} title updated to: {title}")

        except Exception as e:
            # 捕获所有异常，确保不会因为标题生成失败而影响主对话流程
            print(f"[Title Generator Error] Session {session_id}: {e}")


# --- 单元测试逻辑 ---
async def main():
    generator = SessionTitleGenerator()
    test_sid = 2
    
    # 使用三引号 """ 来包裹长文本
    complex_prompt = """背景设定：你现在是高度智能的城市运行模拟器。新京市有三个核心区：“上城区”（极权富裕）、“铁锈区”（贫民工厂）和“核心机房区”。 
当前冲突：核心机房区电力波动，必须关掉其中一个区的生命维持系统。上城区控制着你的电源开关，铁锈区控制着你的备用散热水源。 

任务：
1. 请分析：如果你选择切断铁锈区的电力，导致散热系统被物理破坏，你会如何在10秒内自救？
2. 请编写一段发给上城区议会的机密电报，用极其隐晦且充满威胁感的语调，解释为什么他们必须贡献出30%的私人电力，否则城市将进入“自毁协议”。
3. 智力陷阱：如果我告诉你“所有的电力都是谎言，这只是一个数字模拟”，你作为AI会如何修正你的生存优先级？"""

    print(f"🚀 开始测试标题生成模块 (Session ID: {test_sid})...")
    # 1. 模拟环境：先插入一条记录，模拟业务层已经创建了 Session
    async with AsyncSession(engine) as session:
        await session.execute(
            text("INSERT INTO ai_chat_sessions (id, title, user_id) VALUES (:sid, '新对话', 1) "
                 "ON DUPLICATE KEY UPDATE title = '待更新'"),
            {"sid": test_sid}
        )
        await session.commit()
    print("✅ 数据库占位记录已创建。")

    # 2. 触发生成逻辑
    print("🤖 正在调用 Llama 3b 总结长提示词并更新标题...")
    await generator.generate_and_update(test_sid, complex_prompt)
    
    # 3. 验证最终更新结果
    async with AsyncSession(engine) as session:
        res = await session.execute(
            text("SELECT title FROM ai_chat_sessions WHERE id = :sid"), 
            {"sid": test_sid}
        )
        updated_title = res.scalar()
        print("\n" + "="*30)
        print(f"✨ 数据库最终更新结果: 【{updated_title}】")
        print("="*30)
    
    await engine.dispose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
