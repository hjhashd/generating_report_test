# User 模型字段补全与登录增强计划

## 一、背景说明

### 1.1 系统架构概述

本项目包含两个后端服务，**共享同一个数据库**：

| 系统 | 后端技术 | 前端 | 端口（生产） | 用途 |
|------|---------|------|-------------|------|
| **报告系统** | Python (FastAPI) | - | 12543 | 生成报告 |
| **提示词系统** | Java (Spring Boot) | Vue (note-prompt) | 12544 | 提示词管理 |

两个系统共享 `users` 表，用户账号统一管理。

### 1.2 问题描述

**报告系统** 生产环境容器启动后登录接口崩溃，原因是：

**Python ORM 模型与数据库表结构不一致**

| 字段 | 数据库表 `users` | Python ORM | Java 实体 |
|------|------------------|------------|-----------|
| `department_id` | ✅ 存在 | ❌ 缺失 | ✅ 存在 |
| `real_name` | ✅ 存在 | ❌ 缺失 | ✅ 存在 |
| `shulingtong_sk` | ✅ 存在 | ❌ 缺失 | ❌ 缺失 |

### 1.3 字段含义说明

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `username` | 电话号码 | 登录账号 | `13800138000` |
| `real_name` | 真实姓名 | 用户真实姓名 | `张三` |

用户可以用**电话号码**或**真实姓名**登录系统。

### 1.4 数据库表结构（参考）

来自 `docs/database/generating_reports_test_v2.sql`：

```sql
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL COMMENT '登录账号（电话号码）',
  `password_hash` varchar(255) NOT NULL COMMENT '哈希密码',
  `real_name` varchar(64) DEFAULT NULL COMMENT '真实姓名',
  `department_id` int DEFAULT NULL COMMENT '部门ID',
  `shulingtong_sk` varchar(255) DEFAULT NULL COMMENT '数灵童用户SK(用于知识库关联)',
  `status` smallint NOT NULL DEFAULT '1' COMMENT '1=正常 0=禁用',
  `is_deleted` smallint NOT NULL DEFAULT '0' COMMENT '软删除',
  `last_login_at` datetime DEFAULT NULL,
  `last_login_ip` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
);
```

---

## 二、修改目标

1. **补全 Python ORM 模型字段**：让报告系统正常运行
2. **增强登录功能**：两个系统都支持用**电话号码**或**真实姓名**登录

---

## 三、修改计划

### 3.1 修改文件清单

| 序号 | 系统 | 文件路径 | 修改类型 |
|------|------|----------|----------|
| 1 | 报告系统 (Python) | `generate_report_test/ORM_Model/user.py` | 添加字段 |
| 2 | 报告系统 (Python) | `generate_report_test/utils/lyf/auth_utils.py` | 修改查询逻辑 |
| 3 | 提示词系统 (Java) | `ljt/prompt-system-backend/src/main/resources/mapper/UserMapper.xml` | 修改 SQL 查询 |

---

### 3.2 详细修改内容

---

## 🐍 报告系统（Python 后端）

### 修改一：`ORM_Model/user.py` - 补全缺失字段

**文件位置**：`generate_report_test/ORM_Model/user.py`

**当前代码**（第 9-21 行）：
```python
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=True, comment="登录账号")
    password_hash = Column(String(255), nullable=False, comment="哈希密码")
    
    status = Column(SmallInteger, server_default="1", nullable=False, comment="1=正常 0=禁用")
    is_deleted = Column(SmallInteger, server_default="0", nullable=False, comment="软删除")
    
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(64), nullable=True)
    
    # 自动生成时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
```

**修改后**（在 `password_hash` 后添加三个字段）：
```python
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=True, comment="登录账号（电话号码）")
    password_hash = Column(String(255), nullable=False, comment="哈希密码")
    
    # ===== 新增字段 =====
    real_name = Column(String(64), nullable=True, comment="真实姓名")
    department_id = Column(Integer, nullable=True, comment="部门ID")
    shulingtong_sk = Column(String(255), nullable=True, comment="数灵童用户SK(用于知识库关联)")
    # ===================
    
    status = Column(SmallInteger, server_default="1", nullable=False, comment="1=正常 0=禁用")
    is_deleted = Column(SmallInteger, server_default="0", nullable=False, comment="软删除")
    
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(64), nullable=True)
    
    # 自动生成时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
```

---

### 修改二：`utils/lyf/auth_utils.py` - 支持真实姓名登录

**文件位置**：`generate_report_test/utils/lyf/auth_utils.py`

**当前代码**（第 100-104 行）：
```python
        # 1. 查询用户
        user = db.query(User).filter(
            User.username == username, 
            User.is_deleted == 0
        ).first()
```

