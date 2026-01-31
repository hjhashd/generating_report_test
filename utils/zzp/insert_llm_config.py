import os
import sys
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from cryptography.fernet import Fernet

# ==========================================
# 0. 基础配置
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
from utils import sql_config as config

# 🔐 【重要】必须使用和读取代码完全一致的密钥！
ENCRYPTION_KEY = b'8P_Gk9wz9qKj-4t8z9qKj-4t8z9qKj-4t8z9qKj-4t8=' 
cipher_suite = Fernet(ENCRYPTION_KEY)

# ==========================================
# 1. 数据库连接
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 2. 写入逻辑 (自动加密 + 强制Custom类型)
# ==========================================

def save_custom_config(model_name, api_key, base_url, user_id):
    """
    接收前端数据，加密后存入数据库
    自动将 llm_type 设为 'custom'
    """
    engine = get_db_connection()
    
    # 1. 🔒 加密 API Key
    if api_key:
        encrypted_key = cipher_suite.encrypt(api_key.encode()).decode()
    else:
        encrypted_key = ""
        
    print(f"🔒 Key 已加密: {encrypted_key[:10]}...")

    # 2. 💾 SQL 语句
    # 增加 user_id 字段
    sql = text("""
        INSERT INTO llm_config (llm_type, model_name, api_key, base_url, user_id)
        VALUES ('custom', :name, :key, :url, :user_id)
        ON DUPLICATE KEY UPDATE
            model_name = VALUES(model_name),
            api_key = VALUES(api_key),
            base_url = VALUES(base_url),
            user_id = VALUES(user_id)
    """)
    
    try:
        with engine.connect() as conn:
            conn.execute(sql, {
                "name": model_name,
                "key": encrypted_key,
                "url": base_url,
                "user_id": user_id
            })
            conn.commit()
            
        print(f"✅ [Custom] 配置已成功写入数据库！")
        return True
        
    except Exception as e:
        print(f"❌ 写入失败: {e}")
        return False

# ==========================================
# 3. 模拟前端调用 (Main)
# ==========================================

if __name__ == "__main__":
    
    # 假设这是前端传给你的数据
    model_name = "kimi-k2-0905-preview"
    api_key = "sk-P3RDEov9bsUxciEKN43a6RLtYhvdls1xlUEjg9D6TPiiuih" # 明文 Key
    base_url = "https://api.moonshot.cn/v1"
    
    print("📥 接收到前端配置请求...")
    
    # 调用保存函数
    save_custom_config(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url
    )