import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime
import json

# =============================
# 配置导入路径
# =============================
import sys
import os
# lyf_path = os.path.dirname(__file__)
# if lyf_path not in sys.path:
#     sys.path.append(lyf_path)
from .sql_config import get_mysql_url

# =============================
# 数据库连接
# =============================
def get_db_connection():
    db_url = get_mysql_url("report_db")
    return create_engine(db_url)
# =============================
# 查询文件及文件夹信息
# =============================
def get_all_files_with_folders(top_n=None, user_id=None):
    """
    查询 file_item 表，返回文件及其对应的文件夹信息：
    - fileId
    - fileName
    - hotClick
    - folderId
    - folderName
    - createTime
    
    参数:
        top_n: int or None
            - None: 返回全部文件
            - 数字: 返回 hotClick 排名前 N 的文件
        user_id: int or None
            - 用户ID，用于过滤专属文件
    """
    engine = get_db_connection()
    try:
        with engine.begin() as conn:
            sql = """
                SELECT
    s.id           AS folderId,
    s.folder_name  AS folderName,
    s.user_id      AS userId,
    f.id           AS fileId,
    f.file_name    AS fileName,
    f.hotClick,
    f.create_time
FROM file_structure s
LEFT JOIN file_item f
    ON s.id = f.folder_id
            """
            params = {}
            if user_id is not None:
                sql += " WHERE (s.user_id = :user_id OR s.user_id = 0) "
                params['user_id'] = user_id

            sql += """
ORDER BY
    COALESCE(f.hotClick, 0) DESC,
    f.create_time DESC
            """
            
            if top_n is not None:
                sql += f" LIMIT {int(top_n)}"
            
            rows = conn.execute(text(sql), params).fetchall()
            result = []
            for r in rows:
                raw_time = r[6]
                formatted_time = raw_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(raw_time, datetime.datetime) else str(raw_time)
                result.append({
    "folderId": r[0],    # 对应 SQL 中的 s.id
    "folderName": r[1],  # 对应 SQL 中的 s.folder_name
    "userId": r[2],      # 对应 SQL 中的 s.user_id
    "fileId": r[3],      # 对应 SQL 中的 f.id
    "fileName": r[4],    # 对应 SQL 中的 f.file_name
    "hotClick": r[5],    # 对应 SQL 中的 f.hotClick
    "createTime": formatted_time
})
                  
            return result
    except Exception as e:
        print(f"❌ 查询文件列表失败: {e}")
        import traceback
        traceback.print_exc()
        return []

# =============================
# 查询模型名称列表
# =============================
def get_model_names(user_id=None):
    """
    查询 llm_config 表，返回模型配置列表
    支持根据 user_id 过滤：返回 公用模型(user_id IS NULL) + 用户私有模型
    """
    engine = get_db_connection()
    try:
        with engine.begin() as conn:
            sql = "SELECT id, model_name, llm_type FROM llm_config"
            params = {}
            
            if user_id is not None:
                sql += " WHERE user_id IS NULL OR user_id = :user_id"
                params['user_id'] = user_id
                
            rows = conn.execute(text(sql), params).fetchall()

            result = [
                {
                    "id": row[0],
                    "model_name": row[1],
                    "llm_type": row[2]
                }
                for row in rows
            ]
            return result

    except Exception as e:
        print(f"❌ 查询模型名称失败: {e}")
        import traceback
        traceback.print_exc()
        return []



# =============================
# 测试运行
# =============================
if __name__ == "__main__":
    # 全部文件
    all_files = get_all_files_with_folders()
    print(f"✅ 全部文件，共 {len(all_files)} 个")
    print(json.dumps(all_files, indent=2, ensure_ascii=False))

    # 热门 TOP5
    top_files = get_all_files_with_folders(top_n=5)
    print(f"🔥 热门 TOP5 文件")
    print(json.dumps(top_files, indent=2, ensure_ascii=False))

    # 查询模型名称列表
    model_names = get_model_names()
    print(f"🤖 模型名称列表: {model_names}")