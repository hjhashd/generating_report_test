import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime
import json
from datetime import datetime as dt
# =============================
# 配置导入路径
# =============================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
from utils.lyf.db_session import get_engine


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, dt):
            return obj.isoformat()
        return super().default(obj)


# =============================
# 数据库连接（明确：agent_report）
# =============================
def get_db_connection():
    return get_engine("agent_db")


# =============================
# 业务函数：根据文件夹名称查询提示词
# =============================
def get_prompts_by_folder_name(folder_name: str):
    """
    前端传来的folder_name中的"_"需要替换为"/"
    """
    # folder_name = folder_name.replace("_", "/")

    """
    前端传入文件夹名称，返回该文件夹下的所有用户提示词
    """
    engine = get_db_connection()

    sql = """
    SELECT 
        up.id,
        up.title,
        up.content,
        up.description,
        up.user_id,
        up.created_at,
        f.id   AS folder_id,
        f.name AS folder_name
    FROM user_prompts up
    INNER JOIN folders f
        ON up.folder_id = f.id
    WHERE f.name = :folder_name
    ORDER BY up.created_at DESC
    """

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(sql),
                {"folder_name": folder_name}
            ).mappings().all()

            result = []
            for r in rows:
                result.append({
                    "title": r["title"],
                    "content": r["content"]
                })

            return result

    except Exception as e:
        print(f"❌ 查询提示词失败: {e}")
        import traceback
        traceback.print_exc()
        return []

# ============================
# 按照浏览量获取最热门的提示词（默认十条）
# ============================

def get_hot_trending_prompts(limit: int = 10):
    """
    从公共提示词库中获取浏览量（曝光率）最高的数据
    """
    engine = get_db_connection()

    # SQL 逻辑：按照 views_count 降序排列
    sql = """
    SELECT
        id,
        title,
        content,
        views_count
    FROM public_prompts
    ORDER BY views_count DESC
    LIMIT :limit
    """

    try:
        with engine.begin() as conn:
            # 执行查询
            params = {"limit": limit}
            rows = conn.execute(text(sql), params).mappings().all()

            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "views_count": r["views_count"]
                }
                for r in rows
            ]

    except Exception as e:
        print(f"❌ 查询热门提示词失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_latest_updated_prompts(limit: int = None):
    engine = get_db_connection()

    sql = """
    SELECT
        id,
        title,
        content,
        updated_at
    FROM user_prompts
    ORDER BY updated_at DESC
    """

    if limit:
        sql += " LIMIT :limit"

    try:
        with engine.begin() as conn:
            params = {"limit": limit} if limit else {}
            rows = conn.execute(text(sql), params).mappings().all()

            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "updated_at": r["updated_at"]
                }
                for r in rows
            ]

    except Exception as e:
        print(f"❌ 查询最近更新提示词失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_prompts_by_keyword(keyword: str):
    """
    根据用户输入的关键字进行连表模糊查询
    匹配范围：文件夹名 / 标题 / 内容 / 描述
    """
    engine = get_db_connection()

    like_keyword = f"%{keyword}%"

    sql = """
    SELECT
        t3.title,
        t3.content
    FROM folders t1
    LEFT JOIN user_prompt_folders t2
        ON t1.id = t2.folder_id
    LEFT JOIN user_prompts t3
        ON t2.user_prompt_id = t3.id
    WHERE
        t3.title    LIKE :kw
        OR t3.content  LIKE :kw
    ORDER BY t3.updated_at DESC
    """

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(sql),
                {"kw": like_keyword}
            ).mappings().all()

            result = []
            for r in rows:
                # 防止 LEFT JOIN 产生空记录
                if r["title"] and r["content"]:
                    result.append({
                        "title": r["title"],
                        "content": r["content"]
                    })

            return result

    except Exception as e:
        print(f"❌ 模糊查询提示词失败: {e}")
        import traceback
        traceback.print_exc()
        return []


# =============================
# 测试运行
# =============================
if __name__ == "__main__":
    # 测试用文件夹名称（请替换为你库里真实存在的）
    test_folder_name = "通用"

    print(f"🧪 测试查询文件夹：{test_folder_name}")

    prompts = get_prompts_by_folder_name(test_folder_name)

    print(f"✅ 查询完成，共 {len(prompts)} 条提示词")

    # 漂亮打印 JSON，使用自定义编码器处理日期时间
    print(json.dumps(prompts, indent=2, ensure_ascii=False, cls=DateTimeEncoder))

    print("🧪 测试 1：最近更新的全部提示词")
    latest_prompts = get_latest_updated_prompts()
    print(json.dumps(latest_prompts, indent=2, ensure_ascii=False, cls=DateTimeEncoder))

    print("\n🧪 测试 2：关键字模糊搜索")
    keyword = "项目背景"
    search_result = search_prompts_by_keyword(keyword)
    print(json.dumps(search_result, indent=2, ensure_ascii=False, cls=DateTimeEncoder))

    # ✨ 新增测试：获取曝光率最高的前十条
    print("\n🧪 测试 3：浏览量（曝光率）最高的前十条公共提示词")
    hot_prompts = get_hot_trending_prompts(limit=10)
    print(f"🔥 热门提示词共 {len(hot_prompts)} 条：")
    print(json.dumps(hot_prompts, indent=2, ensure_ascii=False, cls=DateTimeEncoder))