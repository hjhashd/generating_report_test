import logging
import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# 配置导入路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 引入底层操作函数
from utils.lyf.query_prompts import get_latest_updated_prompts, search_prompts_by_keyword,get_hot_trending_prompts

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# ===========================
# 请求模型
# ===========================
class LatestPromptsQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    limit: Optional[int] = 5  # 最近更新多少条，默认 5

class SearchPromptsQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    keyword: str  # 用户输入关键字

class HotTrendingPromptsQuery(BaseModel):
    task_id: str
    status: int
    agentUserId: int
    limit: Optional[int] = 10  # 热门可设置条数，默认 10

# ===========================
# 新增接口：查询最近更新提示词
# ===========================

@router.post("/query_latest_prompts/")
def query_latest_prompts_endpoint(req: LatestPromptsQuery):
    logger.info(f"接收到查询最近更新提示词请求 | limit={req.limit}")
    try:
        prompts = get_latest_updated_prompts(limit=req.limit)
        return {
            "status_code": 0,
            "message": "查询成功",
            "status": req.status,
            "data": prompts
        }
    except Exception as e:
        logger.error(f"查询最近更新提示词失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"查询失败: {str(e)}",
            "status": req.status,
            "data": []
        }

# ===========================
# 新增接口：关键字模糊搜索提示词
# ===========================
@router.post("/search_prompts/")
def search_prompts_endpoint(req: SearchPromptsQuery):
    logger.info(f"接收到关键字模糊查询请求 | keyword={req.keyword}")
    try:
        prompts = search_prompts_by_keyword(req.keyword)
        return {
            "status_code": 0,
            "message": "查询成功",
            "status": req.status,
            "data": prompts
        }
    except Exception as e:
        logger.error(f"关键字模糊查询失败: {e}", exc_info=True)
        return {
            "status_code": 1,
            "message": f"查询失败: {str(e)}",
            "status": req.status,
            "data": []
        }

# ===========================
# 新增接口：热门趋势提示词
# ===========================
@router.post("/query_hot_trending_prompts/")
def get_hot_trending_prompts_endpoint(req: HotTrendingPromptsQuery):
    logger.info(f"接收到查询热门趋势提示词请求 | limit={req.limit}")
    try:
        # 调用之前写好的数据库函数
        prompts = get_hot_trending_prompts(limit=req.limit)
        
        return {
            "status_code": 0,
            "message": "查询成功",
            "status": req.status,
            "data": prompts
        }
    except Exception as e:
        logger.error(f"查询热门趋势提示词失败: {e}", exc_info=True)
        # 抛出标准的 HTTP 异常
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

# ===========================
# 健康检查
# ===========================
@router.get("/health")
def health_check():
    return {"status": "healthy"}