import os
import sys
import logging
import shutil
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
# 1. 核心删除逻辑
# ==========================================
def delete_merged_report_task(merged_id: int, user_id=None):
    """
    删除单个已合并报告及其物理文件
    :param merged_id: 报告合并记录ID
    :param user_id: 用户ID (可选)，如果提供则校验归属权
    """
    engine = get_db_connection()
    
    try:
        with engine.connect() as conn:
            # Step 1: 获取文件路径
            query_sql = "SELECT file_path, merged_report_name, user_id FROM report_merged_record WHERE id = :mid"
            params = {"mid": merged_id}
            
            sql_get = text(query_sql)
            result = conn.execute(sql_get, params).fetchone()
            
            if not result:
                logger.warning(f"⚠️ 未找到 ID 为 {merged_id} 的合并报告记录")
                return False
            
            file_path = result[0]
            report_name = result[1]
            owner_id = result[2]
            
            # 权限校验
            # 转换为字符串进行比较，避免 int vs str 类型不匹配问题
            if user_id is not None and str(owner_id) != str(user_id):
                logger.warning(f"⛔ 权限拒绝: 用户 {user_id} 试图删除属于用户 {owner_id} 的报告 (ID: {merged_id})")
                return False

            # Step 2: 执行物理文件删除
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"🗑️ [文件删除成功] {file_path}")
                    
                    # 2.1 删除同名 HTML 文件
                    html_path = os.path.splitext(file_path)[0] + ".html"
                    if os.path.exists(html_path):
                        os.remove(html_path)
                        logger.info(f"🗑️ [HTML删除成功] {html_path}")
                        
                    try:
                        dir_name = os.path.dirname(file_path) # .../report_merge/{user_id}/{type_name}
                        type_name = os.path.basename(dir_name)
                        
                        target_img_dir = os.path.join(
                            server_config.EDITOR_IMAGE_DIR,
                            "report_merge",
                            str(owner_id),
                            type_name,
                            report_name
                        )
                        
                        if os.path.exists(target_img_dir):
                            shutil.rmtree(target_img_dir)
                            logger.info(f"🗑️ [图片目录删除成功] {target_img_dir}")
                    except Exception as e:
                        logger.warning(f"⚠️ 计算或删除图片目录失败: {e}")

                except Exception as e:
                    logger.error(f"❌ [文件删除失败] {file_path}: {e}")
                    # 即使文件删除失败，我们通常也继续删除数据库记录
            else:
                logger.warning(f"⚠️ 文件不存在，跳过物理删除: {file_path}")

            # Step 3: 删除数据库记录
            sql_delete = text("DELETE FROM report_merged_record WHERE id = :mid")
            conn.execute(sql_delete, {"mid": merged_id})
            conn.commit()
            
            logger.info(f"✅ 数据库记录删除成功: {report_name} (ID: {merged_id})")
            return True

    except Exception as e:
        logger.error(f"❌ 删除合并报告异常 (ID: {merged_id}): {e}", exc_info=True)
        return False

# ==========================================
# 2. 测试运行
# ==========================================
if __name__ == "__main__":
    # 测试删除 ID 为 1 的记录
    TEST_ID = 1
    print(f"🚀 开始删除合并报告 ID: {TEST_ID}")
    success = delete_merged_report_task(TEST_ID)
    if success:
        print("✅ 删除成功")
    else:
        print("❌ 删除失败")
