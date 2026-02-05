import logging
import os
import shutil
import uuid
import zipfile
import threading
import json
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, status
from utils.zzp.import_doc_to_db import process_document, scan_docx_structure
from routers.dependencies import require_user, CurrentUser
from utils.redis_client import get_redis_client

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

class TaskStatusManager:
    """
    Manages task status persistence, switching between Redis and Memory based on configuration.
    Handles JSON serialization for complex fields.
    """
    def __init__(self):
        self.memory_store = {}
        self.redis_prefix = os.getenv("REDIS_PREFIX", "langextract")
        # Check specific feature flag first, then general enabled flag
        self.redis_enabled = (os.getenv("REDIS_TASK_STATUS_ENABLED", "0") == "1") and \
                             (os.getenv("REDIS_ENABLED", "0") == "1")
        self.ttl = 24 * 60 * 60  # 24 hours
        self.env = os.getenv("ENV", "dev")
        
        if self.redis_enabled:
            logger.info("🚀 TaskStatusManager: Redis persistence ENABLED")
        else:
            logger.info("⚠️ TaskStatusManager: Using In-Memory Store (Redis disabled)")

    def _get_key(self, user_id, task_id):
        return f"{self.redis_prefix}:{self.env}:task:import:{user_id}:{task_id}"

    def _get_redis(self):
        try:
            client = get_redis_client()
            if client:
                return client
        except Exception as e:
            logger.error(f"Failed to get Redis client: {e}")
        return None

    def update(self, task_id, data, user_id):
        """
        Update task status.
        data: dict containing fields to update.
        user_id: required for key generation in Redis mode.
        """
        # 1. Try Redis if enabled
        if self.redis_enabled:
            client = self._get_redis()
            if client:
                try:
                    key = self._get_key(user_id, task_id)
                    # Prepare data for HSET (serialize complex types)
                    processed_data = {}
                    for k, v in data.items():
                        if isinstance(v, (dict, list)):
                            processed_data[k] = json.dumps(v, ensure_ascii=False)
                        elif v is None:
                            pass # Skip None
                        else:
                            processed_data[k] = str(v)
                    
                    if processed_data:
                        client.hset(key, mapping=processed_data)
                        client.expire(key, self.ttl)
                    return
                except Exception as e:
                    logger.error(f"Redis update failed for task {task_id}: {e}")
                    # Fallback to memory? 
                    # Ideally we should stick to one source of truth.
                    # If Redis fails, we might lose state updates.
                    # For now, let's just log error to avoid blocking the process.

        # 2. Memory Fallback (or Primary if Redis disabled)
        if task_id not in self.memory_store:
             self.memory_store[task_id] = {}
        
        # Ensure owner_user_id is set in memory for consistency
        if "owner_user_id" not in self.memory_store[task_id] and user_id:
            self.memory_store[task_id]["owner_user_id"] = user_id
            
        self.memory_store[task_id].update(data)

    def get(self, task_id, user_id):
        """
        Retrieve task status.
        user_id: required to find the key in Redis mode.
        """
        # 1. Try Redis
        if self.redis_enabled:
            client = self._get_redis()
            if client:
                try:
                    key = self._get_key(user_id, task_id)
                    data = client.hgetall(key)
                    if data:
                        # Deserialize
                        result = {}
                        for k, v in data.items():
                            if k in ['structure', 'result']: # Fields known to be JSON
                                try:
                                    result[k] = json.loads(v)
                                except:
                                    result[k] = v
                            elif k in ['progress', 'owner_user_id']:
                                try:
                                    result[k] = int(v)
                                except:
                                    result[k] = v
                            else:
                                result[k] = v
                        return result
                    else:
                        return None # Not found
                except Exception as e:
                    logger.error(f"Redis get failed for task {task_id}: {e}")
        
        # 2. Memory Fallback
        return self.memory_store.get(task_id)

    def set_initial(self, task_id, data, user_id):
        """Initialize task data (clears previous if any)"""
        if self.redis_enabled:
            client = self._get_redis()
            if client:
                try:
                    key = self._get_key(user_id, task_id)
                    client.delete(key) # Clear old
                except:
                    pass
        
        if task_id in self.memory_store:
            del self.memory_store[task_id]
            
        self.update(task_id, data, user_id)

# Initialize Manager
task_manager = TaskStatusManager()

# 并发控制：限制同时进行的文档处理任务数量
# 服务器配置：251GB 内存，80 核 CPU。
# 即使配置很高，为了防止极端并发导致 OOM，设置一个安全上限。
# 假设每个大文件处理消耗 2-4GB 内存，20 个并发约占用 40-80GB，非常安全。
MAX_CONCURRENT_TASKS = 20
task_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

