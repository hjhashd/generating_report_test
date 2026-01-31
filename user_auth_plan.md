 # 多用户与 JWT 登录体系最佳实践方案（内网简化版）

 ## 1. 设计背景与目标

 - 支持多用户登录、注册和访问系统资源
 - 使用 JWT 作为主要认证方式，便于前后端分离和后续扩展
 - 用户信息、权限、配置做到统一管理、统一入口，降低维护成本
 - 结合现有的数据库配置中心 [sql_config.py](file:///root/zzp/langextract-main/generate_report_test/utils/sql_config.py)，避免重复造轮子
 - 项目部署在内网环境，允许在保证基本安全性的前提下适当简化实现，优先快速落地

 ---

 ## 2. 总体架构概览

 从用户认证与管理视角，推荐按以下几个层次来设计：

 - 接口层（API）
   - 提供登录、注册、获取当前用户信息、用户管理（增删改查）等 HTTP 接口
   - 所有需要登录的接口通过中间件或装饰器统一校验 JWT
 - 认证与授权层
   - JWT 生成与解析
   - 鉴权中间件（负责解析请求头中的 token，注入当前用户）
   - 简单 RBAC（基于角色的访问控制）
 - 数据存储层
   - 统一使用 `report_db`（或指定库）中的 `users` 表（及可选的角色表）
   - 通过 `utils/sql_config.py` 提供的 `get_mysql_url` 统一创建连接
 - 配置与常量
   - JWT 密钥、过期时间、默认角色等集中配置
   - 禁止在业务代码中散落魔法字符串

 ---

 ## 3. 数据库模型设计（内网简化版）

 推荐在 `report_db` 中新增一个 `users` 表，满足当前需求并方便扩展。

 ### 3.1 users 表（核心）

 字段建议：

 - `id`：主键，自增
 - `username`：登录用户名，唯一索引
 - `password_hash`：密码哈希值（比如 bcrypt / PBKDF2）
 - `display_name`：展示用昵称
 - `email`：邮箱（可选）
 - `role`：角色，枚举值，例如 `admin` / `user` / `guest`
 - `is_active`：是否启用账号，布尔值
 - `last_login_at`：最近登录时间
 - `created_at`：创建时间
 - `updated_at`：更新时间

 内网场景，初期可以只用一张 `users` 表，后续如果角色、权限变复杂，再拆出：

 - `roles` 表：角色定义表（role_key, role_name, 描述）
 - `user_roles` 表：多对多关系表（user_id, role_id）

 ---

 ## 4. 配置与统一管理设计

 目标是：所有“与用户和登录相关的配置”有一个清晰统一的入口，避免散落在代码各处。

 ### 4.1 与数据库配置中心的关系

 当前已有的数据库配置中心：

 - 文件：`utils/sql_config.py`
 - 通过 `DATABASES` 字典和 `get_mysql_url(db_name)` 统一管理数据库连接信息

 推荐做法：

 - 用户相关的表默认放在 `report_db` 中
 - 用户模块连接数据库时统一使用：
   - `get_mysql_url("report_db")` 创建 SQLAlchemy 引擎或 ORM Session
 - 如果未来需要将用户系统迁移到 `agent_db` 或其他库，只需在 `DATABASES` 中调整配置即可，不需要改业务代码

 ### 4.2 认证与用户相关配置集中化

 新增一个专门的配置模块（示例）：

 - 路径示例：`config/auth.py` 或 `utils/auth_config.py`
 - 职责：
   - `JWT_SECRET_KEY`
   - `JWT_ALGORITHM`（例如 `HS256`）
   - `JWT_EXPIRE_MINUTES`（例如 8 小时内网可接受）
   - `PASSWORD_HASH_SCHEME`（如 `bcrypt`）
   - 默认管理员账号配置（是否自动创建一个初始 admin）

 配置来源建议：

 - 内网环境可以先把这些配置写在配置文件中
 - 如有条件，敏感信息（JWT 密钥等）可以放环境变量中，而不是硬编码在仓库里

 ---

 ## 5. 接口设计与业务流程

 ### 5.1 核心接口列表

 认证相关：

 - `POST /api/auth/register`
   - 功能：新用户注册
   - 请求体：`username, password, display_name, email(可选)`
   - 规则：用户名唯一；密码长度符合最基本规则
 - `POST /api/auth/login`
   - 功能：登录，返回 JWT
   - 请求体：`username, password`
   - 响应体：`access_token, token_type`（如 `Bearer`）
 - `GET /api/auth/me`
   - 功能：获取当前登录用户的信息
   - 要求：必须携带合法 JWT

 用户管理（通常仅管理员可用）：

 - `GET /api/users`
   - 分页查询用户列表，支持按用户名、角色、是否启用筛选
 - `POST /api/users`
   - 管理员创建新用户（可指定角色）
 - `PATCH /api/users/{id}`
   - 修改用户信息（display_name、role、is_active 等）
 - `DELETE /api/users/{id}`
   - 删除或逻辑删除用户（推荐逻辑删除或标记禁用）

 ### 5.2 注册流程（后端视角）

 1. 校验请求参数（用户名、密码合法性）
 2. 检查 `username` 是否已存在
 3. 使用安全算法对密码进行哈希（如 bcrypt）
 4. 插入 `users` 表，设置默认角色（如 `user`）和 `is_active = 1`

 ### 5.3 登录与发放 JWT 流程

 1. 根据 `username` 查询 `users` 表
 2. 校验 `is_active`，禁用用户不能登录
 3. 校验密码哈希是否匹配
 4. 登录成功时：
    - 更新 `last_login_at`
    - 生成 JWT，载荷包含：
      - `sub`：用户 ID
      - `username`
      - `role`
      - `iat`：签发时间
      - `exp`：过期时间
 5. 将 `access_token` 返回给前端，前端以 `Authorization: Bearer <token>` 的方式携带

 ---

 ## 6. JWT 使用规范（内网简化版）

 ### 6.1 Token 内容设计

 JWT Header：

 ```json
 {
   "alg": "HS256",
   "typ": "JWT"
 }
 ```

 JWT Payload 示例：

 ```json
 {
   "sub": 123,
   "username": "alice",
   "role": "admin",
   "iat": 1710000000,
   "exp": 1710028800
 }
 ```

 建议仅放与认证授权有关的信息，避免放敏感数据（如明文手机号、邮箱等）。

 ### 6.2 过期时间与刷新策略

 内网简化策略：

 - `access_token` 有效期：建议 4–8 小时
 - 不强制实现刷新 token 机制
   - token 过期后，用户重新登录即可
 - 如未来要支持“长时间保持登录”，可增加 `refresh_token` 表和接口，当前阶段可以不实现

 ### 6.3 校验流程与中间件

 统一用中间件或装饰器处理认证逻辑：

 1. 从请求头 `Authorization` 中获取值，要求形如 `Bearer <token>`
 2. 使用统一的 `JWT_SECRET_KEY` 与算法进行解码
 3. 校验 `exp` 是否过期
 4. 校验 `sub` 对应用户是否存在且 `is_active` 为启用
 5. 将用户对象（或用户 ID、角色信息）注入到请求上下文，供后续业务使用

 如果校验失败：

 - 返回 `401 Unauthorized`，并给出简要错误信息（例如 `token expired` / `invalid token`）

 ---

 ## 7. 权限控制（统一、可配置）

 初期推荐使用“基于角色的访问控制”（RBAC）的简单版本：

 - 角色示例：
   - `admin`：系统管理员，拥有用户管理等高级权限
   - `user`：普通用户
   - `guest`：只读访问（如有需要）

 授权策略：

 - 普通业务接口：
   - 要求登录即可（拥有任意有效角色）
 - 管理接口（如用户管理）：
   - 要求 `role == "admin"`

 实现方式建议：

 - 封装若干装饰器 / 依赖注入函数，例如：
   - `require_user`：校验已登录，将当前用户注入
   - `require_admin`：在 `require_user` 之上再校验 `role == "admin"`
 - 将“接口需要什么角色”的逻辑写在路由定义处，而不是散落在业务逻辑内部

 角色配置的统一管理：

 - 将可用角色列表、默认角色等信息集中放在配置模块中
 - 如未来改角色名或新增角色，只需改配置，不改大量业务代码

 ---

 ## 8. 用户统一管理能力

 为了后期维护简单，建议预留一个“用户管理”功能（可以先不做 UI，只提供接口）：

 - 用户列表查询
   - 支持分页、按用户名、角色、启用状态过滤
 - 用户启用 / 禁用
   - 修改 `is_active` 字段
 - 重置密码
   - 管理员可为用户重置密码（重新生成密码哈希）
 - 修改角色
   - 在不改动代码的前提下，通过接口调整用户角色，实现动态授权

 这些能力统一走一套接口和一张或几张表，避免以后在多处“特殊处理某个用户”。

 ---

 ## 9. 安全与日志（在内网环境下的平衡）

 尽管是内网系统，也建议遵循一些基本安全实践：

 - 密码安全
   - 必须使用安全密码哈希库（如 bcrypt / PBKDF2）
   - 不在日志中输出明文密码
 - 登录安全
   - 可以简单做一个“登录失败计数”，在短时间内多次失败时暂时锁定账号
   - 内网环境可适当放宽限制，避免影响使用
 - 日志与审计（按需开启）
   - 记录登录日志：用户、时间、IP（如果有）、结果（成功/失败）
   - 记录关键操作日志：例如创建/删除用户、变更角色

 同时结合实际情况，不必引入过于复杂的安全组件，尽量保持实现简洁可维护。

 ---

 ## 10. 建议的实施阶段划分

### 阶段一：当前项目必做（✅ 已完成核心部分）

- [x] 创建 `users` 表
- [x] 实现注册接口（可视实际需要决定是否对外开放注册）
- [x] 实现登录接口，发放 JWT
- [x] 实现 JWT 校验依赖注入 (`routers/dependencies.py`)
- [x] 在部分关键接口（报告查询、删除）上接入登录校验

这一步之后，系统已经具备多用户与基本权限控制能力。

### 阶段二：增强与优化（后续计划）

- 用户管理接口（列表、启用/禁用、重置密码、修改角色）
- 更完善的权限体系（细粒度权限、菜单控制等）
- 登录日志、操作审计
- 引入 refresh token、单点登录等更高级特性（如有需要）

 ---

 ## 11. 已实现的组件与复用指南

当前系统已完成核心认证逻辑的封装，开发者可直接复用以下组件：

### 11.1 底层逻辑：auth_utils.py
- **路径**：[auth_utils.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/auth_utils.py)
- **核心功能**：
    - `register_user_logic`: 统一注册入口，自动处理 bcrypt 密码哈希和默认角色分配。
    - `login_user_logic`: 统一登录入口，校验身份并直接返回签发的 JWT Token。
    - `verify_token`: 解析并验证 JWT 合法性。
- **Token 规范**：
    - 有效期：7 天 (10080 分钟)。
    - Payload：包含 `sub` (用户ID), `username`, `roles` (角色列表)。

### 11.2 接口层：auth_utils_api.py
- **路径**：[auth_utils_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/auth_utils_api.py)
- **接口说明**：
    - `POST /auth/login`: 登录并获取 Token。
    - `POST /auth/register`: 注册新用户。
- **返回结构**：
    ```json
    {
      "success": true,
      "access_token": "...",
      "token_type": "bearer",
      "user": { "id": 1, "username": "...", "roles": [...] }
    }
    ```

---

## 12. 认证识别机制
后续系统所有需要辨别用户身份的接口，均统一通过解析请求头中的 **JWT Token** 来实现。
- **Header 格式**：`Authorization: Bearer <token>`
- **识别原则**：后端解析 Token 中的 `sub` 字段作为当前操作者的唯一用户标识。

---

## 13. 前端对接指南（最小改动方案）

针对前端开发同事，以下是对接变更说明：

### 13.1 核心变更
以下接口现已接入 JWT 认证体系，所有请求**必须**携带用户 Token，后端将根据 Token 自动隔离用户数据。

**涉及接口**：
1.  `/Query_report/` (查询报告草稿列表)
2.  `/Query_catalogue/` (查询报告目录/类型)
3.  `/delete_report_batch/` (批量删除报告)

### 13.2 前端修改要求

1.  **Header 必填**：
    所有请求头必须包含：
    `Authorization: Bearer <your_access_token>`
    *(注：Token 请从登录接口 `/auth/login` 获取)*

2.  **参数说明 (重要 - 关于 agentUserId)**：
    *   请求体中的 `agentUserId` 字段**仍需保留**（为了维持 JSON 结构不报错，实现最小改动）。
    *   后端**不再使用**该字段作为身份标识，而是优先信任 Token 解析出的 User ID。
    *   前端传任意数字即可（建议传 `0` 或保持原有逻辑不变）。

**示例代码 (Axios)**：
```javascript
// 示例：查询报告列表
axios.post('/Query_report/', {
    task_id: "...",
    status: 1,
    agentUserId: 123  // <--- 仍需传一个数字占位，但实际身份以 Token 为准
}, {
    headers: {
        'Authorization': `Bearer ${token}` // <--- 必须添加此 Header
    }
})
```

**预期行为**：
*   请求成功：返回该 Token 对应用户的私有数据。
*   请求失败 (401)：Token 缺失、无效或过期。

### 13.3 公共接口豁免清单（Risk Warning）
以下接口属于公共资源访问接口，**不需要**也**不应该**添加 JWT 验证，请后端开发人员注意检查：

1.  `/Query_modul/`：查询公共推荐模板。
2.  `/Import_modul/`：加载具体模板内容。
3.  `/Import_catalogue/`：导入章节超市中的公共章节。

---

## 14. 开发注意事项

在开发新的路由（Router）或修改现有路由时，请务必注意以下技术细节：

### 14.1 FastAPI 依赖注入导入
当你在路由函数中使用 `Depends(require_user)` 进行身份校验时，必须确保在文件顶部正确导入了 `Depends`。
- **常见错误**：仅导入了 `APIRouter`，导致运行时报错 `NameError: name 'Depends' is not defined`。
- **正确写法**：
  ```python
  from fastapi import APIRouter, Depends
  from routers.dependencies import require_user
  ```

### 14.2 路由保护原则
- **私有接口**：涉及用户个人数据（增删改查）的接口，必须添加 `current_user: CurrentUser = Depends(require_user)`。
- **公共接口**：如模板浏览等不区分用户的接口，不应添加该依赖，否则会导致未登录用户无法访问。

### 14.3 JWT Payload 字段统一处理 (Standardized)
通过 `routers/dependencies.py` 中的 `CurrentUser` Pydantic 模型，我们已经实现了字段的统一映射：
- **Token 解析**：后端会自动将 Token 中的 `sub` 字段映射为 `CurrentUser.id`。
- **推荐写法**：在接口中直接使用对象属性访问：
  ```python
  def some_api(current_user: CurrentUser = Depends(require_user)):
      user_id = current_user.id       # ✅ 推荐：直接使用 .id (类型为 int)
      username = current_user.username # ✅ 推荐
  ```
- **废弃写法**：不再建议将 `current_user` 当作字典使用（如 `current_user["sub"]`），虽然 Pydantic 模型可能兼容字典转换，但属性访问提供了更好的类型检查和 IDE 提示。
- **历史背景**：早期版本曾因混淆 `sub` 和 `id` 导致 KeyError，现在通过 Pydantic 模型已彻底规避此问题。


