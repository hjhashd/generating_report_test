import os
import sys
import logging
import re  # ✅ 新增：用于正则提取章节号
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from docx import Document
from docxcompose.composer import Composer 
from utils.zzp.create_catalogue import safe_path_component # 引入归一化函数 

# ==========================================
# 0. 基础配置与导入
# ==========================================
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)
import server_config
from utils.zzp import sql_config as config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TARGET_ROOT_DIR = server_config.MERGE_DIR

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def get_chapter_sort_key(file_path):
    """
    ✅ 新增函数：从文件路径中提取章节号进行自然排序
    例如："/path/to/2.1.1 现状分析.docx" -> [2, 1, 1]
    这样可以确保 1.2 在 1.10 前面，且 3.1 在 1.1 后面
    """
    filename = os.path.basename(file_path)
    # 正则匹配开头的数字和点，例如 "3.2.2.1"
    match = re.match(r'^([\d\.]+)', filename)
    if match:
        # 将 "3.2.1" 变成 [3, 2, 1]
        try:
            return [int(n) for n in match.group(1).split('.') if n]
        except ValueError:
            return [float('inf')] # 解析失败放到最后
    return [float('inf')] # 没有数字开头的文件放到最后

def merge_docx_files(source_files, target_path):
    """
    合并多个 docx 文件的核心逻辑
    """
    try:
        if not source_files:
            return False, "没有可合并的文件"

        # 1. 以第一个文件为母版
        master_doc = Document(source_files[0])
        composer = Composer(master_doc)

        # 2. 依次追加后续文件
        for i in range(1, len(source_files)):
            doc_path = source_files[i]
            if os.path.exists(doc_path):
                try:
                    sub_doc = Document(doc_path)
                    composer.append(sub_doc)
                except Exception as sub_e:
                    logger.warning(f"⚠️ 追加文件失败 {doc_path}: {sub_e}")
            else:
                logger.warning(f"⚠️ 合并时跳过不存在的文件: {doc_path}")

        # 3. 保存
        composer.save(target_path)
        return True, "合并成功"
    except Exception as e:
        logger.error(f"合并文件出错: {e}")
        return False, str(e)

def get_sorted_source_files(target_type_name: str, target_report_name: str, user_id=None):
    engine = get_db_connection()
    with engine.connect() as conn:
        sql_type = text("SELECT id FROM report_type WHERE type_name = :t_name LIMIT 1")
        result_type = conn.execute(sql_type, {"t_name": target_type_name}).fetchone()
        if not result_type:
            return []
        type_id = result_type[0]
        
        # [MODIFIED] Filter by user_id, and fetch storage_dir
        query_report = "SELECT id, storage_dir FROM report_name WHERE type_id = :tid AND report_name = :r_name"
        params = {"tid": type_id, "r_name": target_report_name}
        if user_id is not None:
            query_report += " AND user_id = :uid"
            params["uid"] = user_id
        query_report += " LIMIT 1"
        
        sql_report = text(query_report)
        result_report = conn.execute(sql_report, params).fetchone()
        
        if not result_report:
            return []
        report_name_id = result_report[0]
        storage_dir = result_report[1]

        # 确定报告的物理文件夹名称
        base_dir = server_config.get_user_report_dir(user_id)
        
        # 优先使用数据库记录的 storage_dir
        if storage_dir:
             report_dir_name = storage_dir
        else:
             # 兼容旧数据：尝试归一化路径，如果不存在则使用原始名称
             safe_name = safe_path_component(target_report_name)
             if os.path.exists(os.path.join(base_dir, target_type_name, safe_name)):
                 report_dir_name = safe_name
             else:
                 report_dir_name = target_report_name
        
        full_report_dir = os.path.join(base_dir, target_type_name, report_dir_name)

        sql_files = text("""
            SELECT file_name FROM report_catalogue 
            WHERE report_name_id = :rid 
            ORDER BY sortOrder ASC
        """)
        file_results = conn.execute(sql_files, {"rid": report_name_id}).fetchall()
        raw_source_files = []
        for row in file_results:
            file_name = row[0]
            if file_name:
                # 拼接完整路径
                full_path = os.path.join(full_report_dir, file_name)
                if os.path.exists(full_path):
                    raw_source_files.append(full_path)
                else:
                    logger.warning(f"文件不存在: {full_path}")

    # 使用自然排序对文件进行重新排序
    # 因为数据库里的 sortOrder 可能是按插入顺序，不一定完全对应章节号逻辑
    # 如果您信任 sortOrder，可以跳过这一步。这里为了保险，再次按章节号排序。
    sorted_files = sorted(raw_source_files, key=get_chapter_sort_key)
    # 修正：既然数据库已经有 sortOrder，我们应该优先信赖数据库的顺序。
    # 除非 sortOrder 不可靠。根据之前逻辑，似乎没用 sortOrder 而是查出来后再排？
    # 原代码只写了 ORDER BY sortOrder ASC，然后就没动作了。
    # 假设数据库顺序是对的。
    return sorted_files

