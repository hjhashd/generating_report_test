import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入统一的 sql_config
try:
    # 尝试直接从当前包或父包导入
    from . import sql_config
except ImportError:
    # 如果失败，从 utils 导入
    from utils import sql_config

_ENGINE_POOL = {}

def get_mysql_url(db_name: str):
    """根据数据库名生成 URL"""
    # 优先从 sql_config.DATABASES 获取配置
    if db_name in sql_config.DATABASES:
        return sql_config.get_mysql_url(db_name)
    
    # 兼容逻辑：如果传入的是具体的数据库名（如 'generating_reports'），
    # 但 DATABASES 里只有 'report_db'，则默认返回 'report_db' 的配置
    return sql_config.get_mysql_url('report_db')


def get_engine(db_name: str):
    if db_name not in _ENGINE_POOL:
        _ENGINE_POOL[db_name] = create_engine(
            get_mysql_url(db_name),
            pool_pre_ping=True,  # 远程连接必备：自动重连
            pool_recycle=3600    # 每小时重置连接，防止 MySQL 断开
        )
    return _ENGINE_POOL[db_name]

# ==========================================
# 适配 FastAPI 的新函数
# ==========================================

def get_db(db_name: str = "report_db"):
    """
    FastAPI 依赖项生成器
    默认连接 report_db (在测试环境下已统一为 generating_reports_test)
    """
    engine = get_engine(db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_session_cm(db_name: str = "report_db"):
    """
    用于后台脚本的上下文管理器 (with 语法)
    """
    engine = get_engine(db_name)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
