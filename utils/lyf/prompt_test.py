import re
import time
from typing import Generator
from utils.lyf.base_prompt_ai import base_ai

class PromptTest:
    def __init__(self):
        self.client = base_ai.get_client()
        self.model = base_ai.get_model_name()

    def run_test_stream(self, system_prompt_content: str, user_test_input: str) -> Generator[str, None, None]:
        """
        流式测试模式：实时输出，但自动隐藏 <think> 内容
        """
        # 1. 强力指令：在提示词头部告诉模型直接回答
        fast_system_prompt = f"Respond directly. DO NOT use <think> tags or internal reasoning. {system_prompt_content}"
        
        messages = [
            {"role": "system", "content": fast_system_prompt},
            {"role": "user", "content": user_test_input}
        ]

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.3
            )

            is_thinking = False  # 状态机：是否正在思考

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if not content:
                    continue

                # --- 状态检测逻辑：如果模型不听话输出了 <think>，我们把它过滤掉 ---
                if "<think>" in content:
                    is_thinking = True
                    # 尝试取 <think> 之前的内容（如果有的话）
                    content = content.split("<think>")[0]

                if "</think>" in content:
                    is_thinking = False
                    # 取 </think> 之后的内容
                    content = content.split("</think>")[-1]
                    if not content:
                        continue

                # 只有不在思考状态时，才返回给前端
                if not is_thinking and content:
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
