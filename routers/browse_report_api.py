import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from routers.dependencies import require_user, CurrentUser
from natsort import natsorted  # ✅ 新增：用于文件名自然排序 (1.2 在 1.10 前面)
from utils.zzp.create_catalogue import safe_path_component
from utils.zzp import sql_config as config

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_config

#查询具体的报告在前端进行展示。
# logging.basicConfig(level=logging.INFO,
#                     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 定义报告文件的基准路径
BASE_DIR = server_config.REPORT_DIR
MERGE_DIR = server_config.MERGE_DIR

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def resolve_storage_dir(type_name, report_name, user_id):
    """
    根据 Type, Name, UserID 从数据库查询 storage_dir
    """
    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            # 1. Get Type ID
            res_type = conn.execute(text("SELECT id FROM report_type WHERE type_name=:tn LIMIT 1"), {"tn": type_name}).fetchone()
            if res_type:
                tid = res_type[0]
                # 2. Get Report Storage Dir
                sql = text("SELECT storage_dir FROM report_name WHERE type_id=:tid AND report_name=:rn AND user_id=:uid LIMIT 1")
                res = conn.execute(sql, {"tid": tid, "rn": report_name, "uid": user_id}).fetchone()
                if res and res[0]:
                    return res[0]
    except Exception as e:
        logger.error(f"Error querying storage_dir in browse_report: {e}")
    return None

# 请求参数模型
class BrowseReport(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    type_name: str
    report_name: str
    source_type: Optional[str] = None  # 新增字段: draft 或 merge

@router.post("/Browse_Report/")
def Browse_Report_endpoint(report: BrowseReport, current_user: CurrentUser = Depends(require_user)):
    logger.info(f'接收到的参数：{report}')
    # [MODIFIED] Get user_id from token
    user_id = current_user.id
    
    # 获取用户专属目录和公共目录
    user_base_dir = server_config.get_user_report_dir(user_id)
    user_merge_dir = server_config.get_user_merge_dir(user_id)
    public_base_dir = server_config.get_user_report_dir(None) # same as server_config.REPORT_DIR
    public_merge_dir = server_config.get_user_merge_dir(None) # same as server_config.MERGE_DIR

    try:
        found_path = None
        
        # [NEW] 1. 尝试从数据库获取 storage_dir (物理路径)
        storage_dir_name = resolve_storage_dir(report.type_name, report.report_name, user_id)
        
        # [NEW] 2. 准备候选目录名列表
        # 优先级: storage_dir > safe_name (归一化) > report_name (原始)
        candidate_names = []
        if storage_dir_name:
            candidate_names.append(storage_dir_name)
        
        safe_name = safe_path_component(report.report_name)
        if safe_name not in candidate_names:
            candidate_names.append(safe_name)
            
        if report.report_name not in candidate_names:
            candidate_names.append(report.report_name)
            
        logger.info(f"路径查找候选列表: {candidate_names}")

        # 新增分支处理逻辑
        if report.source_type == 'merge':
            # 分支 1: 只在 MERGE_DIR 查找 .docx 文件
            # 注意: merge 文件的文件名通常就是 report_name.docx，不涉及文件夹名 (除非是 type 文件夹)
            # 但这里我们主要关注的是 merge 后的文件是否存在
            
            roots = [user_merge_dir, public_merge_dir]
            
            # 对于 merge 文件，文件名本身可能也需要尝试归一化?
            # 通常 merge 文件名直接使用 report_name.docx (create_catalogue.py 生成时似乎没有归一化文件名，只归一化了目录)
            # 但为了保险，我们可以对文件名也做候选检查
            
            file_candidates = []
            for c in candidate_names:
                if not c.lower().endswith('.docx'):
                    file_candidates.append(c + '.docx')
                else:
                    file_candidates.append(c)
            
            logger.info(f"source_type='merge'，在 MERGE_DIR 查找文件: {file_candidates}")
            
            for root in roots:
                if not root: continue
                for fname in file_candidates:
                    p = os.path.join(root, report.type_name, fname)
                    if os.path.exists(p) and os.path.isfile(p):
                        found_path = p
                        logger.info(f"✅ [merge] 精确匹配到文件: {found_path}")
                        break
                if found_path: break
                    
        elif report.source_type == 'draft':
            # 分支 2: 只在 REPORT_DIR 查找目录
            roots = [user_base_dir, public_base_dir]
            logger.info(f"source_type='draft'，在 REPORT_DIR 查找目录, 候选: {candidate_names}")
            
            for root in roots:
                if not root: continue
                for dname in candidate_names:
                    p = os.path.join(root, report.type_name, dname)
                    if os.path.exists(p) and os.path.isdir(p):
                        found_path = p
                        logger.info(f"✅ [draft] 精确匹配到目录: {found_path}")
                        break
                if found_path: break
        
        else:
            # 兼容旧逻辑：原有的自动查找逻辑
            # 混合查找文件和目录
            logger.info(f"未指定 source_type，使用兼容模式查找")
            
            # 候选路径生成 (Type/Name)
            for dname in candidate_names:
                # 假设是目录
                roots_dir = [user_base_dir, public_base_dir]
                for root in roots_dir:
                    if not root: continue
                    p = os.path.join(root, report.type_name, dname)
                    if os.path.exists(p) and os.path.isdir(p):
                        found_path = p
                        logger.info(f"✅ [legacy] 找到目录: {found_path}")
                        break
                if found_path: break
                
                # 假设是文件
                fname = dname + '.docx' if not dname.lower().endswith('.docx') else dname
                roots_file = [user_merge_dir, public_merge_dir]
                for root in roots_file:
                    if not root: continue
                    p = os.path.join(root, report.type_name, fname)
                    if os.path.exists(p) and os.path.isfile(p):
                        found_path = p
                        logger.info(f"✅ [legacy] 找到文件: {found_path}")
                        break
                if found_path: break
        
        if found_path:
            full_report_path = found_path
        else:
            # 如果都没找到，保持回落逻辑 (优先使用 storage_dir 或 safe_name)
            fallback_name = candidate_names[0]
            if report.report_name.lower().endswith('.docx'):
                 full_report_path = os.path.join(user_merge_dir, report.type_name, fallback_name)
            else:
                 full_report_path = os.path.join(user_base_dir, report.type_name, fallback_name)
            logger.warning(f"❌ 未找到任何匹配路径，回落到默认: {full_report_path}")

        logger.info(f"最终确定的报告路径: {full_report_path}")

        file_list = []
        base_url_part = ""

        # 2. ✅ 新增逻辑：检查路径是否存在并区分目录与文件
        if os.path.exists(full_report_path):
            if os.path.isdir(full_report_path):
                # 如果是目录，扫描目录下所有 .docx 文件
                files = [f for f in os.listdir(full_report_path) 
                         if f.endswith('.docx') and not f.startswith('~$')]
                file_list = natsorted(files)
                # 【修改点】返回物理目录路径，确保以 / 结尾
                base_url_part = full_report_path if full_report_path.endswith(os.sep) else full_report_path + os.sep
                logger.info(f"✅ 查询成功 (目录)，找到 {len(file_list)} 个文件")
            else:
                # 如果是文件，直接将其作为列表返回
                file_list = [os.path.basename(full_report_path)]
                # 【修改点】返回文件所在的物理目录路径
                base_url_part = os.path.dirname(full_report_path) + os.sep
                logger.info(f"✅ 查询成功 (文件): {full_report_path}")
        else:
            logger.info(f"⚠️ 路径不存在: {full_report_path}")

        # 3. 返回结果 (合并了原有逻辑和新逻辑)
        return {
            "report_generation_status": 0,
            "report_generation_condition": "查询成功" if os.path.exists(full_report_path) else "目录不存在",
            "status": report.status,
            "report_path": full_report_path,  # 绝对路径 (后端用)
            "file_list": file_list,           # ✅ 新增：文件名列表 ['1.1 x.docx', '1.2 x.docx']
            "base_url_part": base_url_part    # ✅ 新增：前端拼接用的 URL 前缀
        }

    except Exception as e:
        logger.error(f"❌ 查询模块失败: {e}", exc_info=True)
        # 4. 发生异常时的返回
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"读取模块失败: {str(e)}",
            "status": report.status,
            "report_path": None,
            "file_list": [],
            "base_url_part": ""
        }


