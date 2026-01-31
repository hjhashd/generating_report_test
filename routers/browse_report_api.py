import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from routers.dependencies import require_user, CurrentUser
from natsort import natsorted  # ✅ 新增：用于文件名自然排序 (1.2 在 1.10 前面)

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_config

#查询具体的报告在前端进行展示。
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 定义报告文件的基准路径
BASE_DIR = server_config.REPORT_DIR
MERGE_DIR = server_config.MERGE_DIR

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
        
        # 新增分支处理逻辑
        if report.source_type == 'merge':
            # 分支 1: 只在 MERGE_DIR 查找 .docx 文件
            search_name = report.report_name
            if not search_name.lower().endswith('.docx'):
                search_name += '.docx'
            
            roots = [user_merge_dir, public_merge_dir]
            logger.info(f"source_type='merge'，在 MERGE_DIR 查找 .docx: {search_name}")
            for root in roots:
                if not root: continue
                p = os.path.join(root, report.type_name, search_name)
                if os.path.exists(p) and os.path.isfile(p):
                    found_path = p
                    logger.info(f"✅ [merge] 精确匹配到文件: {found_path}")
                    break
                    
        elif report.source_type == 'draft':
            # 分支 2: 只在 REPORT_DIR 查找目录
            roots = [user_base_dir, public_base_dir]
            logger.info(f"source_type='draft'，在 REPORT_DIR 查找目录: {report.report_name}")
            for root in roots:
                if not root: continue
                p = os.path.join(root, report.type_name, report.report_name)
                if os.path.exists(p) and os.path.isdir(p):
                    found_path = p
                    logger.info(f"✅ [draft] 精确匹配到目录: {found_path}")
                    break
        
        else:
            # 兼容旧逻辑：原有的自动查找逻辑
            search_candidates = []
            if not report.report_name.lower().endswith('.docx'):
                search_candidates.append(report.report_name + '.docx') 
            search_candidates.append(report.report_name)
            
            logger.info(f"未指定 source_type，使用兼容模式查找: {search_candidates}")
            
            for name in search_candidates:
                is_docx = name.lower().endswith('.docx')
                if is_docx:
                    roots = [user_merge_dir, user_base_dir, public_merge_dir, public_base_dir]
                else:
                    roots = [user_base_dir, user_merge_dir, public_base_dir, public_merge_dir]
                
                for root in roots:
                    if not root: continue
                    p = os.path.join(root, report.type_name, name)
                    if os.path.exists(p):
                        found_path = p
                        logger.info(f"✅ [legacy] 找到路径: {found_path}")
                        break
                if found_path:
                    break
        
        if found_path:
            full_report_path = found_path
        else:
            # 如果都没找到，保持回落逻辑
            if report.report_name.lower().endswith('.docx'):
                 full_report_path = os.path.join(user_merge_dir, report.type_name, report.report_name)
            else:
                 full_report_path = os.path.join(user_base_dir, report.type_name, report.report_name)
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