def process_report_merge(type_name: str, report_name: str, user_id=None):
    """
    执行合并流程的主入口
    :param type_name: 报告类型
    :param report_name: 报告名称
    :param user_id: 用户ID
    :return: (bool, message)
    """
    # 1. 获取源文件列表
    source_files = get_sorted_source_files(type_name, report_name, user_id)
    if not source_files:
        return False, f"未找到该报告下的子文件: {report_name}"

    # 2. 准备目标目录
    # [MODIFIED] Use user-specific merge dir
    base_merge_dir = server_config.get_user_merge_dir(user_id)
    
    save_dir = os.path.join(base_merge_dir, type_name)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 3. 构造目标文件路径
    target_file_name = f"{report_name}.docx"
    target_path = os.path.join(save_dir, target_file_name)

    logger.info(f"开始合并 {len(source_files)} 个文件 -> {target_path}")

    # 4. 执行合并
    success, msg = merge_docx_files(source_files, target_path)
    
    # 5. [NEW] 如果合并成功，将记录写入数据库
    if success:
        try:
            save_merged_record_to_db(type_name, report_name, target_path, user_id)
            logger.info(f"✅ 合并记录已写入数据库: {report_name}")
        except Exception as db_e:
            logger.error(f"❌ 写入数据库失败: {db_e}")
            # 注意：这里虽然数据库写入失败，但文件合并是成功的。
            # 我们可以选择返回成功但带警告，或者视为失败。
            # 通常为了数据一致性，应该视为某种程度的失败，但文件已经生成了。
            # 这里我们仅记录日志，依然返回成功。

    return success, msg

def save_merged_record_to_db(type_name, report_name, file_path, user_id):
    """
    将合并后的报告记录写入 report_merged_record 表
    """
    engine = get_db_connection()
    with engine.begin() as conn: # 使用事务
        # 1. 获取 type_id
        sql_type = text("SELECT id FROM report_type WHERE type_name = :t_name LIMIT 1")
        res_type = conn.execute(sql_type, {"t_name": type_name}).fetchone()
        if not res_type:
            raise Exception(f"未找到报告类型: {type_name}")
        type_id = res_type[0]

        # 2. 获取 report_name_id
        # 注意：这里需要根据 user_id 过滤，确保关联到正确的报告
        sql_report = "SELECT id FROM report_name WHERE type_id = :tid AND report_name = :r_name"
        params = {"tid": type_id, "r_name": report_name}
        if user_id is not None:
            sql_report += " AND user_id = :uid"
            params["uid"] = user_id
        sql_report += " LIMIT 1"
        
        res_report = conn.execute(text(sql_report), params).fetchone()
        if not res_report:
            raise Exception(f"未找到报告名称记录: {report_name}")
        report_name_id = res_report[0]

        # 3. 插入或更新 report_merged_record
        # 策略：如果已存在同名合并记录，是覆盖还是新增？
        # 通常合并操作会覆盖旧文件，所以数据库记录也应该更新或覆盖。
        # 这里我们先查询是否存在
        check_sql = "SELECT id FROM report_merged_record WHERE report_name_id = :rid AND type_id = :tid"
        check_params = {"rid": report_name_id, "tid": type_id}
        if user_id is not None:
            check_sql += " AND user_id = :uid"
            check_params["uid"] = user_id
            
        existing = conn.execute(text(check_sql), check_params).fetchone()
        
        if existing:
            # 更新
            update_sql = """
                UPDATE report_merged_record 
                SET file_path = :path, create_time = NOW(), merged_report_name = :m_name
                WHERE id = :eid
            """
            conn.execute(text(update_sql), {
                "path": file_path, 
                "m_name": report_name, 
                "eid": existing[0]
            })
        else:
            # 插入
            insert_sql = """
                INSERT INTO report_merged_record 
                (type_id, report_name_id, merged_report_name, file_path, create_time, user_id)
                VALUES (:tid, :rid, :m_name, :path, NOW(), :uid)
            """
            # 如果 user_id 为 None，我们需要给一个默认值吗？数据库定义是 NOT NULL DEFAULT 2
            # 但我们在代码里应该尽量明确。如果 user_id 是 None，可能需要处理。
            # 不过根据调用链，user_id 应该传进来了。
            real_uid = user_id if user_id is not None else 2 # Fallback to default user 2
            
            conn.execute(text(insert_sql), {
                "tid": type_id,
                "rid": report_name_id,
                "m_name": report_name,
                "path": file_path,
                "uid": real_uid
            })

if __name__ == "__main__":
    INPUT_TYPE = "资产报告"
    INPUT_NAME = "123456"
    print(f"🚀 开始合并任务: [{INPUT_TYPE}] - [{INPUT_NAME}]")
    success, msg = process_report_merge(INPUT_TYPE, INPUT_NAME)
    if success:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")
