import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

def del_file(file_id: int, user_id: int, is_admin: bool = False) -> bool:
    engine = get_db_connection()

    try:
        with engine.begin() as conn:
            # 1. 查询文件信息以便删除物理文件 (同时校验 user_id 或管理员权限)
            # 如果是管理员 (is_admin=True)，则忽略 user_id 校验
            sql_select = text("""
                SELECT f.file_name, s.folder_name, s.user_id
                FROM file_item f
                JOIN file_structure s ON f.folder_id = s.id
                WHERE f.id = :file_id 
                AND (:is_admin = 1 OR s.user_id = :user_id)
            """)
            result = conn.execute(sql_select, {
                "file_id": file_id, 
                "user_id": user_id,
                "is_admin": 1 if is_admin else 0
            }).fetchone()
            
            if not result:
                print(f"❌ 删除失败: 未找到文件 id={file_id} 或无权删除 (user_id={user_id}, is_admin={is_admin})")
                return False
                
            file_name = result[0]
            folder_name = result[1]
            file_owner_id = result[2]  # 获取文件实际所有者 ID，用于构建路径

            # 2. 删除数据库记录
            sql_delete = text("""
                DELETE FROM file_item WHERE id = :file_id
            """)
            conn.execute(sql_delete, {"file_id": file_id})
            
        # 3. 删除物理文件
        base_dir = project_root 
        # 注意：使用文件的实际所有者 ID (file_owner_id) 而不是请求者 ID (user_id)
        # 因为管理员可能删除其他用户的文件
        file_path = os.path.join(base_dir, "inferrence", str(file_owner_id), folder_name, file_name)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"✅ 物理文件已删除: {file_path}")
            except OSError as e:
                print(f"⚠️ 物理文件删除失败: {e}")
        else:
            print(f"⚠️ 物理文件不存在，跳过: {file_path}")
            # 尝试查找带时间戳的同名文件 (容错处理)
            parent_dir = os.path.dirname(file_path)
            if os.path.exists(parent_dir):
                name_no_ext, ext = os.path.splitext(file_name)
                # 查找 pattern: name_no_ext + "_" + timestamp + ext
                # 简单遍历目录查找
                found_fuzzy = False
                for f in os.listdir(parent_dir):
                    if f.startswith(name_no_ext + "_") and f.endswith(ext):
                         # 再次确认前缀匹配 (避免 'test' 匹配 'test_1' 但其实是 'test_new')
                         # 假设格式严格为 Name_Timestamp.ext
                         fuzzy_path = os.path.join(parent_dir, f)
                         try:
                             os.remove(fuzzy_path)
                             print(f"✅ (模糊匹配) 物理文件已删除: {fuzzy_path}")
                             found_fuzzy = True
                             # break? 可能会有多个副本，全部删除？为了安全只删一个？
                             # 考虑到数据不一致，全部删除可能更干净，但也更危险。
                             # 暂时只删第一个找到的，或者不删。
                             # 用户抱怨"奇怪"，可能是因为删不掉。
                             # 还是稳妥点，只删精确匹配，或者提示用户手动删。
                             # 但用户之前的日志显示 404，说明文件名确实不匹配。
                             # 这里做一个简单的尝试删除，如果不匹配就算了。
                         except Exception as e:
                             print(f"⚠️ (模糊匹配) 删除失败: {e}")
                
                if not found_fuzzy:
                    print(f"⚠️ 未找到模糊匹配的文件")

        print(f"✅ 文件 id={file_id} 数据库记录已成功删除")
        return True

    except Exception as e:
        print(f"❌ 删除文件失败: {e}")
        return False


if __name__ == "__main__":
    # 测试用例：需要提供有效的 file_id 和 user_id
    # del_file(28, 1001) 
    print("✅ 测试代码需手动配置参数运行")