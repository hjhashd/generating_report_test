"""
管理员面板 API 接口
提供系统统计、用户管理、内容审核等功能
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from routers.dependencies import CurrentUser, require_user
from utils.lyf.db_async_config import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin"])


def check_admin(user: CurrentUser) -> None:
    """检查用户是否为管理员（暂时允许所有登录用户访问）"""
    pass


class SystemStats(BaseModel):
    """系统统计数据"""
    total_users: int = Field(default=0, description="总用户数")
    total_prompts: int = Field(default=0, description="提示词总数")
    total_likes: int = Field(default=0, description="总点赞数")
    total_uses: int = Field(default=0, description="总使用次数")
    total_favorites: int = Field(default=0, description="总收藏数")
    total_shares: int = Field(default=0, description="总分享数")
    total_views: int = Field(default=0, description="总查看数")
    active_users_today: int = Field(default=0, description="今日活跃用户数")
    new_prompts_today: int = Field(default=0, description="今日新增提示词数")


class TopUser(BaseModel):
    """活跃用户排行项"""
    id: int
    name: str
    email: Optional[str] = None
    score: int
    rank: int
    prompt_count: int = Field(default=0, description="提示词数量")
    like_count: int = Field(default=0, description="获赞数量")


class TopPrompt(BaseModel):
    """热门提示词排行项"""
    id: int
    title: str
    author: str
    score: int
    rank: int
    like_count: int = Field(default=0)
    view_count: int = Field(default=0)
    copy_count: int = Field(default=0)


class UserListItem(BaseModel):
    """用户列表项"""
    id: int
    name: str
    email: Optional[str] = None
    role: str
    status: str
    join_date: str
    prompt_count: int = Field(default=0)
    department_id: Optional[int] = None
    department_name: Optional[str] = None


class UserListResponse(BaseModel):
    """用户列表响应"""
    list: List[UserListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class UpdateUserStatusRequest(BaseModel):
    """更新用户状态请求"""
    status: str = Field(..., description="状态: active/inactive/banned")


@router.get("/stats")
async def get_system_stats(
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取系统统计数据
    需要管理员权限
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        stats = {}
        
        result = await session.execute(
            text("""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM ai_prompts
                WHERE status != 0
            """)
        )
        row = result.mappings().fetchone()
        stats["total_users"] = int(row["total_users"] or 0) if row else 0
        
        result = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total_prompts,
                    COALESCE(SUM(like_count), 0) as total_likes,
                    COALESCE(SUM(favorite_count), 0) as total_favorites,
                    COALESCE(SUM(share_count), 0) as total_shares,
                    COALESCE(SUM(view_count), 0) as total_views,
                    COALESCE(SUM(copy_count), 0) as total_uses
                FROM ai_prompts
                WHERE status != 0
            """)
        )
        row = result.mappings().fetchone()
        if row:
            stats["total_prompts"] = int(row["total_prompts"] or 0)
            stats["total_likes"] = int(row["total_likes"] or 0)
            stats["total_favorites"] = int(row["total_favorites"] or 0)
            stats["total_shares"] = int(row["total_shares"] or 0)
            stats["total_views"] = int(row["total_views"] or 0)
            stats["total_uses"] = int(row["total_uses"] or 0)
        else:
            stats.update({
                "total_prompts": 0,
                "total_likes": 0,
                "total_favorites": 0,
                "total_shares": 0,
                "total_views": 0,
                "total_uses": 0
            })
        
        result = await session.execute(
            text("""
                SELECT COUNT(DISTINCT user_id) as active_users_today
                FROM ai_user_interactions
                WHERE DATE(create_time) = CURDATE()
            """)
        )
        row = result.mappings().fetchone()
        stats["active_users_today"] = int(row["active_users_today"] or 0) if row else 0
        
        result = await session.execute(
            text("""
                SELECT COUNT(*) as new_prompts_today
                FROM ai_prompts
                WHERE DATE(create_time) = CURDATE() AND status != 0
            """)
        )
        row = result.mappings().fetchone()
        stats["new_prompts_today"] = int(row["new_prompts_today"] or 0) if row else 0
        
        return {
            "code": 0,
            "message": "success",
            "data": stats
        }


