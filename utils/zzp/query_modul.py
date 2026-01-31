import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 将根目录加入到 Python 搜索路径中
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 2. 统计逻辑函数
# ==========================================

def query_and_print_report_stats(user_id=None):
    engine = get_db_connection()
    all_stats_data = []  # 用于存储所有报告的统计结果
    
    print("=== 开始查询报告统计信息 ===\n")
    
    try:
        with engine.connect() as connection:
            # 第一步：查询所有的 [报告名称] 和对应的 [报告类型]
            # [MODIFIED] Filter by user_id (Private + Public)
            if user_id is not None:
                reports_sql = text("""
                    SELECT n.id, n.report_name, t.type_name
                    FROM report_name n
                    JOIN report_type t ON n.type_id = t.id
                    WHERE n.user_id = :uid OR n.user_id IS NULL
                """)
                params = {"uid": user_id}
            else:
                # If no user_id provided, only return Public reports
                reports_sql = text("""
                    SELECT n.id, n.report_name, t.type_name
                    FROM report_name n
                    JOIN report_type t ON n.type_id = t.id
                    WHERE n.user_id IS NULL
                """)
                params = {}

            reports = connection.execute(reports_sql, params).fetchall()
            
            if not reports:
                print("数据库中暂时没有报告记录。")
                return []  # 返回空列表，防止主程序报错

            # 第二步：遍历每一个报告
            for report in reports:
                report_id = report[0]
                report_name = report[1]
                type_name = report[2]
                
                # 统计该报告下各层级数量
                count_sql = text("""
                    SELECT level, COUNT(*) as cnt
                    FROM report_catalogue
                    WHERE report_name_id = :report_id
                    GROUP BY level
                """)
                
                stats_result = connection.execute(count_sql, {"report_id": report_id}).fetchall()
                level_counts = {row[0]: row[1] for row in stats_result}
                
                level_1 = level_counts.get(1, 0)
                level_2 = level_counts.get(2, 0)
                level_3 = level_counts.get(3, 0)
                
                # 打印日志
                print(f"报告类型：{type_name}")
                print(f"报告名称：{report_name}")
                print(f"报告目录：该类型下的该名称报告包含 {level_1} 个一级，{level_2} 个二级，{level_3} 个三级目录")
                print("-" * 50)
                
                # 将当前报告的数据添加到列表中
                # 这里我们存为一个字典或元组，方便后续使用
                all_stats_data.append({
                    "type_name": type_name,
                    "report_name": report_name,
                    "level_1": level_1,
                    "level_2": level_2,
                    "level_3": level_3
                })

        # 循环结束后，返回所有数据
        return all_stats_data

    except Exception as e:
        print(f"❌ 查询过程中发生错误: {e}")
        return [] # 出错时返回空列表

if __name__ == "__main__":
    # 获取返回的列表
    stats_list = query_and_print_report_stats()
    
    if stats_list:
        print(f"\n✅ 共处理了 {len(stats_list)} 份报告的数据。")
        # 如果你想取第一份数据做测试：
        # first_report = stats_list[0]
        # print("第一份报告名称:", first_report['report_name'])
    else:
        print("\n⚠️ 未获取到任何数据。")