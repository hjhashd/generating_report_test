import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
import server_config

from utils.zzp import sql_config as config

# =============================
# 数据库连接
# =============================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def get_folder_id_by_name(folder_name: str, user_id: int):
    engine = get_db_connection()
    with engine.connect() as conn:
        sql = text("""
            SELECT id
            FROM file_structure
            WHERE folder_name = :name AND user_id = :uid
            LIMIT 1
        """)
        row = conn.execute(sql, {"name": folder_name, "uid": user_id}).fetchone()
        return row.id if row else None

def add_file(file_name: str, folder_name: str, user_id: int):
    engine = get_db_connection()

    try:
        folder_id = get_folder_id_by_name(folder_name, user_id)
        if folder_id is None:
            raise ValueError(f"文件夹不存在: {folder_name} (user_id: {user_id})")

        # 直接使用传入的文件名，不再生成时间戳
        # 假设传入的 file_name 已经包含了时间戳或其他唯一标识
        new_file_name = file_name

        with engine.begin() as conn:
            sql = text("""
                INSERT INTO file_item (file_name, folder_id, file_path)
                VALUES (:fname, :fid, :fpath)
            """)
            conn.execute(sql, {
                "fname": new_file_name,
                "fid": folder_id,
                "fpath": f"{folder_name}/{new_file_name}"
            })

        print(f"✅ 文件新增成功：{new_file_name}")
        return new_file_name

    except Exception as e:
        print(f"❌ 新增文件失败: {e}")
        # 如果是文件夹不存在，应该抛出异常让上层知道
        if "文件夹不存在" in str(e):
             raise e
        return None

if __name__ == "__main__":
    # 使用 server_config 中的 PROJECT_ROOT 拼接测试文件路径
    test_file_path = os.path.join(server_config.PROJECT_ROOT, "utils/zzp/word拆分/李强主持召开国务院常务会议 研究进一步做好节能降碳工作等 广东省人民政府门户网站.pdf")
    add_file(test_file_path, "111")