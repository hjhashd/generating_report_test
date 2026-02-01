import logging
import os
import shutil
import datetime
import sys
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends
from pydantic import BaseModel
from typing import Optional
from routers.dependencies import require_user, CurrentUser

# 配置导入路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 引入底层操作函数
from utils.lyf.queryAll import get_all_files_with_folders, get_model_names
from utils.lyf.add_folder import add_folder
from utils.lyf.add_file import add_file
from utils.lyf.query_prompts import get_prompts_by_folder_name
from utils.lyf.del_file import del_file
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# ===========================
# 请求模型
# ===========================
class FolderQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token

class FileQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    top: Optional[int] = None  # 可选参数，返回热度Top N

class FolderCreate(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    folder_name: str
    is_public: Optional[bool] = False # New: Create in public scope

class FileCreate(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    file_name: str
    folder_name: str
    is_public: Optional[bool] = False # New: Add to public scope

class QueryPrompts(BaseModel):
    folder_name: str

class QueryLLMModels(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token

class LatestPromptsQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    limit: Optional[int] = 5  # 最近更新多少条，默认 5

class SearchPromptsQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    keyword: str  # 用户输入关键字

class deleteFileRequest(BaseModel):
    task_id: str
    status: int
    agentUserId: Optional[int] = None # Deprecated: use token
    file_id: int  # 需要删除的文件 ID




# ===========================
# 查询文件及文件夹信息接口
# ===========================
@router.post("/query_all/")
def query_all_endpoint(req: FileQuery, current_user: CurrentUser = Depends(require_user)):
    logger.info(f"接收到查询文件及文件夹信息参数: {req} (User: {current_user.id})")
    try:
        files_and_folders = get_all_files_with_folders(top_n=req.top, user_id=current_user.id)
        logger.info(f"查询到 {len(files_and_folders)} 个文件及文件夹")
        return {
            "status_code": 0,
            "message": "查询成功",
            "status": req.status,
            "data": files_and_folders
        }
    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"查询失败: {str(e)}",
            "status": req.status,
            "data": []
        }

# ===========================
# 新增文件夹接口
# ===========================
@router.post("/add_folder/")
def add_folder_endpoint(req: FolderCreate, current_user: CurrentUser = Depends(require_user)):
    target_user_id = current_user.id
    if req.is_public:
        target_user_id = 0
        logger.info(f"User {current_user.id} creating PUBLIC folder")

    logger.info(f"接收到新增文件夹请求: {req.folder_name} (Target User: {target_user_id})")
    try:
        folder_id = add_folder(req.folder_name, target_user_id)
        logger.info(f"文件夹添加成功，ID={folder_id}")
        return {
            "status_code": 0,
            "message": "添加成功",
            "status": req.status,
            "data": {"folder_id": folder_id, "folder_name": req.folder_name}
        }
    except Exception as e:
        logger.error(f"新增文件夹失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"添加失败: {str(e)}",
            "status": req.status,
            "data": {}
        }

# ===========================
# 新增文件接口
# ===========================
@router.post("/add_file/")
def add_file_endpoint(req: FileCreate, current_user: CurrentUser = Depends(require_user)):
    target_user_id = current_user.id
    if req.is_public:
        target_user_id = 0
        logger.info(f"User {current_user.id} adding file to PUBLIC folder")

    logger.info(f"接收到新增文件请求: {req.file_name} -> 文件夹: {req.folder_name} (Target User: {target_user_id})")
    try:
        new_file_name = add_file(req.file_name, req.folder_name, target_user_id)
        logger.info(f"文件添加成功: {new_file_name} (folder_name={req.folder_name})")
        return {
            "status_code": 0,
            "message": "添加成功",
            "status": req.status,
            "data": {"file_name": new_file_name, "folder_name": req.folder_name}
        }
    except Exception as e:
        logger.error(f"新增文件失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"添加失败: {str(e)}",
            "status": req.status,
            "data": {}
        }

# ===========================
# 删除文件接口
# ===========================
@router.post("/delete_file/")
def delete_file_endpoint(req: deleteFileRequest, current_user: CurrentUser = Depends(require_user)):
    logger.info(f"接收到删除文件请求: {req.file_id} (User: {current_user.id})")
    try:
        # 检查管理员权限
        is_admin = False
        if current_user.roles and "admin" in current_user.roles:
            is_admin = True
            
        result = del_file(req.file_id, current_user.id, is_admin=is_admin)
        if result:
            logger.info(f"文件删除成功: {req.file_id}")
            return {
                "status_code": 0,
                "message": "删除成功",
                "status": req.status,
                "data": {"file_id": req.file_id}
            }
        else:
            logger.error(f"文件删除失败: {req.file_id}")
            return {
                "status_code": 1,
                "message": f"删除失败: {req.file_id}，可能无权限或文件不存在",
                "status": req.status,
                "data": {}
            }
    except Exception as e:
        logger.error(f"删除文件失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"删除失败: {str(e)}",
            "status": req.status,
            "data": {}
        }

# ===========================
# 文件上传接口
# ===========================
@router.post("/upload_file/")
async def upload_file_endpoint(
    folder_name: str = Form(...),
    agentUserId: Optional[int] = Form(None), # Deprecated: use token, but kept for frontend compatibility
    is_public: bool = Form(False),           # New: Allow upload to public folder
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_user)
):
    # Determine the target owner of the file
    # If is_public is True, we use User ID 0 (Public)
    target_user_id = current_user.id
    if is_public:
        target_user_id = 0
        logger.info(f"用户 {current_user.id} 请求上传文件到公共文件夹 (User 0)")

    logger.info(f"接收到文件上传请求: {file.filename} -> 文件夹: {folder_name} (Target User: {target_user_id})")
    
    # if agentUserId is present, we log a warning or debug message, but we DO NOT use it.
    if agentUserId is not None:
        logger.debug(f"Frontend provided agentUserId={agentUserId}, ignoring it in favor of token/is_public logic.")

    try:
        # [修改] 不再强制添加时间戳，保持原文件名
        # 但为了防止覆盖，如果文件已存在，则自动添加序号 (1), (2) 等
        original_filename = file.filename
        name, ext = os.path.splitext(original_filename)
        
        # 路径
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # generate_report
        # 修改为: inferrence/{target_user_id}/{folder_name}/
        infer_dir = os.path.join(base_dir, "inferrence", str(target_user_id), folder_name)
        os.makedirs(infer_dir, exist_ok=True)
        
        # 碰撞检测与重命名逻辑
        new_filename = original_filename
        file_path = os.path.join(infer_dir, new_filename)
        
        counter = 1
        while os.path.exists(file_path):
            new_filename = f"{name}({counter}){ext}"
            file_path = os.path.join(infer_dir, new_filename)
            counter += 1
            
        if new_filename != original_filename:
            logger.info(f"文件名冲突，自动重命名为: {new_filename}")
        
        # -------------------------------------------------------
        # 自动修复：确保数据库中有该文件夹记录
        # -------------------------------------------------------
        try:
            # 尝试添加文件夹（add_folder 内部有幂等检查，如果已存在会直接返回 ID）
            # 注意：这里使用 target_user_id
            folder_id = add_folder(folder_name, target_user_id)
            logger.info(f"确保文件夹记录存在: {folder_name} (ID: {folder_id})")
        except Exception as db_err:
            # 如果是 User 3 尝试往 User 0 的文件夹传东西，但 DB 报错，可能是因为 User 0 还没这个文件夹
            # 且当前逻辑允许创建。如果报错 IntegrityError，说明 add_folder 内部处理不够完美，但我们已在 add_folder 做了 try-catch
            logger.warning(f"自动创建文件夹记录失败 (非致命): {db_err}")
        # -------------------------------------------------------
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"文件上传成功: {file_path}")
        return {
            "status_code": 0,
            "message": "上传成功",
            "data": {"file_path": file_path, "file_name": new_filename}
        }
    except Exception as e:
        logger.error(f"文件上传失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"上传失败: {str(e)}",
            "data": {}
        }



