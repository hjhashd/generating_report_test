from urllib.parse import quote_plus
import os

# ==========================================
# 统一数据库配置中心
# ==========================================

# 1. 基础连接信息 (主要供 zzp 模块及兼容使用)
# 优先从环境变量读取，否则使用默认值（开发/测试环境）
# 这样既支持 Docker 生产环境注入，也支持本地直接运行（回退到默认值）
username = os.getenv("REPORT_DB_USER", 'root')
password = os.getenv("REPORT_DB_PASSWORD", 'xinan@2024')
host = os.getenv("REPORT_DB_HOST", '192.168.3.10')
port = int(os.getenv("REPORT_DB_PORT", 3306))
database = os.getenv("REPORT_DB_NAME", 'generating_reports_test')

# 2. 多数据库配置字典 (主要供 lyf 模块使用)
DATABASES = {
    "report_db": {
        "username": username,
        "password": password,
        "host": host,
        "port": port,
        "database": database,
    },
    "agent_db": {
        # 提示词/Agent 数据库配置
        "username": os.getenv("AGENT_DB_USER", "root"),
        "password": os.getenv("AGENT_DB_PASSWORD", "xinan123456"),
        "host": os.getenv("AGENT_DB_HOST", "192.168.3.13"),
        "port": int(os.getenv("AGENT_DB_PORT", 3306)),
        "database": os.getenv("AGENT_DB_NAME", "agent_report"),
    }
    # # ✅ 新增：远程 SSH 数据库配置
    # "remote_db": {
    #     "username": "root",
    #     "password": "#s@#$%^&*(I9", 
    #     "host": "8.138.186.7",
    #     "port": 31526,
    #     "database": "generating_reports", # ⚠️ 记得填入你在 Navicat 创建的数据库名
    # }
}

# 3. 工具函数 (主要供 lyf 模块使用)
def get_mysql_url(db_name: str) -> str:
    # 增加一个小容错，防止 db_name 传错直接崩掉
    if db_name not in DATABASES:
        raise KeyError(f"Database config '{db_name}' not found!")
        
    cfg = DATABASES[db_name]
    return (
        f"mysql+pymysql://{cfg['username']}:"
        f"{quote_plus(str(cfg['password']))}@" # 强制转 string 确保 quote_plus 不报错
        f"{cfg['host']}:{cfg['port']}/"
        f"{cfg['database']}?charset=utf8mb4"
    )
