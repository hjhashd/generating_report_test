import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
import datetime

# ==========================================
# 0. 解决配置导入路径问题
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

# ==========================================
# 1. 数据库连接
# ==========================================
def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 2. 核心功能：查询所有报告列表（含时间与类型）
# ==========================================
def get_all_reports_list(user_id: int = None):
    """
    查询 report_name 表，关联 report_type，返回：
    - 报告名称 (report_name)
    - 创建时间 (create_time)
    - 报告类型 (type_name)
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as connection:
            # SQL 查询语句
            # 使用 JOIN 连接两张表
            # ORDER BY n.create_time DESC 表示按时间倒序排列（最新的在前面）
            query_str = """
                SELECT 
                    n.report_name,
                    n.create_time,
                    t.type_name,
                    n.id as report_id
                FROM report_name n
                JOIN report_type t ON n.type_id = t.id
            """
            
            params = {}
            if user_id is not None:
                query_str += " WHERE n.user_id = :user_id"
                params["user_id"] = user_id
                
            query_str += " ORDER BY n.create_time DESC"
            
            sql = text(query_str)
            
            rows = connection.execute(sql, params).fetchall()
            
            if not rows:
                print("⚠️ 数据库中暂时没有报告记录。")
                return []
            
            # 格式化结果
            result_list = []
            for row in rows:
                # 处理时间格式：如果 create_time 是 datetime 对象，转为字符串
                # 如果数据库里有些老数据 create_time 是 NULL，这里给个默认值
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
                    "reportId": row[3]  # 顺便带上ID，前端通常需要用ID来做后续操作
                }
                result_list.append(item)
                
            return result_list

    except Exception as e:
        print(f"❌ 查询报告列表失败: {e}")
        import traceback
        traceback.print_exc()
        return []

        

# ==========================================
# 3. 测试运行
# ==========================================
if __name__ == "__main__":
    report_list = get_all_reports_list()
    
    if report_list:
        import json
        print(f"✅ 共找到 {len(report_list)} 份报告：")
        # 打印结果
        print(json.dumps(report_list, indent=2, ensure_ascii=False))