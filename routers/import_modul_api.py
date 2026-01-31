import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from utils.zzp.import_modul import get_report_json_structure
from routers.dependencies import require_user, CurrentUser

#通过类型和名称，将该名称下的模块进行导入到前端界面
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 请求参数模型
class ImportModul(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    type_name: str
    report_name: str

@router.post("/Import_modul/")
def Import_modul_endpoint(report: ImportModul, current_user: CurrentUser = Depends(require_user)):
    user_id = current_user.id
    logger.info(f'接收到的参数：{report}, User: {user_id}')

    try:
        # 1. 执行查询
        # 注意：这里返回的是一个字典对象 {'reportName':..., 'chapters':...}
        # 传入 user_id 进行过滤
        result_data = get_report_json_structure(report.type_name, report.report_name, user_id=user_id)
        
        # 2. 判断结果
        if result_data:
            logger.info(f"✅ 导入成功")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "查询成功",
                "modul_list": result_data,     # ✅ 修正：使用接收了查询结果的变量名
                "status": report.status
            }
        else:
            logger.info("⚠️ 未获取到任何数据")
            return {
                "report_generation_status": 0,
                "report_generation_condition": "数据库中暂时没有报告数据或无权访问",
                "modul_list": {},              # ✅ 建议：如果没查到，返回空字典 {} 可能比空列表 [] 更符合前端对该字段类型的预期（因为成功时是字典）
                "status": report.status
            }

    except Exception as e:
        logger.error(f"❌ 查询模块失败: {e}", exc_info=True)
        # 3. 发生异常时的返回
        return {
            "report_generation_status": 1,
            "report_generation_condition": f"读取模块失败: {str(e)}",
            "status": report.status,
            "modul_list": {} 
        }

@router.get("/health")
def health_check():
    """简单的健康检查"""
    return {"status": "healthy"}