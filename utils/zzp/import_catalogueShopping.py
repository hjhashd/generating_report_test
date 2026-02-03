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
# 2. 核心功能：获取特定一级类目及其子树
# ==========================================
def get_specific_category_tree(report_type: str, report_name: str, category_name: str):
    """
    根据报告类型、报告名称、一级类目名称，返回该类目下的所有子类目树形结构。
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as connection:
            # --- 第一步：获取 report_id ---
            id_sql = text("""
                SELECT n.id
                FROM report_name n
                JOIN report_type t ON n.type_id = t.id
                WHERE n.report_name = :report_name AND t.type_name = :type_name
                LIMIT 1
            """)
            
            id_result = connection.execute(id_sql, {"report_name": report_name, "type_name": report_type}).fetchone()
            
            if not id_result:
                print(f"❌ 未找到报告: {report_type} - {report_name}")
                return None
            
            report_id = id_result[0]
            
            # --- 第二步：获取该报告的所有目录 ---
            # 我们一次性拉取该报告所有数据，在内存中组装树，比递归查库更高效
            cat_sql = text("""
                SELECT id, catalogue_name, level, sortOrder, parent_id
                FROM report_catalogue
                WHERE report_name_id = :report_id
                ORDER BY level ASC, sortOrder ASC
            """)
            rows = connection.execute(cat_sql, {"report_id": report_id}).fetchall()
            
            if not rows:
                print("⚠️ 该报告下没有任何目录数据")
                return None

            # --- 第三步：构建树形结构并填充 Origin 信息 ---
            id_map = {}
            
            for row in rows:
                catalogue_title = row[1]
                
                # 按照你的要求，自动填充 origin 信息为自身
                node = {
                    "title": catalogue_title,
                    "level": row[2],
                    "sortOrder": row[3],
                    # === 自动填充 ===
                    "isimport": 1, 
                    "origintitle": catalogue_title,
                    "originreportType": report_type,
                    "originreportName": report_name,
                    "origin_catalogue_id": row[0],  # [Best Practice] 暴露源ID给前端
                    # ===============
                    "children": [],
                    "_id": row[0],
                    "_parent_id": row[4]
                }
                id_map[row[0]] = node

            # 组装树
            root_nodes = []
            for node_id, node in id_map.items():
                parent_id = node["_parent_id"]
                if parent_id == 0:
                    root_nodes.append(node)
                else:
                    parent_node = id_map.get(parent_id)
                    if parent_node:
                        parent_node["children"].append(node)
            
            # 递归排序清理函数
            def sort_and_clean(nodes):
                nodes.sort(key=lambda x: x['sortOrder'])
                for node in nodes:
                    if "_id" in node: del node["_id"]
                    if "_parent_id" in node: del node["_parent_id"]
                    if node['children']:
                        sort_and_clean(node['children'])

            # 先对所有根节点进行整理
            sort_and_clean(root_nodes)

            # --- 第四步：筛选目标一级类目 ---
            target_node = None
            for node in root_nodes:
                # 找到名称匹配且层级为1的节点
                if node['title'] == category_name and node['level'] == 1:
                    target_node = node
                    break
            
            if not target_node:
                print(f"⚠️ 未找到名为 [{category_name}] 的一级类目")
                # 如果没找到，可以选择返回空结构或None，这里返回None表示查询失败
                return None

            # --- 第五步：组装最终结果 ---
            result_json = {
                "reportName": report_name,
                "reportType": report_type,
                "chapters": [target_node]  # 注意：这里是一个包含目标节点的列表
            }
            
            return result_json

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return None

# ==========================================
# 测试运行
# ==========================================
if __name__ == "__main__":
    r_type = "可研究性报告1"
    r_name = "可研究性报告（网页）"
    c_name = "项目总览"  # 你要查询的一级类目名称
    
    data = get_specific_category_tree(r_type, r_name, c_name)
    
    if data:
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("未获取到数据")