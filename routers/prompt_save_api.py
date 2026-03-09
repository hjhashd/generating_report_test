"""
Prompt Studio 保存提示词接口
支持从对话/编辑器保存提示词到提示词库，并关联标签、收敛会话
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from routers.dependencies import require_user, CurrentUser
from routers.prompt_models import SavePromptRequest, SavePromptResponse
from routers.prompt_service import PromptSaveService
from utils.lyf.db_async_config import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Prompt-Save"])


@router.get("/test")
async def test_prompt_save_router():
    """测试路由是否正常工作"""
    return {"code": 0, "message": "Prompt save router is working"}


@router.post("/save_from_studio", response_model=SavePromptResponse)
async def save_prompt_from_studio(
    request: SavePromptRequest,
    current_user: CurrentUser = Depends(require_user),
):
    """
    从Prompt Studio保存提示词
    
    支持新建和更新现有提示词，关联标签，收敛会话
    支持无会话模式（直接从编辑器/测试保存）
    """
    logger.info(f"save_from_studio called with data: {request.model_dump()}")
    user_id = int(current_user.id)
    
    # 判断是否为无会话模式
    is_standalone_mode = request.session_id is None
    
    async with AsyncSessionLocal() as session:
        service = PromptSaveService(session)
        
        try:
            # 有会话模式需要验证会话
            if not is_standalone_mode:
                logger.info(f"[PromptSave] Getting session meta for session_id={request.session_id}, user_id={user_id}")
                session_meta = await service.get_session_meta(request.session_id, user_id)
                if not session_meta:
                    logger.error(f"[PromptSave] Session not found or no permission: session_id={request.session_id}, user_id={user_id}")
                    raise HTTPException(status_code=404, detail="会话不存在或无权限")
                logger.info(f"[PromptSave] Session meta found: {session_meta}")
            
            # 获取内容
            content = request.content
            if not content:
                if is_standalone_mode:
                    raise HTTPException(status_code=400, detail="直接保存模式必须提供content")
                elif request.source_type == "reply":
                    if not request.message_id:
                        raise HTTPException(status_code=400, detail="保存AI回复时必须提供message_id")
                    logger.info(f"[PromptSave] Getting message content for message_id={request.message_id}, session_id={request.session_id}")
                    content = await service.get_message_content(
                        request.message_id, request.session_id
                    )
                    if not content:
                        logger.error(f"[PromptSave] Message not found: message_id={request.message_id}, session_id={request.session_id}")
                        raise HTTPException(status_code=404, detail="消息不存在")
                    logger.info(f"[PromptSave] Message content found, length={len(content) if content else 0}")
                else:
                    raise HTTPException(status_code=400, detail="保存编辑器内容时必须提供content")
            
            # 验证部门权限（公开提示词）
            if request.visibility == "plaza":
                if request.department_id is None:
                    raise HTTPException(status_code=400, detail="公开提示词必须选择部门")
                
                user_department_id = current_user.department_id
                ALL_DEPT_ID = 1  # "全部部门"在数据库中的ID
                
                if request.department_id == ALL_DEPT_ID:
                    pass
                elif user_department_id is None:
                    raise HTTPException(status_code=403, detail="您未绑定部门，无法发布公开提示词")
                elif request.department_id != user_department_id:
                    raise HTTPException(status_code=403, detail="您只能选择'全部部门'或'所属部门'")
                
                if request.department_id and request.department_id != ALL_DEPT_ID:
                    dept_result = await session.execute(
                        text("SELECT id FROM ai_prompt_tags WHERE id = :dept_id AND type = 1"),
                        {"dept_id": request.department_id}
                    )
                    if not dept_result.scalar():
                        raise HTTPException(status_code=400, detail="部门不存在")
            
            # 创建或更新提示词
            prompt_id, is_forked = await service.create_or_update_prompt(current_user, request, content)
            
            # 关联标签
            await service.update_tag_relations(prompt_id, request.tag_ids, user_id)
            
            # 关联目录
            await service.update_directory_relation(prompt_id, request.directory_id)
            
            # 有会话模式才收敛会话
            if not is_standalone_mode and request.finalize_session:
                message_id = request.message_id if request.source_type == "reply" else None
                await service.finalize_session(
                    request.session_id, user_id, prompt_id, content, message_id, request.source_type
                )
            
            await session.commit()
            
            return SavePromptResponse(
                code=0,
                message="保存成功",
                data={
                    "prompt_id": prompt_id,
                    "session_id": request.session_id,
                    "session_status": 1 if (not is_standalone_mode and request.finalize_session) else 0,
                    "final_content": content,
                    "is_update": request.prompt_id is not None and not is_forked,
                    "is_forked": is_forked,
                }
            )
            
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"[PromptSave] Error saving prompt: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")
