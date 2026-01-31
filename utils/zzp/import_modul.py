import pymysql
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
import os

# 路径配置
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
# 2. 核心逻辑：获取结构并自动填充 Origin 信息
# ==========================================
def get_report_json_structure(type_name: str, report_name: str, user_id=None):
    """
    查询数据库，并将所有节点标记为 isimport=1，
    来源信息自动填充为当前文档的自身信息。
    支持按 user_id 过滤私有报告。
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as connection:
            # --- 第一步：获取 type_id 和 report_name_id ---
            
            # 基础 SQL
            base_sql = """
                SELECT n.id as report_id, t.id as type_id
                FROM report_name n
                JOIN report_type t ON n.type_id = t.id
                WHERE n.report_name = :report_name AND t.type_name = :type_name
            """
            
            params = {"report_name": report_name, "type_name": type_name}
            
            # 如果提供了 user_id，则增加所有者过滤
            if user_id is not None:
                # [MODIFIED] Allow accessing both Private (own) and Public (NULL) templates
                base_sql += " AND (n.user_id = :user_id OR n.user_id IS NULL)"
                params["user_id"] = user_id
                # Prioritize own template if name conflicts (MySQL: NULL is smallest, so DESC puts user_id first)
                base_sql += " ORDER BY n.user_id DESC"
            
            base_sql += " LIMIT 1"
            
            id_sql = text(base_sql)
            
            id_result = connection.execute(id_sql, params).fetchone()
            
            if not id_result:
                # 尝试查询公共模板 (可选，假设 user_id 为 NULL 或 0 是公共)
                # 目前暂不自动降级查询公共，以免混淆
                print(f"❌ 未找到报告: 类型[{type_name}] - 名称[{report_name}] (User: {user_id})")
                return None
            
            report_name_id = id_result[0]
            
            # --- 第二步：查询基础目录结构 ---
            # 不需要查 origin 字段了，因为我们要用自身信息填充
            cat_sql = text("""
                SELECT id, catalogue_name, level, sortOrder, parent_id
                FROM report_catalogue
                WHERE report_name_id = :report_id
                ORDER BY level ASC, sortOrder ASC
            """)
            
            rows = connection.execute(cat_sql, {"report_id": report_name_id}).fetchall()
            
            if not rows:
                return {
                    "reportName": report_name,
                    "reportType": type_name,
                    "chapters": []
                }

            # --- 第三步：构建树形结构并自动填充 ---
            
            id_map = {}
            
            for row in rows:
                catalogue_title = row[1]
                
                node = {
                    "title": catalogue_title,
                    "level": row[2],
                    "sortOrder": row[3],
                    
                    # === 核心修改：全部填充为自身信息 ===
                    "isimport": 1,                      # 强制标记为导入
                    "origintitle": catalogue_title,     # 来源标题 = 自身标题
                    "originreportType": type_name,      # 来源类型 = 当前报告类型
                    "originreportName": report_name,    # 来源名称 = 当前报告名称
                    # =================================
                    
                    "children": [],
                    "_id": row[0],       
                    "_parent_id": row[4]
                }
                id_map[row[0]] = node

            # 2. 组装父子关系
            chapters = []
            for node_id, node in id_map.items():
                parent_id = node["_parent_id"]
                
                if parent_id == 0:
                    chapters.append(node)
                else:
                    parent_node = id_map.get(parent_id)
                    if parent_node:
                        parent_node["children"].append(node)
            
            # 3. 递归排序并清理
            def sort_children_recursive(nodes):
                nodes.sort(key=lambda x: x['sortOrder'])
                for node in nodes:
                    if "_id" in node: del node["_id"]
                    if "_parent_id" in node: del node["_parent_id"]
                    if node['children']:
                        sort_children_recursive(node['children'])

            sort_children_recursive(chapters)

            # --- 第四步：返回结果 ---
            result_json = {
                "reportName": report_name,
                "reportType": type_name,
                "chapters": chapters
            }
            
            return result_json

    except Exception as e:
        print(f"❌ 查询构建失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# ==========================================
# 测试运行
# ==========================================
if __name__ == "__main__":
    t_name = "可研究性报告1"
    r_name = "可研究性报告（合并资产报告）"
    
    # 假设数据库里有这个报告的基础目录结构
    data = get_report_json_structure(t_name, r_name)
    
    if data:
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))