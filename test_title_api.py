import asyncio
import aiohttp
import sys
import os

# 添加项目根目录到 path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from utils.lyf.db_async_config import engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from utils.lyf.auth_utils import create_access_token # 假设你有这个工具

# 配置
BASE_URL = "http://localhost:34521"
USER_ID = 1  # 假设测试用户ID为1
SESSION_ID = 9999 # 测试会话ID

async def prepare_data():
    """准备测试数据"""
    print("🛠️ 正在准备测试数据...")
    async with AsyncSession(engine) as session:
        # 1. 确保用户存在 (如果你的表有外键约束)
        # 这里的 user_id=1 通常在测试库里应该有，如果没有可能需要插入
        
        # 2. 插入测试会话
        await session.execute(
            text("""
                INSERT INTO ai_chat_sessions (id, user_id, title) 
                VALUES (:sid, :uid, '旧标题') 
                ON DUPLICATE KEY UPDATE title='旧标题'
            """),
            {"sid": SESSION_ID, "uid": USER_ID}
        )
        await session.commit()
    print(f"✅ 测试会话 {SESSION_ID} 已准备就绪")

async def get_auth_header():
    """生成测试用的 Auth Header"""
    # 这里模拟生成一个 Token
    # 注意：如果你的 require_user 依赖会校验数据库用户存在性，请确保 USER_ID 在库里
    token = create_access_token(user_id=USER_ID, username="test_user", roles=["user"])
    return {"Authorization": f"Bearer {token}"}

async def test_generate_title():
    """测试标题生成接口"""
    url = f"{BASE_URL}/api/ai/title/sessions/{SESSION_ID}/auto-title"
    headers = await get_auth_header()
    payload = {
        "context_text": "用户：你好，我想写一个关于人工智能的报告。AI：好的，关于人工智能的哪个方面呢？用户：主要关注大语言模型的发展历史。"
    }
    
    print(f"🚀 开始调用接口: {url}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            print(f"📡 状态码: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"✅ 响应成功: {data}")
                return data.get("new_title")
            else:
                text = await resp.text()
                print(f"❌ 请求失败: {text}")
                return None

async def verify_db(expected_title):
    """验证数据库更新"""
    if not expected_title:
        print("⚠️ 跳过数据库验证")
        return

    print("🔍 正在验证数据库...")
    async with AsyncSession(engine) as session:
        res = await session.execute(
            text("SELECT title FROM ai_chat_sessions WHERE id = :sid"),
            {"sid": SESSION_ID}
        )
        actual_title = res.scalar()
        
    print(f"🗄️ 数据库中的标题: {actual_title}")
    if actual_title == expected_title:
        print("✅ 数据库验证通过！")
    else:
        print(f"❌ 数据库验证失败：期望 '{expected_title}'，实际 '{actual_title}'")

async def main():
    try:
        await prepare_data()
        new_title = await test_generate_title()
        await verify_db(new_title)
    except Exception as e:
        print(f"💥 测试过程发生异常: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
