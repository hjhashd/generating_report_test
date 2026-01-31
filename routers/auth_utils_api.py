from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import timedelta
from typing import List, Optional

# 导入工具函数
from utils.lyf.auth_utils import (
    register_user_logic, 
    authenticate_user, 
    create_access_token
)
from utils.lyf.db_session import get_db

router = APIRouter(prefix="/auth", tags=["用户认证"])

# --- 1. 数据模型 (Schemas) ---

class UserInfo(BaseModel):
    """用户信息响应模型，过滤敏感字段"""
    id: int
    username: str
    roles: List[str]
    
    class Config:
        from_attributes = True  # 允许从 SQLAlchemy 对象直接转换

class LoginResponse(BaseModel):
    """统一的登录/注册响应结构"""
    success: bool
    message: str
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
    user: Optional[UserInfo] = None

class UserRegister(BaseModel):
    """注册请求模型"""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6)
    email: Optional[str] = Field(None, pattern=r"^\S+@\S+\.\S+$")

class UserLogin(BaseModel):
    """登录请求模型"""
    username: str = Field(...)
    password: str = Field(...)

# --- 2. 路由接口 ---

@router.post("/register", summary="新用户注册", response_model=LoginResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """
    接收用户名和密码，创建用户并分配角色。
    """
    result = register_user_logic(db, user_in.username, user_in.password)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    
    # 统一返回 LoginResponse 格式，确保数据被 UserInfo 过滤
    return LoginResponse(
        success=True,
        message="注册成功",
        user=result.get("data")
    )

@router.post("/login", summary="用户登录获取 Token", response_model=LoginResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    验证身份，返回签发的 JWT Token 及过滤后的用户信息。
    """
    # 1. 验证身份
    auth_result = authenticate_user(db, user_in.username, user_in.password)
    
    if not auth_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. 直接使用底层返回的 Token 结构
    # auth_result["data"] 结构已在 auth_utils.py 中更新为包含 access_token
    data = auth_result["data"]
    
    # 3. 返回标准格式
    return LoginResponse(
        success=True,
        message="登录成功",
        access_token=data["access_token"],
        token_type=data["token_type"],
        user=data["user_info"]
    )

@router.post("/logout", summary="退出登录")
def logout():
    """
    JWT 退出逻辑由前端清除客户端 Token 实现。
    """
    return {"success": True, "message": "已安全退出"}