# ===========================
# 查询提示词接口
# ===========================
@router.post("/query_prompts/")
def query_prompts_endpoint(req: QueryPrompts):
    logger.info(f"接收到查询提示词请求: {req.folder_name}")
    try:
        prompts = get_prompts_by_folder_name(req.folder_name)
        return {
            "status_code": 0,
            "message": "查询成功",
            "data": prompts
        }
    except Exception as e:
        logger.error(f"查询提示词失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"查询失败: {str(e)}",
            "data": []
        }

# ===========================
# 查询 LLM 模型配置接口
# ===========================
@router.post("/query_llm_models/")
def query_llm_models_endpoint(req: QueryLLMModels, current_user: dict = Depends(require_user)):
    logger.info(f"接收到查询 LLM 模型请求: {req}, 用户: {current_user.username}")
    try:
        # 使用 Token 解析出的 user_id
        user_id = current_user.id
        # 传递 user_id 以过滤模型 (req.agentUserId 被忽略)
        models = get_model_names(user_id=user_id)
        return {
            "status_code": 0,
            "message": "查询成功",
            "status": req.status,
            "data": models
        }
    except Exception as e:
        logger.error(f"查询 LLM 模型配置失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"查询失败: {str(e)}",
            "status": req.status,
            "data": []
        }


# ===========================
# 健康检查
# ===========================
@router.get("/health")
def health_check():
    return {"status": "healthy"}