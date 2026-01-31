import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
    
from utils.zzp import sql_config as config

# =============================
# 数据库连接
# =============================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def add_folder(folder_name, user_id):
    engine = get_db_connection()
    try:
        # --- 关键修改：把 connect() 改为 begin() ---
        with engine.begin() as conn: 
        # ----------------------------------------
            # 检查是否存在
            check_sql = text("SELECT id FROM file_structure WHERE folder_name = :name AND user_id = :uid")
            existing = conn.execute(check_sql, {"name": folder_name, "uid": user_id}).fetchone()
            
            if existing:
                print(f"ℹ️ 文件夹 '{folder_name}' (user: {user_id}) 已存在，ID: {existing.id}")
                return existing.id

            sql = text("INSERT INTO file_structure (folder_name, user_id) VALUES (:name, :uid)")
            result = conn.execute(sql, {"name": folder_name, "uid": user_id})
            # 这里不需要写 commit()，它会自动提交
            
            print(f"✅ 文件夹 '{folder_name}' (user: {user_id}) 添加成功")
            return result.lastrowid
    except Exception as e:
        print(f"❌ 添加文件夹失败: {e}")
        import traceback
        traceback.print_exc()
        raise e  # 抛出异常以便上层捕获

if __name__ == "__main__":
    add_folder("示例文件夹")