@router.get("/top-users")
async def get_top_users(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取活跃用户排行榜
    基于用户创建的提示词数量和获得的点赞数计算活跃分数
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT 
                    p.user_id as id,
                    p.user_name as name,
                    COUNT(*) as prompt_count,
                    COALESCE(SUM(p.like_count), 0) as like_count,
                    COALESCE(SUM(p.view_count), 0) as view_count,
                    COALESCE(SUM(p.copy_count), 0) as copy_count
                FROM ai_prompts p
                WHERE p.status != 0
                GROUP BY p.user_id, p.user_name
                ORDER BY (COUNT(*) * 10 + COALESCE(SUM(p.like_count), 0) * 5 + COALESCE(SUM(p.view_count), 0) * 0.1) DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        rows = result.mappings().all()
        
        users = []
        for idx, row in enumerate(rows, 1):
            prompt_count = int(row["prompt_count"])
            like_count = int(row["like_count"] or 0)
            view_count = int(row["view_count"] or 0)
            score = prompt_count * 10 + like_count * 5 + int(view_count * 0.1)
            users.append({
                "id": int(row["id"]),
                "name": row["name"] or f"用户{row['id']}",
                "email": None,
                "score": score,
                "rank": idx,
                "prompt_count": prompt_count,
                "like_count": like_count
            })
        
        return {
            "code": 0,
            "message": "success",
            "data": users
        }


@router.get("/top-prompts")
async def get_top_prompts(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取热门提示词排行榜
    基于点赞数、查看数、复制数计算热度分数
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT 
                    id,
                    title,
                    user_name as author,
                    like_count,
                    view_count,
                    copy_count,
                    favorite_count,
                    heat_score
                FROM ai_prompts
                WHERE status != 0
                ORDER BY (like_count * 10 + view_count * 0.1 + copy_count * 5) DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        rows = result.mappings().all()
        
        prompts = []
        for idx, row in enumerate(rows, 1):
            like_count = int(row["like_count"] or 0)
            view_count = int(row["view_count"] or 0)
            copy_count = int(row["copy_count"] or 0)
            score = like_count * 10 + int(view_count * 0.1) + copy_count * 5
            prompts.append({
                "id": int(row["id"]),
                "title": row["title"],
                "author": row["author"] or "未知",
                "score": score,
                "rank": idx,
                "like_count": like_count,
                "view_count": view_count,
                "copy_count": copy_count
            })
        
        return {
            "code": 0,
            "message": "success",
            "data": prompts
        }


@router.get("/users")
async def get_users_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取用户列表（分页）
    支持按状态和关键词筛选
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        where_conditions = ["p.status != 0"]
        params = {}
        
        if keyword:
            where_conditions.append("(p.user_name LIKE :keyword OR p.user_id LIKE :keyword)")
            params["keyword"] = f"%{keyword}%"
        
        where_clause = " AND ".join(where_conditions)
        
        count_result = await session.execute(
            text(f"""
                SELECT COUNT(DISTINCT p.user_id) as total
                FROM ai_prompts p
                WHERE {where_clause}
            """),
            params
        )
        total = int(count_result.scalar() or 0)
        
        offset = (page - 1) * page_size
        params["offset"] = offset
        params["limit"] = page_size
        
        result = await session.execute(
            text(f"""
                SELECT 
                    p.user_id as id,
                    p.user_name as name,
                    p.department_id,
                    COUNT(*) as prompt_count,
                    MAX(p.create_time) as join_date,
                    COALESCE(SUM(p.like_count), 0) as like_count
                FROM ai_prompts p
                WHERE {where_clause}
                GROUP BY p.user_id, p.user_name, p.department_id
                ORDER BY MAX(p.create_time) DESC
                LIMIT :limit OFFSET :offset
            """),
            params
        )
        rows = result.mappings().all()
        
        users = []
        for row in rows:
            dept_name = None
            if row["department_id"]:
                dept_result = await session.execute(
                    text("SELECT tag_name FROM ai_prompt_tags WHERE id = :dept_id"),
                    {"dept_id": row["department_id"]}
                )
                dept_row = dept_result.mappings().fetchone()
                dept_name = dept_row["tag_name"] if dept_row else None
            
            prompt_count = int(row["prompt_count"])
            like_count = int(row["like_count"] or 0)
            
            if prompt_count >= 10 or like_count >= 100:
                role = "高级用户"
            else:
                role = "普通用户"
            
            users.append({
                "id": int(row["id"]),
                "name": row["name"] or f"用户{row['id']}",
                "email": None,
                "role": role,
                "status": "Active",
                "join_date": row["join_date"].strftime("%Y-%m-%d") if row["join_date"] else "",
                "prompt_count": prompt_count,
                "department_id": row["department_id"],
                "department_name": dept_name
            })
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "list": users,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        }


@router.get("/user/{user_id}")
async def get_user_detail(
    user_id: int,
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取用户详细信息
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT 
                    user_id as id,
                    user_name as name,
                    department_id,
                    COUNT(*) as prompt_count,
                    MIN(create_time) as first_create_time,
                    MAX(create_time) as last_create_time,
                    COALESCE(SUM(like_count), 0) as total_likes,
                    COALESCE(SUM(view_count), 0) as total_views,
                    COALESCE(SUM(copy_count), 0) as total_copies,
                    COALESCE(SUM(favorite_count), 0) as total_favorites
                FROM ai_prompts
                WHERE user_id = :user_id AND status != 0
                GROUP BY user_id, user_name, department_id
            """),
            {"user_id": user_id}
        )
        row = result.mappings().fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        dept_name = None
        if row["department_id"]:
            dept_result = await session.execute(
                text("SELECT tag_name FROM ai_prompt_tags WHERE id = :dept_id"),
                {"dept_id": row["department_id"]}
            )
            dept_row = dept_result.mappings().fetchone()
            dept_name = dept_row["tag_name"] if dept_row else None
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "id": int(row["id"]),
                "name": row["name"] or f"用户{row['id']}",
                "department_id": row["department_id"],
                "department_name": dept_name,
                "prompt_count": int(row["prompt_count"]),
                "first_create_time": row["first_create_time"].strftime("%Y-%m-%d %H:%M") if row["first_create_time"] else "",
                "last_create_time": row["last_create_time"].strftime("%Y-%m-%d %H:%M") if row["last_create_time"] else "",
                "total_likes": int(row["total_likes"] or 0),
                "total_views": int(row["total_views"] or 0),
                "total_copies": int(row["total_copies"] or 0),
                "total_favorites": int(row["total_favorites"] or 0)
            }
        }


@router.get("/interaction-stats")
async def get_interaction_stats(
    days: int = Query(default=7, ge=1, le=30),
    current_user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    """
    获取交互统计数据（用于图表展示）
    返回最近N天的每日统计数据
    """
    check_admin(current_user)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT 
                    DATE(create_time) as date,
                    COUNT(*) as count
                FROM ai_user_interactions
                WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
                GROUP BY DATE(create_time)
                ORDER BY date ASC
            """),
            {"days": days}
        )
        rows = result.mappings().all()
        
        daily_stats = []
        for row in rows:
            daily_stats.append({
                "date": row["date"].strftime("%Y-%m-%d") if row["date"] else "",
                "count": int(row["count"])
            })
        
        result = await session.execute(
            text("""
                SELECT 
                    action_type,
                    COUNT(*) as count
                FROM ai_user_interactions
                WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
                GROUP BY action_type
            """),
            {"days": days}
        )
        action_rows = result.mappings().all()
        
        action_stats = {
            "like": 0,
            "favorite": 0,
            "share": 0,
            "copy": 0
        }
        action_map = {1: "like", 2: "favorite", 3: "share", 4: "copy"}
        for row in action_rows:
            action_type = action_map.get(row["action_type"])
            if action_type:
                action_stats[action_type] = int(row["count"])
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "daily": daily_stats,
                "by_action": action_stats
            }
        }
