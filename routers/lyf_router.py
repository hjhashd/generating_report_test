from fastapi import APIRouter
from routers import prompt_chat_api, prompt_optimize_api, prompt_test_api, prompt_session_title_api
from routers import prompt_chat_api_v2, prompt_save_api, prompt_tag_api, prompt_user_api

router = APIRouter()

router.include_router(prompt_chat_api.router, prefix="/chat", tags=["LYF-Prompt"]) #已不再使用
router.include_router(prompt_chat_api_v2.router, prefix="/chat/v2", tags=["LYF-Prompt-V2-Async"])
router.include_router(prompt_optimize_api.router, prefix="/optimize", tags=["LYF-Prompt"])
router.include_router(prompt_test_api.router, prefix="/test", tags=["LYF-Prompt"])
router.include_router(prompt_save_api.router, prefix="/prompts", tags=["Prompt-Save"])
router.include_router(prompt_tag_api.router, prefix="/prompts", tags=["Prompt-Tags"])
router.include_router(prompt_user_api.router, prefix="/prompts", tags=["Prompt-User"])
router.include_router(prompt_session_title_api.router, prefix="/title", tags=["Prompt-Title"])
