import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def delete_report_type_logic(type_name: str, user_id: int) -> tuple[bool, str]:
    """
    删除报告类型逻辑
    Args:
        type_name: 类型名称
        user_id: 当前用户ID
    Returns:
        (success, message)
    """
    if not type_name:
        return False, "类型名称不能为空"

    engine = get_db_connection()
    
    try:
        with engine.begin() as connection:
            # 1. 查询该类型是否存在，且属于该用户
            # 注意：这里我们严格限制只能删除属于自己的类型 (user_id = :uid)
            # 公共类型 (user_id IS NULL) 不允许通过此接口删除，除非后续增加管理员逻辑
            find_sql = text("SELECT id FROM report_type WHERE type_name = :name AND user_id = :uid LIMIT 1")
            row = connection.execute(find_sql, {"name": type_name, "uid": user_id}).fetchone()
            
            if not row:
                # 检查是否是公共类型（提示区分）
                check_public = connection.execute(
                    text("SELECT id FROM report_type WHERE type_name = :name AND user_id IS NULL LIMIT 1"),
                    {"name": type_name}
                ).fetchone()
                
                if check_public:
                    return False, "无法删除公共报告类型，请联系管理员"
                return False, f"未找到名为 '{type_name}' 的私有报告类型"
            
            type_id = row[0]
            
            # 2. 检查是否有相关联的报告 (report_name 表)
            # 只要 report_name 表中有记录使用了这个 type_id，就不能删
            check_usage_sql = text("SELECT COUNT(*) FROM report_name WHERE type_id = :tid")
            usage_count = connection.execute(check_usage_sql, {"tid": type_id}).scalar()
            
            if usage_count > 0:
                return False, f"该类型下包含 {usage_count} 份报告，请先删除相关报告后再尝试删除类型"
            
            # 3. 执行删除
            delete_sql = text("DELETE FROM report_type WHERE id = :tid")
            connection.execute(delete_sql, {"tid": type_id})
            
            logger.info(f"用户 {user_id} 删除了报告类型: {type_name} (ID: {type_id})")
            return True, "删除成功"

    except Exception as e:
        logger.error(f"删除报告类型失败: {e}", exc_info=True)
        return False, f"数据库操作异常: {str(e)}"
