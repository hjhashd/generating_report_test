import os
import sys
import shutil  
import logging
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from utils.zzp.create_catalogue import safe_path_component # 引入归一化函数

# ==========================================
# 0. 基础配置与导入
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
from zzp import sql_config as config
import server_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

# ==========================================
# 1. 核心删除逻辑 (保持不变，负责处理单条任务)
# ==========================================
def delete_report_task(target_type_name: str, target_report_name: str, user_id: int = None):
    """
    删除单个报告及其文件/文件夹
    [UPDATE] 2026-01-30: 支持删除重名记录（循环处理所有匹配项）
    """
    engine = get_db_connection()
    
    try:
        # 使用 begin() 自动管理事务，避免 'Connection' object has no attribute 'commit' 问题
        with engine.begin() as conn:
            # Step 1: 获取 Type ID
            sql_type = text("SELECT id FROM report_type WHERE type_name = :t_name LIMIT 1")
            result_type = conn.execute(sql_type, {"t_name": target_type_name}).fetchone()
            
            if not result_type:
                logger.error(f"❌ [跳过] 未找到报告类型: {target_type_name}")
                return False
            
            type_id = result_type[0]

            # Step 2: 获取所有匹配的 Report Name IDs (移除 LIMIT 1)
            # [Update] 增加查询 user_id 和 storage_dir 以支持精确删除
            query_report_str = "SELECT id, user_id, storage_dir FROM report_name WHERE type_id = :tid AND report_name = :r_name"
            params = {"tid": type_id, "r_name": target_report_name}
            
            if user_id is not None:
                query_report_str += " AND user_id = :user_id"
                params["user_id"] = user_id
                
            # [Fix] 移除 LIMIT 1，改为 fetchall 获取所有记录
            sql_report = text(query_report_str)
            result_reports = conn.execute(sql_report, params).fetchall()
            
            if not result_reports:
                logger.error(f"❌ [跳过] 未找到报告或无权限: {target_report_name}")
                return False
            
            # 循环处理每一条记录（解决重名导致删除不干净的问题）
            for row in result_reports:
                report_name_id = row[0]
                report_user_id = row[1]
                storage_dir = row[2]
                
                # Step 3: 获取关联文件路径 (仅用于日志或确认，删除主要依赖目录结构)
                sql_files = text("SELECT file_name FROM report_catalogue WHERE report_name_id = :rid")
                file_results = conn.execute(sql_files, {"rid": report_name_id}).fetchall()
                
                # [Fix] 直接构造目标目录路径，不再依赖文件路径反推 (因文件路径可能仅为文件名)
                # 优先使用数据库记录中的 user_id，如果没有则使用传入的 user_id
                effective_user_id = report_user_id if report_user_id is not None else user_id
                base_dir = server_config.get_user_report_dir(effective_user_id)
                
                # [UPDATE] 物理清理策略：同时尝试删除 storage_dir, 归一化路径, 原始路径
                paths_to_remove = set()
                
                # 1. 数据库记录的物理路径
                if storage_dir:
                    paths_to_remove.add(os.path.join(base_dir, target_type_name, storage_dir))
                
                # 2. 归一化后的路径 (可能存在于旧系统或文件系统自动转换)
                paths_to_remove.add(os.path.join(base_dir, target_type_name, safe_path_component(target_report_name)))
                
                # 3. 原始名称路径 (可能存在于旧系统)
                paths_to_remove.add(os.path.join(base_dir, target_type_name, target_report_name))
                
                # 执行删除
                deleted_any = False
                for target_directory_to_remove in paths_to_remove:
                    if target_directory_to_remove and os.path.exists(target_directory_to_remove):
                        try:
                            shutil.rmtree(target_directory_to_remove)
                            logger.info(f"🗑️ [文件夹删除] {target_directory_to_remove}")
                            deleted_any = True
                        except Exception as e:
                            logger.warning(f"⚠️ [文件夹删除异常] {e}")
                
                if not deleted_any:
                    # 兜底：逐个删除文件 (如果文件夹删除失败或不存在，尝试删除已知文件)
                    # 注意：这通常发生在文件分散或其他异常情况，一般情况 rmtree 足够
                    for f_row in file_results:
                        file_name = f_row[0]
                        # ... (existing fallback logic if needed, but rmtree should cover it)
                        # 这里简单保留原逻辑的意图，但在新架构下通常不需要
                        pass

                if user_id is not None:
                    img_dir = os.path.join(
                        server_config.EDITOR_IMAGE_DIR,
                        "report",
                        str(user_id),
                        target_type_name,
                        target_report_name
                    )
                    if os.path.exists(img_dir):
                        try:
                            shutil.rmtree(img_dir)
                            logger.info(f"🗑️ [图片目录删除] {img_dir}")
                        except Exception as e:
                            logger.warning(f"⚠️ [图片目录删除异常] {e}")

                # Step 5: 删除数据库记录
                sql_delete = text("DELETE FROM report_name WHERE id = :rid")
                conn.execute(sql_delete, {"rid": report_name_id})
            
            # 事务在 with 块结束时自动提交
            logger.info(f"✅ 删除成功: [{target_type_name}] - [{target_report_name}] (共清理 {len(result_reports)} 条记录)")
            return True

    except Exception as e:
        logger.error(f"❌ 异常: {e}")
        return False

# ==========================================
# 2. 批量执行入口 (这里改动了)
# ==========================================
if __name__ == "__main__":
    
    # 📝在此处定义您的批量任务列表
    # 每一行代表一个要删除的报告：{"type": "类型名称", "name": "报告名称"}
    BATCH_TASKS = [
        {"type": "资产报告", "name": "通用资产报告"},
        {"type": "资产报告", "name": "固定资产清查"},
        {"type": "可行性研究报告", "name": "AI项目一期"},
        {"type": "财务审计", "name": "2023年度审计"},
    ]
    
    total = len(BATCH_TASKS)
    print(f"🚀 启动批量删除任务，共计 {total} 个...")
    print("=" * 50)

    success_count = 0
    fail_count = 0

    # 循环遍历列表，逐个执行
    for index, task in enumerate(BATCH_TASKS):
        t_type = task["type"]
        t_name = task["name"]
        
        print(f"\n👉 [第 {index+1}/{total} 个] 正在处理: {t_name}")
        
        # 调用核心函数
        if delete_report_task(t_type, t_name):
            success_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 50)
    print(f"📊 执行结果汇总")
    print(f"✅ 成功删除: {success_count}")
    print(f"❌ 删除失败: {fail_count} (可能原因：名称不存在或数据库错误)")
    print("=" * 50)
