import os
import sys
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# ==========================================
# 0. 基础配置
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
from utils import sql_config as config

# ==========================================
# 1. 数据库连接
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 2. 删除模型配置
# ==========================================

engine = get_db_connection()

def delete_config(config_id: int, user_id: int = None) -> bool:
    """
    删除指定ID的模型配置
    增加权限校验：如果提供了 user_id，则只能删除该用户的模型
    """
    sql_str = "DELETE FROM llm_config WHERE id = :id"
    params = {"id": config_id}
    
    if user_id is not None:
        sql_str += " AND user_id = :user_id"
        params["user_id"] = user_id

    sql = text(sql_str)

    try:
        with engine.begin() as conn:
            result = conn.execute(sql, params)
            if result.rowcount == 0:
                if user_id is not None:
                    raise ValueError(f"id={config_id} 的模型配置不存在或无权删除")
                else:
                    raise ValueError(f"id={config_id} 的模型配置不存在")

        print(f"✅ 配置 id={config_id} 已成功删除")
        return True

    except ValueError as ve:
        print(f"⚠️ {ve}")
        return False

    except Exception as e:
        print(f"❌ 数据库删除失败: {e}")
        return False

# ==========================================
# 3. 模拟前端调用 (Main)
# ==========================================

if __name__ == "__main__":
    
    delete_config(7)