import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from utils.zzp.query_catalogue_type import get_categories_and_types
from utils.zzp.insert_type import add_new_report_type
from utils.zzp.delete_type import delete_report_type_logic
from routers.dependencies import require_user, CurrentUser

#查询章节超市和报告类型进行返回，并且添加报告类型
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

class QueryCatalogue(BaseModel):
    task_id: str
    status: int
    agentUserId: int

class InsertType(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    type_name: str

class DeleteType(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    type_name: str

@router.post("/Query_catalogue/")
def Query_catalogue_endpoint(report: QueryCatalogue, current_user: CurrentUser = Depends(require_user)):
    logger.info(f'接收到的参数：{report}')
    user_id = current_user.id
    logger.info(f"Current User ID: {user_id}")

    try:
        # ✅ 关键修改：这里使用两个变量接收
        category_list, type_list = get_categories_and_types(user_id=user_id)
        
        # 判断结果 (只要任意一个有数据，或者都为空但没报错，都视为成功)
        # 这里把两个列表拼装回字典给前端
        result_data = {
            "category_list": category_list,
            "type_list": type_list
        }
        
        if category_list or type_list:
            logger.info(f"✅ 查询成功")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "查询成功",
                "modul_list": result_data,     # 返回包含两个列表的字典
                "status": report.status
            }
        else:
            logger.info("⚠️ 未获取到任何数据")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "数据库中暂时没有数据",
                "modul_list": result_data,     # 即使是空的也要返回结构
                "status": report.status
            }

    except Exception as e:
        logger.error(f"❌ 查询模块失败: {e}", exc_info=True)
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"读取模块失败: {str(e)}",
            "status": report.status,
            "modul_list": {"category_list": [], "type_list": []}
        }
@router.post("/Add_Report_Type/")
def add_report_type_endpoint(req: InsertType, current_user: CurrentUser = Depends(require_user)):
    logger.info(f"请求添加类型: {req.type_name}")
    user_id = current_user.id

    # 1. 调用工具函数，获取 True 或 False
    is_success = add_new_report_type(req.type_name, user_id=user_id)

    # 2. 根据布尔值判断返回内容
    if is_success:
        # === 情况 A: 成功 (True) ===
        logger.info("✅ 添加成功")
        return {
            "report_generation_status": 0,         # 0 表示成功
            "report_generation_condition": "添加成功",
            "status": req.status,
            "data": { "type_name": req.type_name }
        }
    else:
        # === 情况 B: 失败/已存在 (False) ===
        logger.info("⚠️ 添加失败或已存在")
        return {
            "report_generation_status": 1,         # 1 表示有异常/重复
            "report_generation_condition": f"报告类型 '{req.type_name}' 已存在，请勿重复添加",
            "status": req.status,
            "data": {}
        }

@router.post("/Delete_Report_Type/")
def delete_report_type_endpoint(req: DeleteType, current_user: CurrentUser = Depends(require_user)):
    """
    删除报告类型接口
    权限：只能删除属于自己的类型；若类型下有关联报告，则禁止删除
    """
    logger.info(f"请求删除类型: {req.type_name}")
    user_id = current_user.id

    # 调用底层删除逻辑
    success, message = delete_report_type_logic(req.type_name, user_id=user_id)

    if success:
        logger.info(f"✅ 删除成功: {req.type_name}")
        return {
            "report_generation_status": 0,
            "report_generation_condition": "删除成功",
            "status": req.status,
            "data": { "type_name": req.type_name }
        }
    else:
        logger.warning(f"⚠️ 删除失败: {message}")
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"删除失败: {message}",
            "status": req.status,
            "data": {}
        }

@router.get("/health")
def health_check():
    return {"status": "healthy"}