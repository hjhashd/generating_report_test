import asyncio
import json
import sys
import os

# 设置项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.lyf.ai_search import Search_Chat_Generator_Stream
from utils.zzp.ai_generate_langchain import get_llm_config_by_id

async def test_search():
    # 使用 ID 6 的模型测试
    model_id = 6
    config = get_llm_config_by_id(model_id)
    if not config:
        print("未找到模型配置")
        return

    print(f"使用模型: {config['model_name']}")
    
    task_id = "test_task_123"
    user_query = "2024年中国节能降碳政策"
    
    generator = Search_Chat_Generator_Stream(
        user_query=user_query,
        model_name=config['model_name'],
        base_url=config['base_url'],
        api_key=config['api_key'],
        task_id=task_id
    )
    
    async for chunk in generator:
        if "data:" in chunk:
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                if "content" in data:
                    print(data["content"], end="", flush=True)
            except:
                pass
    print("\n--- 测试完成 ---")

if __name__ == "__main__":
    asyncio.run(test_search())
