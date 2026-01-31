import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def get_categories_and_types(user_id: int = None):
    """
    返回两个列表：
    1. 一级类目列表 (公共模板 + 用户私有)
    2. 报告类型列表
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as connection:
            # --- 1. 查询一级类目 ---
            # 关键逻辑：
            # 1. 基础查询：所有 user_id IS NULL 的记录（公共模板）
            # 2. OR：当前登录用户的私有记录 (user_id = :user_id)
            # 3. 关联关系调整：参考 Query_modul，通过 report_name (n) 关联 report_type (t)，确保一致性
            cat_query = """
                SELECT 
                    t.type_name,
                    n.report_name,
                    c.catalogue_name,
                    c.id as catalogue_id,
                    c.sortOrder
                FROM report_catalogue c
                JOIN report_name n ON c.report_name_id = n.id
                JOIN report_type t ON n.type_id = t.id
                WHERE c.level = 1
                AND (n.user_id IS NULL 
            """
            
            params = {}
            if user_id is not None:
                cat_query += " OR n.user_id = :user_id)"
                params["user_id"] = user_id
            else:
                cat_query += ")"
                
            cat_query += " ORDER BY t.id ASC, n.id ASC, c.sortOrder ASC"
            
            cat_sql = text(cat_query)
            cat_rows = connection.execute(cat_sql, params).fetchall()
            
            category_list = []
            if cat_rows:
                for row in cat_rows:
                    category_list.append({
                        "reportType": row[0],
                        "reportName": row[1],
                        "categoryName": row[2],
                        "catalogueId": row[3],
                        "sortOrder": row[4]
                    })

            # --- 2. 查询所有报告类型 ---
            if user_id is not None:
                type_sql = text("SELECT type_name FROM report_type WHERE user_id = :uid OR user_id IS NULL ORDER BY id ASC")
                type_rows = connection.execute(type_sql, {"uid": user_id}).fetchall()
            else:
                type_sql = text("SELECT type_name FROM report_type WHERE user_id IS NULL ORDER BY id ASC")
                type_rows = connection.execute(type_sql).fetchall()
                
            type_list = [row[0] for row in type_rows] if type_rows else []

            # ✅ 关键修改：直接返回两个列表 (元组)
            return category_list, type_list

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        # 出错时返回两个空列表，防止解包报错
        return [], []

# 测试部分
if __name__ == "__main__":
    # ✅ 这里就可以用两个参数来接收了
    cats, types = get_categories_and_types()
    
    print(f"一级目录数量: {len(cats)}")
    print(f"报告类型数量: {len(types)}")
    print("报告类型:", types)