def background_process_wrapper(task_id: str, type_name: str, report_name: str, file_path: str, user_id: int):
    """后台任务包装器，用于更新任务状态并执行处理"""
    acquired = False
    
    # 定义进度回调函数
    def update_progress(percent: int, msg: str):
        # 使用 task_manager 更新状态
        task_manager.update(task_id, {
            "progress": percent,
            "message": msg
        }, user_id)

    try:
        # 尝试获取信号量，如果满了则等待
        logger.info(f"⏳ [任务等待] ID: {task_id} 正在等待执行槽位 (当前并发限制: {MAX_CONCURRENT_TASKS})...")
        task_manager.update(task_id, {
            "status": "queued", 
            "message": "正在排队等待处理资源...", 
            "progress": 5
        }, user_id)
        
        task_semaphore.acquire()
        acquired = True
        
        logger.info(f"▶️ [任务开始] ID: {task_id} 获取到执行槽位")
        task_manager.update(task_id, {
            "status": "processing", 
            "message": "正在后台处理中...", 
            "progress": 10
        }, user_id)

        # 1. 后台扫描文档结构 (优化响应速度)
        try:
            logger.info(f"📑 [后台任务] ID: {task_id} 开始扫描文档结构...")
            doc_structure = scan_docx_structure(file_path)
            # 更新状态中的结构信息，供前端轮询获取
            task_manager.update(task_id, {
                "structure": doc_structure,
                "progress": 20
            }, user_id)
            logger.info(f"📑 [后台任务] ID: {task_id} 结构扫描完成，共 {len(doc_structure)} 章节")
        except Exception as e:
            logger.warning(f"⚠️ [后台任务] ID: {task_id} 结构扫描失败: {e}")
        
        # 调用核心处理逻辑，传入回调和 user_id
        is_success, result_msg = process_document(type_name, report_name, file_path, progress_callback=update_progress, user_id=user_id)
        
        if is_success:
            task_manager.update(task_id, {
                "status": "success", 
                "message": result_msg, 
                "progress": 100,
                "result": {
                    "report_generation_status": 0,
                    "report_generation_condition": result_msg,
                    "reportName": report_name,
                    "reportType": type_name,
                    "task_id": task_id
                }
            }, user_id)
            logger.info(f"✅ [异步任务完成] ID: {task_id} {result_msg}")
        else:
            task_manager.update(task_id, {
                "status": "failed", 
                "message": f"导入失败：{result_msg}", 
                "progress": 100
            }, user_id)
            logger.warning(f"⚠️ [异步任务失败] ID: {task_id} {result_msg}")
            
    except Exception as e:
        logger.error(f"❌ [异步任务异常] ID: {task_id} {e}", exc_info=True)
        
        error_msg = str(e)
        user_friendly_msg = f"系统处理异常: {error_msg}"
        error_code = "UNKNOWN_ERROR"
        
        if "There is no item named" in error_msg and "in the archive" in error_msg:
             user_friendly_msg = "文件似乎已损坏，内部结构缺失，请尝试修复文档或重新保存后再上传。"
             error_code = "DOCX_CORRUPTED"
             logger.info(f"ℹ️ [错误信息转换] 将原始错误转换为友好提示: {user_friendly_msg}")
        elif "BadZipFile" in error_msg or "zipfile" in str(type(e)).lower():
             user_friendly_msg = "文件格式错误或已损坏，无法解析。请确认文件是否为有效的 .docx 文档。"
             error_code = "DOCX_CORRUPTED"
        
        task_manager.update(task_id, {
            "status": "error", 
            "message": user_friendly_msg, 
            "progress": 100,
            "error_code": error_code
        }, user_id)
    finally:
        if acquired:
            task_semaphore.release()
            logger.info(f"⏹️ [任务释放] ID: {task_id} 释放执行槽位")
            
        # 清理临时文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"🧹 已清理临时文件: {file_path}")
            except Exception as cleanup_error:
                logger.error(f"清理临时文件失败: {cleanup_error}")

@router.get("/check_import_status/{task_id}")
def check_import_status(task_id: str, current_user: CurrentUser = Depends(require_user)):
    """查询导入任务状态 (需登录，且只能查自己的任务)"""
    # 使用 TaskManager 获取状态 (Redis/Memory)
    # 注意: Redis key 包含 user_id，所以只能查询当前用户的任务
    status_info = task_manager.get(task_id, current_user.id)
    
    if not status_info:
        return {"status": "unknown", "message": "任务不存在"}
    
    # 再次校验 owner_id (虽然 key 隔离已保证，但双重保险)
    owner_id = status_info.get("owner_user_id")
    current_user_id = current_user.id
    if owner_id is not None and str(owner_id) != str(current_user_id):
        logger.warning(f"⚠️ [越权访问] User {current_user_id} 尝试查看 User {owner_id} 的任务 {task_id}")
        return {"status": "unknown", "message": "任务不存在"}
        
    return status_info

