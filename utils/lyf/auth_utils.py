import logging
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext

# 获取项目根目录并添加到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# 尝试多种可能的导入方式
try:
    # 尝试直接导入ORM_Model.user
    from ORM_Model.user import User, Role
except ImportError:
    try:
        # 如果上面失败，尝试从generate_report_test目录导入
        from generate_report_test.ORM_Model.user import User, Role
    except ImportError:
        # 如果还失败，尝试添加generate_report_test到路径后再导入
        generate_report_test_path = os.path.join(project_root, 'generate_report_test')
        if generate_report_test_path not in sys.path:
            sys.path.insert(0, generate_report_test_path)
        from ORM_Model.user import User, Role

# 初始化日志与加密
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ===========================
# 1. 密码加密底层工具
# ===========================
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ===========================
# 2. 核心业务逻辑
# ===========================

def register_user_logic(db: Session, username: str, password: str) -> Dict[str, Any]:
    """
    MVP 注册逻辑：
    - 强制检查默认角色
    - 捕获 IntegrityError 处理并发
    """
    try:
        # 1. 检查默认角色是否存在
        default_role = db.query(Role).filter(
            Role.role_key == "user",
            Role.status == 1
        ).first()

        if not default_role:
            logger.critical("🔥 严重错误：数据库中未找到默认角色 'user'，请先运行 init_db.py")
            return {"success": False, "message": "系统环境未就绪"}

        # 2. 创建用户实例
        new_user = User(
            username=username,
            password_hash=get_password_hash(password),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        # ORM 自动处理多对多中间表
        new_user.roles.append(default_role)

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(f"✨ 用户注册成功: {username} (ID: {new_user.id})")
        return {"success": True, "user_id": new_user.id}

    except IntegrityError:
        # 处理用户名重复的情况
        db.rollback()
        logger.warning(f"⚠️ 注册冲突：用户名 '{username}' 已被占用")
        return {"success": False, "message": "该用户名已被注册"}

    except Exception as e:
        db.rollback()
        logger.exception(f"💥 注册异常：{str(e)}")
        return {"success": False, "message": "服务器繁忙"}


def login_user_logic(db: Session, username: str, password: str, ip: str = None) -> Dict[str, Any]:
    """
    MVP 登录逻辑：
    - 区分失败原因记入日志
    - 更新登录轨迹
    """
    try:
        # 1. 查询用户
        user = db.query(User).filter(
            User.username == username, 
            User.is_deleted == 0
        ).first()

        # 2. 审计与校验 (内部区分逻辑，外部统一返回)
        if not user:
            logger.info(f"🚫 登录失败：账号不存在 | User: {username} | IP: {ip}")
            return {"success": False, "message": "用户名或密码错误"}
        
        if user.status == 0:
            logger.warning(f"🚫 登录失败：账号被封禁 | User: {username} | IP: {ip}")
            return {"success": False, "message": "账号已被禁用"}

        if not verify_password(password, user.password_hash):
            logger.info(f"🚫 登录失败：密码错误 | User: {username} | IP: {ip}")
            return {"success": False, "message": "用户名或密码错误"}

        # 3. 更新登录信息
        user.last_login_at = datetime.now()
        user.last_login_ip = ip
        
        db.commit()

        # 4. 获取角色列表 (由于 lazy="selectin", 这里不会产生额外的 N+1 查询)
        roles_list = [r.role_key for r in user.roles]
        
        # 5. 生成 JWT Token
        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            roles=roles_list,
            department_id=user.department_id
        )

        logger.info(f"🔑 登录成功: {username} | 角色: {roles_list} | 部门ID: {user.department_id} | IP: {ip}")
        return {
            "success": True, 
            "data": {
                "access_token": access_token,
                "token_type": "bearer",
                "user_info": {
                    "id": user.id,
                    "username": user.username,
                    "roles": roles_list,
                    "department_id": user.department_id,
                    "display_name": username
                }
            }
        }   

    except Exception as e:
        db.rollback()
        logger.exception(f"💥 登录逻辑崩溃：{str(e)}")
        return {"success": False, "message": "系统错误，请重试"}


# 在 auth_utils.py 中新增
import jwt
from datetime import datetime, timedelta

# ===========================
# 3. JWT 配置加载 (从环境变量读取)
# ===========================
# 密钥：优先从环境变量获取，若不存在则抛出异常或使用安全默认值（生产环境必须配置）
SECRET_KEY = os.getenv("JWT_SECRET", "fallback-secret-for-dev-only-change-me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天 (10080分钟)

if SECRET_KEY == "fallback-secret-for-dev-only-change-me":
    logger.warning("⚠️ 安全警告：未检测到 JWT_SECRET 环境变量，正在使用开发环境默认密钥！")

def create_access_token(user_id: int, username: str, roles: list, department_id: int = None) -> str:
    """
    签发 JWT Token，Payload 包含：
    - sub: 用户ID
    - username: 用户名
    - role: 角色列表
    - department_id: 用户所属部门ID
    - iat: 签发时间
    - exp: 过期时间
    """
    now = datetime.utcnow()
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "role": roles[0] if roles else "user",
        "roles": roles,
        "department_id": department_id,
        "iat": now,
        "exp": expire
    }
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """解析并验证 Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning(f"🚫 Token 验证失败: 签名已过期 | Token: {token[:10]}...")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"🚫 Token 验证失败: 无效的 Token ({str(e)}) | Token: {token[:10]}...")
        return None
    except Exception as e:
        logger.exception(f"💥 Token 验证发生未知异常: {str(e)}")
        return None

# ... 以下是测试代码


def authenticate_user(db: Session, username: str, password: str, ip: str = None) -> Dict[str, Any]:
    """
    封装登录逻辑，供 API 层调用
    """
    return login_user_logic(db, username, password, ip)

if __name__ == "__main__":
    import sys
    import os

    # 1. 确保能导入同级目录的模块
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.append(current_dir)

    # 从你的 session 管理器导入 contextmanager
    from db_session import get_session_cm

    # 设定测试数据
    test_user = "lyf_tester_v1"
    test_pwd = "password_secure_123"

    print("🚀 开始底层 Utils 功能测试...")

    # 2. 使用 get_session_cm 开启一个数据库会话
    # 这里的 "remote_db" 必须在你的 sql_config.DATABASES 中定义过
    try:
        with get_session_cm("remote_db") as db:
            
            # --- 测试 A: 注册 ---
            print("\n[测试 A] 尝试注册新用户...")
            reg_result = register_user_logic(db, test_user, test_pwd)
            print(f"结果: {reg_result}")

            # --- 测试 B: 登录 ---
            if reg_result["success"] or reg_result["message"] == "该用户名已被注册":
                print("\n[测试 B] 尝试用户登录...")
                login_result = login_user_logic(db, test_user, test_pwd, ip="127.0.0.1")
                print(f"结果: {login_result}")
                
                if login_result["success"]:
                    # 注意：结构已变更为包含 access_token
                    print(f"✅ 登录成功，Token: {login_result['data']['access_token'][:20]}...")
            
            # --- 测试 C: 错误密码登录 ---
            print("\n[测试 C] 尝试错误密码登录...")
            wrong_login = login_user_logic(db, test_user, "wrong_pwd_xxx")
            print(f"结果: {wrong_login} (预期应为 False)")

    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
    
    print("\n🏁 测试结束。")