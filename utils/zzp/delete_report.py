import os
import sys
import shutil  
import logging
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

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
            query_report_str = "SELECT id FROM report_name WHERE type_id = :tid AND report_name = :r_name"
            params = {"tid": type_id, "r_name": target_report_name}
            
            if user_id is not None:
                query_report_str += " AND user_id = :user_id"
                params["user_id"] = user_id
                
            # [Fix] 移除 LIMIT 1，改为 fetchall 获取所有记录
            sql_report = text(query_report_str)
            result_reports = conn.execute(sql_report, params).fetchall()
            
            if not result_reports:
                logger.warning(f"⚠️ [兜底模式] 数据库未找到报告: {target_report_name}，尝试清理物理残留...")
                
                # 1. 尝试删除默认路径 (兼容旧版/公共版)
                paths_to_check = []
                paths_to_check.append(os.path.join(server_config.REPORT_DIR, target_type_name, target_report_name))
                
                # 2. 尝试删除用户隔离路径 (如果提供了 user_id)
                if user_id is not None:
                    paths_to_check.append(os.path.join(server_config.REPORT_DIR, str(user_id), target_type_name, target_report_name))
                    
                    # 3. 尝试删除图片目录
                    img_dir = os.path.join(
                        server_config.EDITOR_IMAGE_DIR, "report", str(user_id), target_type_name, target_report_name
                    )
                    paths_to_check.append(img_dir)

                deleted_any = False
                for p in paths_to_check:
                    if os.path.exists(p):
                        try:
                            shutil.rmtree(p)
                            logger.info(f"🗑️ [兜底删除] 物理目录: {p}")
                            deleted_any = True
                        except Exception as e:
                            logger.error(f"❌ [兜底删除失败] {p}: {e}")
                            
                return True # 视为处理完成
            
            # 循环处理每一条记录（解决重名导致删除不干净的问题）
            for row in result_reports:
                report_name_id = row[0]
                
                # Step 3: 获取关联文件路径
                sql_files = text("SELECT file_name FROM report_catalogue WHERE report_name_id = :rid")
                file_results = conn.execute(sql_files, {"rid": report_name_id}).fetchall()
                
                target_directory_to_remove = None

                # 寻找目标文件夹
                for f_row in file_results:
                    file_path = f_row[0]
                    if not file_path: continue
                    
                    # [Modified] 向上递归查找直到找到名为 target_report_name 的目录
                    # 解决文件位于子目录（如 images, word 等）导致无法匹配根目录的问题
                    current_path = file_path
                    found_root = False
                    
                    # 限制向上查找层级(例如5层)，防止死循环
                    for _ in range(5): 
                        parent_dir = os.path.dirname(current_path)
                        # 如果已经到达根目录或路径过短，停止
                        if not parent_dir or len(parent_dir) <= 1: 
                            break
                        
                        if os.path.basename(parent_dir) == target_report_name:
                            target_directory_to_remove = parent_dir
                            found_root = True
                            break
                        
                        current_path = parent_dir
                        
                        # 如果 current_path 已经不再变化（到达根），停止
                        if os.path.dirname(current_path) == current_path:
                            break
                    
                    if found_root:
                        break 
                
                # Step 4: 执行物理删除
                if target_directory_to_remove and os.path.exists(target_directory_to_remove):
                    try:
                        shutil.rmtree(target_directory_to_remove)
                        logger.info(f"🗑️ [文件夹删除] {target_directory_to_remove}")
                    except Exception as e:
                        logger.warning(f"⚠️ [文件夹删除异常] {e}")
                else:
                    # 兜底：逐个删除文件
                    for f_row in file_results:
                        file_path = f_row[0]
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except: pass

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
