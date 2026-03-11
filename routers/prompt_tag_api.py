"""
标签管理路由
包含标签创建、删除、查询等功能
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from routers.dependencies import require_user, CurrentUser
from routers.prompt_models import (
    CreateTagRequest, 
    TagTreeNode, 
    DepartmentNode,
    UpdateTagDepartmentRequest,
    AddTagToPromptRequest,
)
from routers.prompt_service import PromptSaveService
from utils.lyf.db_async_config import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Prompt-Tags"])


def build_tree(items: List[dict], parent_id: int = 0) -> List[dict]:
    """构建树结构"""
    nodes = []
    for item in items:
        if item.get("parent_id", 0) == parent_id:
            children = build_tree(items, item["id"])
            node = {
                "id": item["id"],
                "tag_name": item.get("tag_name") or item.get("name"),
                "type": item.get("type"),
                "parent_id": item.get("parent_id", 0),
                "icon_code": item.get("icon_code"),
                "color": item.get("color"),
                "department_id": item.get("department_id"),
                "children": children,
            }
            nodes.append(node)
    return nodes


@router.post("/tags/personal")
async def create_personal_tag(
    request: CreateTagRequest,
    current_user: CurrentUser = Depends(require_user),
):
    """创建个人标签"""
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        service = PromptSaveService(session)
        try:
            tag_id = await service.create_personal_tag(user_id, request)
            await session.commit()
            
            return {
                "code": 0,
                "message": "创建成功",
                "data": {"tag_id": tag_id, "tag_name": request.tag_name}
            }
        except Exception as e:
            await session.rollback()
            logger.error(f"[PromptTag] Error creating tag: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"创建标签失败: {str(e)}")


@router.get("/tags/tree")
async def get_tags_tree(
    current_user: CurrentUser = Depends(require_user),
    include_personal: bool = Query(True, description="是否包含个人标签"),
    include_all_public: bool = Query(False, description="是否包含所有公开标签（用于提示词广场）"),
):
    """
    获取标签树（系统标签+可选个人标签+可选所有公开标签）
    
    tags表中存的是部门等系统标签，type=1
    个人标签type=2
    
    参数说明:
    - include_personal: 是否包含当前用户创建的个人标签
    - include_all_public: 是否包含所有已关联部门的公开标签（用于提示词广场显示所有公开标签）
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tag_name, type, parent_id, icon_code, color, department_id
                FROM ai_prompt_tags
                WHERE type = 1
                ORDER BY sort_order, id
            """)
        )
        system_tags = [dict(row) for row in result.mappings().all()]
        
        personal_tags = []
        if include_personal:
            result = await session.execute(
                text("""
                    SELECT id, tag_name, type, parent_id, icon_code, color, department_id
                    FROM ai_prompt_tags
                    WHERE type = 2 AND user_id = :user_id
                    ORDER BY id
                """),
                {"user_id": user_id}
            )
            personal_tags = [dict(row) for row in result.mappings().all()]
        
        # 获取所有已关联部门的公开标签（用于提示词广场）
        public_tags = []
        if include_all_public:
            result = await session.execute(
                text("""
                    SELECT id, tag_name, type, parent_id, icon_code, color, department_id
                    FROM ai_prompt_tags
                    WHERE type = 2 AND department_id IS NOT NULL
                    ORDER BY id
                """)
            )
            public_tags = [dict(row) for row in result.mappings().all()]
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "system_tags": build_tree(system_tags),
                "personal_tags": build_tree(personal_tags),
                "public_tags": build_tree(public_tags),
            }
        }


@router.get("/departments/tree")
async def get_departments_tree(
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取部门树
    
    从ai_prompt_tags表中获取type=1的记录作为部门
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tag_name as name, parent_id, department_id
                FROM ai_prompt_tags
                WHERE type = 1
                ORDER BY sort_order, id
            """)
        )
        departments = [dict(row) for row in result.mappings().all()]
        
        def build_dept_tree(depts: List[dict], parent_id: int = 0) -> List[dict]:
            nodes = []
            for dept in depts:
                if dept.get("parent_id", 0) == parent_id:
                    children = build_dept_tree(depts, dept["id"])
                    node = {
                        "id": dept["id"],
                        "name": dept["name"],
                        "parent_id": dept.get("parent_id", 0),
                        "department_id": dept.get("department_id"),
                        "children": children,
                    }
                    nodes.append(node)
            return nodes
        
        return {
            "code": 0,
            "message": "success",
            "data": build_dept_tree(departments)
        }


