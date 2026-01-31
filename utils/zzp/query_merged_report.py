import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime
import logging

# ==========================================
# 0. 解决配置导入路径问题
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 1. 数据库连接
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 2. 核心功能：查询所有已合并报告列表
# ==========================================
def get_merged_reports_list(user_id=None):
    """
    查询 report_merged_record 表，关联 report_type，返回：
    - 报告名称 (merged_report_name)
    - 创建时间 (create_time)
    - 报告类型 (type_name)
    - 文件路径 (file_path)
    :param user_id: 用户ID (可选)，如果提供则仅查询该用户的报告
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as connection:
            # SQL 查询语句
            # 使用 JOIN 连接两张表
            query_sql = """
                SELECT 
                    r.merged_report_name,
                    r.create_time,
                    t.type_name,
                    r.id as merged_id,
                    r.file_path
                FROM report_merged_record r
                JOIN report_type t ON r.type_id = t.id
            """
            
            params = {}
            if user_id is not None:
                query_sql += " WHERE r.user_id = :uid "
                params["uid"] = user_id
                
            query_sql += " ORDER BY r.create_time DESC"
            
            sql = text(query_sql)
            
            rows = connection.execute(sql, params).fetchall()
            
            if not rows:
                logger.info("⚠️ 数据库中暂时没有已合并报告记录。")
                return []
            
            # 格式化结果
            result_list = []
            for row in rows:
                raw_time = row[1]
                formatted_time = ""
                if isinstance(raw_time, datetime.datetime):
                    formatted_time = raw_time.strftime("%Y-%m-%d %H:%M:%S")
                elif raw_time:
                    formatted_time = str(raw_time)
                else:
                    formatted_time = "未知时间"

                item = {
                    "reportName": row[0],
                    "createTime": formatted_time,
                    "reportType": row[2],
                    "reportId": row[3],
                    "filePath": row[4]
                }
                result_list.append(item)
                
            return result_list

    except Exception as e:
        logger.error(f"❌ 查询已合并报告列表失败: {e}", exc_info=True)
        return []

# ==========================================
# 3. 测试运行
# ==========================================
if __name__ == "__main__":
    report_list = get_merged_reports_list()
    
    if report_list:
        import json
        print(f"✅ 共找到 {len(report_list)} 份已合并报告：")
        print(json.dumps(report_list, indent=2, ensure_ascii=False))
