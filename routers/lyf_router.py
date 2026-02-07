from fastapi import APIRouter
from routers import prompt_chat_api, prompt_optimize_api, prompt_test_api

router = APIRouter()

# 统一挂载 LYF 模块的路由
router.include_router(prompt_chat_api.router, prefix="/chat", tags=["LYF-Prompt"])
router.include_router(prompt_optimize_api.router, prefix="/optimize", tags=["LYF-Prompt"])
router.include_router(prompt_test_api.router, prefix="/test", tags=["LYF-Prompt"])
