"""
Prompt 相关数据模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SavePromptRequest(BaseModel):
    """保存提示词请求体"""
    session_id: Optional[int] = None  # 可选，无会话时直接保存提示词
    title: str
    content: Optional[str] = None
    source_type: str
    message_id: Optional[int] = None
    visibility: str = "private"
    department_id: Optional[int] = None
    tag_ids: List[int] = []
    directory_id: Optional[int] = None
    icon_code: Optional[str] = None
    description: Optional[str] = None
    user_input_example: Optional[str] = None
    variables_json: Optional[Dict[str, Any]] = None
    model_config_json: Optional[Dict[str, Any]] = None
    finalize_session: bool = True
    prompt_id: Optional[int] = None


class CreateTagRequest(BaseModel):
    """创建个人标签请求"""
    tag_name: str = Field(..., min_length=1, max_length=50, description="标签名称")
    parent_id: int = Field(default=0, description="父标签ID，0表示根标签")
    icon_code: Optional[str] = Field(None, description="图标代码")
    color: Optional[str] = Field(None, description="标签颜色")


class SavePromptResponse(BaseModel):
    """保存提示词响应"""
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="响应数据")


class TagTreeNode(BaseModel):
    """标签树节点"""
    id: int
    tag_name: str
    type: int
    parent_id: int
    icon_code: Optional[str] = None
    color: Optional[str] = None
    department_id: Optional[int] = None
    children: List["TagTreeNode"] = []


class DepartmentNode(BaseModel):
    """部门树节点"""
    id: int
    name: str
    parent_id: int
    children: List["DepartmentNode"] = []


class UpdateTagDepartmentRequest(BaseModel):
    """更新标签部门请求"""
    department_id: int = Field(..., description="部门ID")


class AddTagToPromptRequest(BaseModel):
    """为提示词添加标签请求"""
    tag_id: int = Field(..., description="标签ID")


class UserStatsResponse(BaseModel):
    """用户统计数据响应"""
    total_prompts: int = Field(default=0, description="总提示词数")
    favorite_count: int = Field(default=0, description="收藏提示词数")
    like_count: int = Field(default=0, description="获赞总数")
    share_count: int = Field(default=0, description="分享次数")
    view_count: int = Field(default=0, description="被查看次数")
    copy_count: int = Field(default=0, description="被复制次数")


class ActivityItem(BaseModel):
    """活动记录项"""
    id: int
    type: str
    text: str
    highlight: str
    time: str
    icon: str


class UserPromptItem(BaseModel):
    """用户提示词项"""
    id: int
    title: str
    like_count: int
    favorite_count: int
    copy_count: int
    view_count: int
    create_time: str
    update_time: str
    status: int
    is_template: int