@router.put("/tags/{tag_id}/department")
async def update_tag_department(
    tag_id: int,
    request: UpdateTagDepartmentRequest,
    current_user: CurrentUser = Depends(require_user),
):
    """
    更新个人标签的关联部门

    用途：当用户创建标签后保存公开提示词时，将标签关联到对应部门
    权限：只能更新自己创建的个人标签（type=2）
    """
    user_id = int(current_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tag_name, type, user_id, department_id
                FROM ai_prompt_tags
                WHERE id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        tag = result.mappings().fetchone()

        if not tag:
            raise HTTPException(status_code=404, detail="标签不存在")
        if tag["type"] != 2:
            raise HTTPException(status_code=403, detail="只能更新个人标签的部门")
        if int(tag["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="无权更新该标签")

        if request.department_id and request.department_id != 0:
            dept_result = await session.execute(
                text("SELECT id FROM ai_prompt_tags WHERE id = :dept_id AND type = 1"),
                {"dept_id": request.department_id}
            )
            if not dept_result.scalar():
                raise HTTPException(status_code=400, detail="部门不存在")

        await session.execute(
            text("""
                UPDATE ai_prompt_tags
                SET department_id = :department_id
                WHERE id = :tag_id
            """),
            {"tag_id": tag_id, "department_id": request.department_id}
        )
        await session.commit()

        logger.info(f"[PromptTag] Updated tag {tag_id} department_id to {request.department_id} by user {user_id}")

        return {
            "code": 0,
            "message": "更新成功",
            "data": {
                "tag_id": tag_id,
                "department_id": request.department_id
            }
        }


@router.delete("/tags/{tag_id}")
async def delete_personal_tag(
    tag_id: int,
    delete_prompts: bool = Query(False, description="是否同步删除关联的提示词"),
    current_user: CurrentUser = Depends(require_user),
):
    """
    删除个人标签
    
    权限：只能删除自己创建的个人标签（type=2）
    行为：
    - 默认只删除标签，自动移除与提示词的关联关系
    - 如果 delete_prompts=true，则同时删除关联的提示词
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tag_name, type, user_id
                FROM ai_prompt_tags
                WHERE id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        tag = result.mappings().fetchone()
        
        if not tag:
            raise HTTPException(status_code=404, detail="标签不存在")
        if tag["type"] != 2:
            raise HTTPException(status_code=403, detail="只能删除个人标签")
        if int(tag["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="无权删除该标签")
        
        result = await session.execute(
            text("""
                SELECT prompt_id
                FROM ai_prompt_tag_relation
                WHERE tag_id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        related_prompt_ids = [row["prompt_id"] for row in result.mappings().all()]
        
        deleted_prompts = 0
        if delete_prompts and related_prompt_ids:
            result = await session.execute(
                text("""
                    UPDATE ai_prompts
                    SET status = 0, update_time = NOW()
                    WHERE id IN :prompt_ids AND user_id = :user_id
                """),
                {"prompt_ids": tuple(related_prompt_ids), "user_id": user_id}
            )
            deleted_prompts = result.rowcount
            
            await session.execute(
                text("""
                    DELETE FROM ai_prompt_tag_relation
                    WHERE prompt_id IN :prompt_ids
                """),
                {"prompt_ids": tuple(related_prompt_ids)}
            )
        else:
            await session.execute(
                text("DELETE FROM ai_prompt_tag_relation WHERE tag_id = :tag_id"),
                {"tag_id": tag_id}
            )
        
        await session.execute(
            text("DELETE FROM ai_prompt_tags WHERE id = :tag_id"),
            {"tag_id": tag_id}
        )
        await session.commit()
        
        logger.info(f"[PromptTag] Deleted personal tag {tag_id} by user {user_id}, delete_prompts={delete_prompts}, deleted_prompts={deleted_prompts}")
        
        return {
            "code": 0,
            "message": "删除成功",
            "data": {
                "tag_id": tag_id,
                "deleted_prompts": deleted_prompts
            }
        }


@router.delete("/tags/{tag_id}/public")
async def delete_public_tag(
    tag_id: int,
    delete_prompts: bool = Query(False, description="是否同步删除关联的提示词"),
    current_user: CurrentUser = Depends(require_user),
):
    """
    删除自己创建的公共标签
    
    权限：只能删除自己创建的公共标签（type=1且user_id不为null）
    限制：系统预设标签（user_id=null）不可删除
    """
    user_id = int(current_user.id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tag_name, type, user_id
                FROM ai_prompt_tags
                WHERE id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        tag = result.mappings().fetchone()
        
        if not tag:
            raise HTTPException(status_code=404, detail="标签不存在")
        if tag["type"] != 1:
            raise HTTPException(status_code=403, detail="只能删除公共标签")
        if tag["user_id"] is None:
            raise HTTPException(status_code=403, detail="系统预设标签不可删除")
        if int(tag["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="只能删除自己创建的公共标签")
        
        result = await session.execute(
            text("""
                SELECT prompt_id
                FROM ai_prompt_tag_relation
                WHERE tag_id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        related_prompt_ids = [row["prompt_id"] for row in result.mappings().all()]
        
        deleted_prompts = 0
        if delete_prompts and related_prompt_ids:
            result = await session.execute(
                text("""
                    UPDATE ai_prompts
                    SET status = 0, update_time = NOW()
                    WHERE id IN :prompt_ids AND user_id = :user_id
                """),
                {"prompt_ids": tuple(related_prompt_ids), "user_id": user_id}
            )
            deleted_prompts = result.rowcount
            
            await session.execute(
                text("""
                    DELETE FROM ai_prompt_tag_relation
                    WHERE prompt_id IN :prompt_ids
                """),
                {"prompt_ids": tuple(related_prompt_ids)}
            )
        else:
            await session.execute(
                text("DELETE FROM ai_prompt_tag_relation WHERE tag_id = :tag_id"),
                {"tag_id": tag_id}
            )
        
        await session.execute(
            text("DELETE FROM ai_prompt_tags WHERE id = :tag_id"),
            {"tag_id": tag_id}
        )
        await session.commit()
        
        logger.info(f"[PromptTag] Deleted public tag {tag_id} by user {user_id}, delete_prompts={delete_prompts}, deleted_prompts={deleted_prompts}")
        
        return {
            "code": 0,
            "message": "删除成功",
            "data": {
                "tag_id": tag_id,
                "deleted_prompts": deleted_prompts
            }
        }


@router.post("/{prompt_id}/tags")
async def add_tag_to_prompt(
    prompt_id: int,
    request: AddTagToPromptRequest,
    current_user: CurrentUser = Depends(require_user),
):
    """
    为提示词添加标签（拖拽功能）

    权限：只能为自己创建的提示词添加标签
    """
    user_id = int(current_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, user_id, title
                FROM ai_prompts
                WHERE id = :prompt_id AND status = 1
            """),
            {"prompt_id": prompt_id}
        )
        prompt = result.mappings().fetchone()

        if not prompt:
            raise HTTPException(status_code=404, detail="提示词不存在")

        if int(prompt["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="无权为该提示词添加标签")

        result = await session.execute(
            text("""
                SELECT id, tag_name, type, user_id
                FROM ai_prompt_tags
                WHERE id = :tag_id
            """),
            {"tag_id": request.tag_id}
        )
        tag = result.mappings().fetchone()

        if not tag:
            raise HTTPException(status_code=404, detail="标签不存在")

        if tag["type"] == 2 and int(tag["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="无权使用该标签")

        result = await session.execute(
            text("""
                SELECT 1 FROM ai_prompt_tag_relation
                WHERE prompt_id = :prompt_id AND tag_id = :tag_id
            """),
            {"prompt_id": prompt_id, "tag_id": request.tag_id}
        )
        if result.scalar():
            return {
                "code": 0,
                "message": "标签已关联",
                "data": {"prompt_id": prompt_id, "tag_id": request.tag_id}
            }

        await session.execute(
            text("""
                INSERT INTO ai_prompt_tag_relation (prompt_id, tag_id)
                VALUES (:prompt_id, :tag_id)
            """),
            {"prompt_id": prompt_id, "tag_id": request.tag_id}
        )

        await session.commit()

        logger.info(f"[PromptTag] Added tag {request.tag_id} to prompt {prompt_id} by user {user_id}")

        return {
            "code": 0,
            "message": "标签添加成功",
            "data": {
                "prompt_id": prompt_id,
                "tag_id": request.tag_id,
                "tag_name": tag["tag_name"]
            }
        }


@router.delete("/{prompt_id}/tags/{tag_id}")
async def remove_tag_from_prompt(
    prompt_id: int,
    tag_id: int,
    current_user: CurrentUser = Depends(require_user),
):
    """
    从提示词移除标签

    权限：只能为自己创建的提示词移除标签
    """
    user_id = int(current_user.id)

    async with AsyncSessionLocal() as session:
        # 检查提示词是否存在且属于当前用户
        result = await session.execute(
            text("""
                SELECT id, user_id, title
                FROM ai_prompts
                WHERE id = :prompt_id AND status = 1
            """),
            {"prompt_id": prompt_id}
        )
        prompt = result.mappings().fetchone()

        if not prompt:
            raise HTTPException(status_code=404, detail="提示词不存在")

        if int(prompt["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="无权为该提示词移除标签")

        # 检查标签是否存在
        result = await session.execute(
            text("""
                SELECT id, tag_name, type, user_id
                FROM ai_prompt_tags
                WHERE id = :tag_id
            """),
            {"tag_id": tag_id}
        )
        tag = result.mappings().fetchone()

        if not tag:
            raise HTTPException(status_code=404, detail="标签不存在")

        # 检查关联关系是否存在
        result = await session.execute(
            text("""
                SELECT 1 FROM ai_prompt_tag_relation
                WHERE prompt_id = :prompt_id AND tag_id = :tag_id
            """),
            {"prompt_id": prompt_id, "tag_id": tag_id}
        )
        if not result.scalar():
            return {
                "code": 0,
                "message": "标签未关联",
                "data": {"prompt_id": prompt_id, "tag_id": tag_id}
            }

        # 删除关联关系
        await session.execute(
            text("""
                DELETE FROM ai_prompt_tag_relation
                WHERE prompt_id = :prompt_id AND tag_id = :tag_id
            """),
            {"prompt_id": prompt_id, "tag_id": tag_id}
        )

        await session.commit()

        logger.info(f"[PromptTag] Removed tag {tag_id} from prompt {prompt_id} by user {user_id}")

        return {
            "code": 0,
            "message": "标签移除成功",
            "data": {
                "prompt_id": prompt_id,
                "tag_id": tag_id
            }
        }
