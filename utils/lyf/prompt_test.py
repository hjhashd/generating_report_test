import re
import time
from typing import Generator
from utils.lyf.base_prompt_ai import base_ai

class PromptTest:
    def __init__(self):
        self.client = base_ai.get_client()
        self.model = base_ai.get_model_name()

    def run_test_stream(self, system_prompt_content: str, user_test_input: str = None) -> Generator[str, None, None]:
        """
        流式测试模式：实时输出所有内容（包括 <think>，由前端解析）
        如果 user_test_input 为空，则只发送 system_prompt，让 AI 直接根据提示词模板输出
        """
        messages = [{"role": "system", "content": system_prompt_content}]
        
        # 只有当用户提供了测试输入时才添加用户消息
        if user_test_input and user_test_input.strip():
            messages.append({"role": "user", "content": user_test_input})

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.3
            )

            for chunk in stream:
                # 透传推理内容（如果有）
                # 注意：这里我们选择将推理内容也作为普通内容返回，或者你可以选择加上 <think> 标签
                # 考虑到测试接口的通用性，我们暂且让它自然流出
                if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                    reasoning = chunk.choices[0].delta.reasoning_content
                    # yield f"<think>{reasoning}</think>" # 可选：显式标记

                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            yield f"Error: {str(e)}"

prompt_test_service = PromptTest()

# ==========================================
# 3. 运行入口 (独立测试用 - 流式隐藏版)
# ==========================================
if __name__ == "__main__":
    TARGET_SYSTEM_PROMPT = """
    你是一个专业的职場写作助手。
    任务：根据用户输入的记录，生成一份结构清晰的周报。
    """

    TARGET_USER_INPUT = "这周修复了登录界面的CSS样式，对接了两个API接口，周五下午请假。"

    print("--- 🌊 开始流式测试 (已过滤思考过程) ---")
    print("🤖 AI 正在响应...\n")
    
    service = PromptTest()
    start_time = time.time()

    # 模拟流式打印
    for chunk in service.run_test_stream(TARGET_SYSTEM_PROMPT, TARGET_USER_INPUT):
        print(chunk, end="", flush=True)

    print("\n\n" + "-" * 50)
    print(f"⏱️ 响应结束，总耗时: {time.time() - start_time:.2f}s")
