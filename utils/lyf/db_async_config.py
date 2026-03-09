import os
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from server_config import AI_API_KEY, AI_BASE_URL, AI_MODEL_NAME

class Config:
    # ================= 数据库配置 =================
    DB_USER = os.getenv("REPORT_DB_USER", "root")
    DB_PASSWORD = quote_plus(os.getenv("REPORT_DB_PASSWORD", "xinan@2024"))
    DB_HOST = os.getenv("REPORT_DB_HOST", "192.168.3.10")
    _db_port_str = os.getenv("REPORT_DB_PORT", "3306")
    DB_PORT = _db_port_str if _db_port_str else "3306"
    DB_NAME = os.getenv("REPORT_DB_NAME", "generating_reports_test")

    @staticmethod
    def db_url() -> str:
        return (
            f"mysql+aiomysql://"
            f"{Config.DB_USER}:{Config.DB_PASSWORD}"
            f"@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
        )

    # ================= 主模型配置 (从 server_config 获取) =================
    MAIN_API_KEY = AI_API_KEY
    MAIN_BASE_URL = AI_BASE_URL
    MAIN_MODEL = AI_MODEL_NAME
    MAIN_LLM_URL = MAIN_BASE_URL

    # ================= 本地模型配置 (默认值或环境变量) =================
    LOCAL_API_KEY = os.getenv("LOCAL_API_KEY", MAIN_API_KEY)
    LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", MAIN_BASE_URL)
    LOCAL_MODEL = os.getenv("LOCAL_MODEL", MAIN_MODEL)
    TITLE_MODEL = LOCAL_MODEL # Alias for title generation
    LOCAL_LLM_URL = LOCAL_BASE_URL

    # ================= 性能 / 安全 =================
    MAX_CONCURRENCY = 8
    CONNECT_TIMEOUT = 10.0
    READ_TIMEOUT = 120.0
    MAX_TOKENS = 8192

    # ================= 业务策略 =================
    WINDOW_SIZE = 5
    SUMMARY_THRESHOLD = 8


# ================= 数据库 Engine / Session =================
engine = create_async_engine(
    Config.db_url(),
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