# ... (保持上面的 imports 和 class BrowseReport 不变) ...

# ✅ 新增接口：专门用于返回 .md 文件
@router.post("/Browse_MD_Report/")
def Browse_MD_Report_endpoint(report: BrowseReport):
    logger.info(f'接收到的 MD 查询参数：{report}')

    try:
        # 1. 拼接最终的文件夹路径 (逻辑与 docx 接口一致)
        full_report_path = os.path.join(BASE_DIR, report.type_name, report.report_name)
        logger.info(f"正在扫描 MD 文件的路径: {full_report_path}")

        file_list = []
        base_url_part = ""

        # 2. 检查目录是否存在并扫描文件
        if os.path.exists(full_report_path):
            # ✅ 核心修改：只扫描 .md 文件
            # 注意：Markdown 文件通常没有 Word 那种以 ~$ 开头的临时锁定文件，但保留过滤也无妨
            files = [f for f in os.listdir(full_report_path) 
                     if f.endswith('.md')]
            
            # 使用自然排序
            file_list = natsorted(files)
            
            # 【修改点】返回物理目录路径，确保以 / 结尾
            base_url_part = full_report_path if full_report_path.endswith(os.sep) else full_report_path + os.sep
            
            logger.info(f"✅ MD 查询成功，找到 {len(file_list)} 个文件")
        else:
            logger.info(f"⚠️ 路径不存在: {full_report_path}")

        # 3. 返回结果
        return {
            "report_generation_status": 0,
            "report_generation_condition": "查询成功" if os.path.exists(full_report_path) else "目录不存在",
            "status": report.status,
            "report_path": full_report_path,
            "file_list": file_list,           # 这里返回的是 .md 文件列表
            "base_url_part": base_url_part
        }

    except Exception as e:
        logger.error(f"❌ MD 查询模块失败: {e}", exc_info=True)
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"读取模块失败: {str(e)}",
            "status": report.status,
            "report_path": None,
            "file_list": [],
            "base_url_part": ""
        }
@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}