@router.post("/Import_Doc/")
async def Import_Doc_endpoint(  # 改为async
    background_tasks: BackgroundTasks,
    task_id: str = Form(...),
    status: int = Form(...),
    agentUserId: int = Form(...),
    type_name: str = Form(...),
    report_name: str = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_user)
):
    # 优先使用 Token 中的用户 ID
    user_id = current_user.id
    logger.info(f'🚀 [任务接收] ID: {task_id}, User: {user_id} (Claimed: {agentUserId}), 报告: {report_name}, 类型: {type_name}, 模式: 异步处理')

    # 1. 路径准备
    current_dir = os.getcwd()
    temp_dir = os.path.join(current_dir, "temp_uploads")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # 2. 提取并验证文件扩展名
    original_filename = file.filename
    file_ext = os.path.splitext(original_filename)[1].lower()
    
    # 3. 严格校验文件格式，只接受.docx
    if file_ext != '.docx':
        return {
            "report_generation_status": 1,
            "report_generation_condition": "系统仅支持标准 OpenXML 格式的 .docx 文档，请勿使用旧版 .doc 或手动修改后缀名。",
            "task_id": task_id,
            "error_code": "UNSUPPORTED_FILE_FORMAT"
        }

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    temp_file_path = os.path.join(temp_dir, unique_filename)

    try:
        # 4. 重置文件指针，确保从开头读取
        await file.seek(0)

        # 5. 保存文件 (使用分块写入以支持大文件)
        with open(temp_file_path, "wb") as buffer:
            # 使用分块写入避免大文件内存溢出
            chunk_size = 8192
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)
        
        # 6. 强制将数据刷入磁盘（解决IO竞争问题）
        with open(temp_file_path, "ab") as buffer:
            buffer.flush()
            os.fsync(buffer.fileno())
        
        file_size = os.path.getsize(temp_file_path)
        logger.info(f"📂 文件已接收: {temp_file_path}, 大小: {file_size / 1024 / 1024:.2f} MB")

        if file_size == 0:
            os.remove(temp_file_path)
            return {"report_generation_status": 1, "report_generation_condition": "文件大小为0", "task_id": task_id}
        
        # 7. 严格的文件格式校验 - 在强制刷盘后进行
        # 首先检查是否为有效的 Zip 文件 (docx 本质是 zip)
        if not zipfile.is_zipfile(temp_file_path):
             logger.warning(f"⚠️ 文件格式校验失败: {temp_file_path} 不是有效的 zip/docx")
             os.remove(temp_file_path)
             return {
                 "report_generation_status": 1,
                 "report_generation_condition": "文件已损坏或不是有效的 Word (.docx) 文档",
                 "task_id": task_id,
                 "error_code": "DOCX_CORRUPTED_OR_INVALID"
             }
        
        # 8. 进一步验证是否包含docx必要结构
        try:
            with zipfile.ZipFile(temp_file_path, 'r') as zip_file:
                # 检查是否存在必要的docx文件
                required_files = ['word/document.xml', '[Content_Types].xml', 'word/_rels/document.xml.rels']
                missing_files = [f for f in required_files if f not in zip_file.namelist()]
                
                if missing_files:
                    logger.warning(f"⚠️ docx文件缺少必要组件: {missing_files}")
                    os.remove(temp_file_path)
                    return {
                        "report_generation_status": 1,
                        "report_generation_condition": "文档结构不完整，可能已损坏",
                        "task_id": task_id,
                        "error_code": "DOCX_STRUCTURE_INCOMPLETE"
                    }
        except zipfile.BadZipFile:
            logger.warning(f"⚠️ 文件格式校验失败: {temp_file_path} 无法打开为zip文件")
            os.remove(temp_file_path)
            return {
                "report_generation_status": 1,
                "report_generation_condition": "文件已损坏或不是有效的 Word (.docx) 文档",
                "task_id": task_id,
                "error_code": "DOCX_CORRUPTED_OR_INVALID"
            }

        # 9. 初始化任务状态 (记录 owner_user_id)
        task_manager.set_initial(task_id, {
            "status": "pending",
            "message": "已进入处理队列",
            "progress": 0,
            "owner_user_id": user_id
        }, user_id)

        # 10. 提交后台任务 (立即响应前端)
        # 传入 user_id
        background_tasks.add_task(background_process_wrapper, task_id, type_name, report_name, temp_file_path, user_id)

        # 11. 立即返回
        return {
            "report_generation_status": 0,
            "report_generation_condition": "文件上传成功，正在后台处理中，请通过 /check_import_status 查询进度",
            "status": status,
            "task_id": task_id,
            "mode": "async"
        }

    except Exception as e:
        logger.error(f"❌ 接收文件异常: {e}", exc_info=True)
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass  # 如果清理失败，忽略
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"接收异常: {str(e)}",
            "task_id": task_id
        }

@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}