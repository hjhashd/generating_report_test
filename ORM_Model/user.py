from sqlalchemy import Column, Integer, BigInteger, String, DateTime, SmallInteger, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, comment="登录账号")
    password_hash = Column(String(255), nullable=False, comment="哈希密码")
    
    status = Column(SmallInteger, server_default="1", nullable=False, comment="1=正常 0=禁用")
    is_deleted = Column(SmallInteger, server_default="0", nullable=False, comment="软删除")
    
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(64), nullable=True)
    
    # 自动生成时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # 建立多对多关系关联
    # 通过 secondary 指定中间表，back_populates 实现双向绑定
    roles = relationship(
        "Role", 
        secondary="user_roles", 
        back_populates="users",
        lazy="selectin" 
    )


class Role(Base):
    __tablename__ = "roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    role_key = Column(String(32), unique=True, nullable=False, comment="admin/user")
    role_name = Column(String(64), nullable=False, comment="角色名称")
    description = Column(String(255))
    
    status = Column(SmallInteger, server_default="1", nullable=False)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # ✅ 优化 1：双向同步 selectin
    users = relationship(
        "User", 
        secondary="user_roles", 
        back_populates="roles",
        lazy="selectin"
    )

class UserRole(Base):
    __tablename__ = "user_roles"
    
# ✅ 优化 2：强制唯一约束，防止重复授权
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uk_user_role"),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 建立物理外键关联
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)