**修改后**（支持电话号码或真实姓名登录）：
```python
        # 1. 查询用户（支持电话号码或真实姓名登录）
        user = db.query(User).filter(
            User.is_deleted == 0
        ).filter(
            (User.username == username) | (User.real_name == username)
        ).first()
```

**说明**：
- `username` 参数可能是电话号码（`users.username`）或真实姓名（`users.real_name`）
- 使用 SQLAlchemy 的 `|` (OR) 操作符同时匹配两种登录方式

---

## ☕ 提示词系统（Java 后端）

### 修改三：`UserMapper.xml` - 支持真实姓名登录

**文件位置**：`ljt/prompt-system-backend/src/main/resources/mapper/UserMapper.xml`

**当前代码**（第 19-23 行）：
```xml
    <select id="findByUsername" resultMap="UserResultMap">
        SELECT * FROM users 
        WHERE username = #{username} 
          AND is_deleted = 0
    </select>
```

**修改后**（支持电话号码或真实姓名登录）：
```xml
    <select id="findByUsername" resultMap="UserResultMap">
        SELECT * FROM users 
        WHERE (username = #{username} OR real_name = #{username})
          AND is_deleted = 0
    </select>
```

**说明**：
- 方法名 `findByUsername` 保持不变
- `#{username}` 参数可能是电话号码或真实姓名
- SQL 使用 `OR` 条件同时匹配 `username`（电话号码）和 `real_name`（真实姓名）

---

## 四、部署步骤

### 4.1 报告系统（Python 后端）

```bash
# 进入项目目录
cd /root/zzp/langextract-main/generate_report_test

# 测试环境：重启容器让新代码生效
docker compose --profile dev restart

# 生产环境：重新构建镜像并启动
docker compose --profile prod build --no-cache
docker compose --profile prod up -d
```

### 4.2 提示词系统（Java 后端）

```bash
# 进入项目目录
cd /root/zzp/langextract-main/ljt/prompt-system-backend

# 重新构建并启动（脚本会自动检测代码更新）
./prod_service.sh restart
```

### 4.3 验证修改

```bash
# 报告系统日志
cd /root/zzp/langextract-main/generate_report_test
docker compose --profile prod logs -f app

# 提示词系统日志
cd /root/zzp/langextract-main/ljt/prompt-system-backend
tail -f logs/prod.log
```

---

## 五、注意事项

1. **数据库无需修改**：数据库表已有这些字段，只是 Python ORM 模型未定义

2. **向后兼容**：新增字段都允许 NULL，不影响现有数据

3. **登录方式变化**：
   | 修改前 | 修改后 |
   |--------|--------|
   | 只能用电话号码登录 | 可以用电话号码或真实姓名登录 |

4. **潜在冲突风险**：
   - 如果有用户真实姓名是 `13800138000` 这样的字符串，可能与其他用户的电话号码冲突
   - **建议**：在真实姓名输入时限制不能输入纯数字

5. **Java 实体类无需修改**：`User.java` 已有 `realName` 和 `departmentId` 字段

---

## 六、涉及文件汇总

```
项目结构
├── generate_report_test/                    # 🐍 报告系统（Python）
│   ├── ORM_Model/
│   │   └── user.py                          ← 添加 3 个字段
│   └── utils/lyf/
│       └── auth_utils.py                    ← 修改登录查询逻辑
│
└── ljt/prompt-system-backend/               # ☕ 提示词系统（Java）
    └── src/main/resources/mapper/
        └── UserMapper.xml                   ← 修改 SQL 查询条件
```

---

## 七、系统架构图

```
                    ┌─────────────────────────────────────┐
                    │         前端 (note-prompt)          │
                    │        Vue + Nginx 反向代理          │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                              │
                    ▼                              ▼
        ┌───────────────────┐          ┌───────────────────┐
        │   /api/python/    │          │   /api/java/      │
        │   报告系统后端      │          │   提示词系统后端    │
        │   Python:12543    │          │   Java:12544      │
        └─────────┬─────────┘          └─────────┬─────────┘
                  │                              │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │      MySQL 数据库       │
                    │    共享 users 表        │
                    └────────────────────────┘
```

---

## 八、代码调用链路参考

### 报告系统（Python）

```
API 路由 → auth_utils.login_user_logic()
         → db.query(User).filter(...)  ← 修改点
```

### 提示词系统（Java）

```
AuthController.login()
    → UserService.login()
        → UserMapper.findByUsername()  ← 修改点（XML 中的 SQL）
```

---

*文档更新时间：2026-03-10*
