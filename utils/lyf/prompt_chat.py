import re
from typing import List, Generator, Dict
from utils.lyf.base_prompt_ai import base_ai, AISettings

class PromptChat:
    def __init__(self):
        self.client = base_ai.get_client()
        self.model = base_ai.get_model_name()
        # 引入全局会话管理器
        self.session_mgr = base_ai.get_session_manager()

    def _summarize_old_context(self, old_messages: List[Dict]) -> str:
        """
        内部方法：调用 AI 对久远的对话进行摘要
        """
        if not old_messages:
            return ""
        
        conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_messages])
        
        try:
            # 摘要逻辑保持 stream=False，确保快速拿到结果
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "请简要总结以下对话的关键信息，保留核心意图和事实，不要遗漏重要参数。"},
                    {"role": "user", "content": conversation_text}
                ],
                stream=False,
                max_tokens=300, # 摘要可以稍微长一点点
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"摘要生成失败: {e}")
            return "（旧对话摘要生成失败）"

    def construct_context(self, history: List[Dict], current_query: str) -> List[Dict]:
        """
        核心策略：根据历史长度决定是否压缩
        """
        # 如果历史记录少于等于 5 条，直接组装
        if len(history) <= 5:
            return history + [{"role": "user", "content": current_query}]

        # --- 触发摘要逻辑 ---
        old_part = history[:-5]  # 5条之前的全部摘要
        recent_part = history[-5:] # 保留最近5条原文

        summary = self._summarize_old_context(old_part)

        system_message = {
            "role": "system", 
            "content": f"你是一个提示词优化助手。直接输出正文，不要输出思考过程。早期对话摘要：\n{summary}"
        }

        return [system_message] + recent_part + [{"role": "user", "content": current_query}]

    def chat_stream(self, user_id: str, query: str) -> Generator[str, None, None]:
        """
        对外暴露的流式对话接口：现在只需要传入 user_id
        """
        # 1. 从管理器中获取该用户的专属历史
        history = self.session_mgr.get_history(user_id)
        
        # 2. 构建经过压缩的上下文
        messages = self.construct_context(history, query)
        
        full_reply = ""
        is_thinking = False  # 思考标签过滤开关

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                max_tokens=AISettings.MAX_TOKENS_LIMIT, # 保护资源
                temperature=AISettings.TEMPERATURE_DEFAULT
            )

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if not content:
                    continue

                # --- 恢复原始逻辑：直接返回内容，交由前端解析 ---
                # 后端只负责透传，不负责 UI 逻辑
                full_reply += content 
                yield content

            # 3. 对话顺利结束，更新用户的内存历史
            new_history = history + [
                {"role": "user", "content": query},
                {"role": "assistant", "content": full_reply}
            ]
            self.session_mgr.update_history(user_id, new_history)

        except Exception as e:
            yield f"\n[会话异常]: {str(e)}"

# 实例化单例供外部调用
prompt_chat_service = PromptChat()

# ==========================================
# 3. 运行入口 (支持多用户隔离测试)
# ==========================================
if __name__ == "__main__":
    import time
    service = PromptChat()

    print("--- 🚀 开始对话隔离与摘要测试 ---")

    # 模拟用户 A：聊 Python
    USER_A = "user_123"
    print(f"\n[用户 A]: 我想学习 Python 爬虫。")
    for chunk in service.chat_stream(USER_A, "我想学习 Python 爬虫。"):
        print(chunk, end="", flush=True)

    # 模拟用户 B：聊 烹饪 (完全隔离)
    USER_B = "user_456"
    print(f"\n\n[用户 B]: 如何做红烧肉？")
    for chunk in service.chat_stream(USER_B, "如何做红烧肉？"):
        print(chunk, end="", flush=True)

    # 再次回到用户 A：检查是否记得刚才的话
    print(f"\n\n[用户 A 追问]: 你刚才推荐的第一个库是什么？")
    for chunk in service.chat_stream(USER_A, "你刚才推荐的第一个库是什么？"):
        print(chunk, end="", flush=True)

    print("\n\n[测试结束]")
