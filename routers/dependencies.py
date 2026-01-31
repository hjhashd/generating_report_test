
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import List, Optional
from utils.lyf.auth_utils import verify_token
import logging

# Setup logger
logger = logging.getLogger(__name__)

# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# 定义统一的用户模型
class CurrentUser(BaseModel):
    id: int = Field(..., alias="sub")  # 将 JWT 中的 sub 自动映射为 id
    username: str
    roles: List[str] = []

    class Config:
        # 允许通过别名填充数据 (sub -> id)
        populate_by_name = True

def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """
    Dependency to get the current user from the JWT token.
    Returns a Pydantic model with standardized fields (user.id, user.username).
    """
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # 自动转换：Pydantic 会读取 payload['sub'] 并赋值给 user.id
        return CurrentUser(**payload)
    except Exception as e:
        logger.error(f"Token payload parsing failed: {e} | payload: {payload}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token structure",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """
    Dependency that ensures a user is authenticated.
    """
    return current_user
