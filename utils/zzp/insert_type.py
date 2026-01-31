import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os

# 环境配置
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def add_new_report_type(type_name_input: str, user_id=None) -> bool:
    """
    尝试添加一个新的报告类型。
    返回:
        True:  插入成功 (原库无此类型)
        False: 插入失败 (原库已有此类型，或数据库报错)
    """
    type_name = type_name_input.strip()
    if not type_name:
        return False

    engine = get_db_connection()
    
    try:
        with engine.begin() as connection:
            # 1. 查重 (区分用户)
            if user_id is not None:
                check_sql = text("SELECT id FROM report_type WHERE type_name = :name AND user_id = :uid LIMIT 1")
                params = {"name": type_name, "uid": user_id}
            else:
                # 如果没有传 user_id，检查是否有 user_id 为 NULL 的公共类型 (或兼容旧数据)
                check_sql = text("SELECT id FROM report_type WHERE type_name = :name AND user_id IS NULL LIMIT 1")
                params = {"name": type_name}

            existing = connection.execute(check_sql, params).fetchone()
            
            if existing:
                print(f"⚠️ 类型 '{type_name}' 已存在，跳过插入。")
                return False  # 返回 False 表示已存在
            
            # 2. 插入
            if user_id is not None:
                insert_sql = text("INSERT INTO report_type (type_name, user_id) VALUES (:name, :uid)")
                connection.execute(insert_sql, {"name": type_name, "uid": user_id})
            else:
                insert_sql = text("INSERT INTO report_type (type_name) VALUES (:name)")
                connection.execute(insert_sql, {"name": type_name})
            
            print(f"✅ 类型 '{type_name}' 插入成功。")
            return True   # 返回 True 表示成功

    except Exception as e:
        print(f"❌ 数据库操作出错: {e}")
        return False      # 出错也返回 False

if __name__ == "__main__":
    # 测试1：尝试添加一个可能不存在的
    print("--- 测试添加新类型 ---")
    res1 = add_new_report_type("全新测试报告类型")
    print(res1)
    
    print("\n--- 测试重复添加 ---")
    # 测试2：再次添加同一个，应该提示已存在
    res2 = add_new_report_type("全新测试报告类型")
    print(res2)