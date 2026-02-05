# 提示词管理系统后端（Java / Spring Boot + MyBatis）共库实施计划

## 0. 背景与约束

- 本模块是现有主系统的扩展，不提供独立登录/注册。
- 用户上下文通过主系统鉴权后透传到本模块（Header / JWT / 网关注入）。
- 数据库与主系统共用一套表结构，来源脚本：`/root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_v2.sql`。

## 1. 现状：可复用的数据库能力盘点

脚本中已经包含提示词相关核心表，足以支撑大部分需求：

- 组织与用户
  - `sys_departments`：部门树（`parent_id` 支持一级/二级部门层级）。
  - `users`：用户（含 `department_id` 关联部门）。
- Prompt 核心
  - `ai_prompts`：提示词主体与统计字段（`view_count/like_count/favorite_count/copy_count/apply_report_count/heat_score`）。
  - `ai_prompt_tags` + `ai_prompt_tag_relation`：标签体系。
  - `ai_prompt_directories` + `ai_prompt_directory_rel`：目录体系（可做“个人/公共”的目录树）。
  - `ai_user_interactions`：点赞/收藏/分享/派生的幂等交互记录（唯一键 `uk_user_target_action`）。
  - `ai_chat_history`：对话/优化过程记录（可承载“专业模式测试”“AI优化”“对话模式”）。
- 关联与审计
  - `sys_operation_logs`：操作审计（适合记录“浏览/复制/应用到报告/运行测试”等事件）。
  - `sys_entity_relations`：通用实体关系（适合记录 Prompt 与 Report 的“应用/引用/复用”等关系）。
- 模型配置
  - `llm_config`：模型提供商与密钥（注意：`api_key` 为敏感字段）。

结论：后端项目优先“复用现有表 + 增量补齐缺口”，避免破坏主系统。

## 2. 关键业务规则落库映射（先定规则，后写代码）

### 2.1 用户组织架构

- 账号绑定二级部门：以 `users.department_id` 作为“二级部门”ID。
- 一级部门：`sys_departments` 中 `parent_id=0`（或 `ancestors` 为空）的节点。
- 二级部门：`sys_departments.parent_id` 指向一级部门。

后端需要提供两个通用查询：

- 根据二级部门 ID 查一级部门 ID（用于“分享至一级部门”）。
- 根据一级部门 ID 查所有二级部门 ID（用于“部门范围可见性查询”）。

### 2.2 分享范围（建议先用“可推导模型”，尽量不改表）

现有表缺少显式 `share_scope` 字段，推荐先做“约定式映射”，后续再决定是否加表：

- 私有：`ai_prompts.is_template = 0` 且 `ai_prompts.department_id IS NULL`
- 分享到部门（一级部门）：`ai_prompts.is_template = 0` 且 `ai_prompts.department_id = <一级部门ID>`
- 分享到全公司：`ai_prompts.is_template = 1`

可见性查询（用户 U 的二级部门为 D2，对应一级部门为 D1）：

- 作者本人：永远可见（`ai_prompts.user_id = U.id`）
- 全公司：可见（`is_template=1`）
- 部门共享：可见（`department_id = D1`）
- 私有：仅作者可见

如果后续发现“department_id 同时需要表达作者归属与分享目标”存在冲突，则新增一张增量表是更稳的方案（见 2.4）。

### 2.3 二次编辑/复用（Fork/Reuse）

- 原 prompt 不可被非作者修改。
- 复用行为：
  - 写入一条新的 `ai_prompts` 记录（新 ID，`origin_prompt_id` 指向原始模板，`parent_prompt_id` 指向被复用的 Prompt）。
  - 原 prompt 的 `copy_count` 自增。
  - 在 `ai_user_interactions` 插入/更新（`action_type=4` 派生）以实现幂等与统计基础。

### 2.4 什么时候需要改表（增量迁移）

当出现以下需求之一，建议新增增量表或新增列，而不是继续“靠约定推导”：

- 同一条 Prompt 需要同时“作者部门归属”和“分享目标部门”。
- 需要支持多部门共享/多个范围叠加。
- 需要区分“模板（公共内容）”与“全公司共享（非模板）”。

推荐的最小增量设计：

- 新表 `ai_prompt_shares(prompt_id, scope, target_dept_id, create_time)`
  - scope：PRIVATE / DEPT / GLOBAL
  - target_dept_id：当 scope=DEPT 时填一级部门 ID
  - 约束：`prompt_id` 唯一

并采用 Flyway/Liquibase 以“增量迁移脚本”的方式升级，严禁在共库环境中执行 DROP/重建。

## 3. API 设计准备（让 AI 生成项目时不跑偏）

### 3.1 统一响应与错误码（建议）

- 统一响应 envelope：
  - `code`（0 成功，非 0 失败）
  - `message`
  - `data`
  - `traceId`
- 统一错误码分段：
  - 10xxx：参数校验
  - 20xxx：鉴权/权限
  - 30xxx：业务约束（不可编辑他人 Prompt 等）
  - 50xxx：依赖故障（LLM 调用失败、DB 超时等）

### 3.2 鉴权透传契约（JWT 标准化方案）

在创建 Java 项目之前，明确采用 **JWT 验签** 方案（与 Python 主系统保持一致）：

- **Token 来源**：HTTP Header `Authorization: Bearer <token>`
- **Token 解析**：本模块作为 Resource Server，需配置与主系统一致的 `JWT_SECRET` 进行本地验签。
- **共享配置**（必须从 Python 后端同步给 Java 后端，请直接复制以下值）：
  - `JWT_SECRET`: `"你的加密私钥_请务必修改为复杂的随机字符串"` (硬编码值，来自 `/root/zzp/langextract-main/generate_report_test/utils/lyf/auth_utils.py`)
  - `JWT_ALGORITHM`: `HS256`
- **Claims 结构**（Payload）：
  - `sub` (String): 用户 ID (如 "123")
  - `username` (String): 用户名 (如 "zhangsan")
  - `roles` (List<String>): 角色列表 (如 ["admin", "user"])
  - `deptId` (Integer): 二级部门 ID (若主系统 Token 未包含，需查库补充或要求主系统下发)
  - `exp` (Long): 过期时间戳

**快速开发策略**：建议编写一个统一的 `JwtAuthenticationFilter`，解析成功后构建 `UserContext` 存入 `ThreadLocal`，供 Controller/Service 层直接调用 `UserContext.getCurrentUser()` 获取当前用户信息。

### 3.3 数据库与资源配置（绝对路径与敏感信息）

Java AI 必须使用以下**绝对路径**和**真实配置**来生成项目配置：

1. **SQL 脚本路径**：
   `/root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_v2.sql`
   (请让 AI 读取此文件以生成 Entity/Mapper)

2. **数据库连接配置**（来自 `/root/zzp/langextract-main/generate_report_test/utils/sql_config.py`）：
   - Host: `192.168.3.10`
   - Port: `3306`
   - Database: `generating_reports_test`
   - Username: `root`
   - Password: `xinan@2024`

3. **核心 Python 参考代码**：
   - 鉴权逻辑：`/root/zzp/langextract-main/generate_report_test/utils/lyf/auth_utils.py`
   - 用户模型：`/root/zzp/langextract-main/generate_report_test/ORM_Model/user.py`

### 3.4 核心接口清单（最小闭环）

- Prompt
  - `POST /api/prompts`：新建（含分享范围、变量、标签、模型参数）
  - `PUT /api/prompts/{id}`：作者更新
  - `POST /api/prompts/{id}/fork`：复用（生成新 Prompt）
  - `GET /api/prompts/{id}`：详情（记录浏览数）
  - `GET /api/prompts`：列表查询（分页、搜索、目录/标签筛选、排序）
- 交互
  - `POST /api/prompts/{id}/like:toggle`
  - `POST /api/prompts/{id}/favorite:toggle`
  - `POST /api/prompts/{id}/copy`（仅计数）
- LLM
  - `POST /api/prompts/{id}/test-run`：运行测试（写 `ai_chat_history` 与审计日志）
  - `POST /api/prompts/{id}/ai-optimize`：AI 优化（写 `ai_chat_history`）
- 报告关联
  - `POST /api/reports/{reportId}/apply-prompt`：应用到报告（写关系与计数）
- 辅助
  - `GET /api/prompts/recent`：最近使用模板（基于审计日志/交互表查询）
  - `GET /api/tags`：标签列表（系统/个人）
  - `GET /api/directories/tree`：目录树

## 4. 后端工程最佳实践（Spring Boot + MyBatis）

### 4.1 项目骨架与分层（快速开发模式）

建议简化分层，以“Controller -> Service -> Mapper”为主轴，避免过度封装：

- `api`：Controller（处理 HTTP 请求、参数校验、调用 Service、返回 Result）
- `service`：业务逻辑层（事务控制、权限校验、复杂编排）
- `mapper`：MyBatis 接口
- `model`：
  - `entity`：数据库表映射对象（PO）
  - `dto`：数据传输对象（入参/出参）
- `common`：统一响应、全局异常处理、JWT Filter、UserContext

**技术选型建议**：
- **MyBatis**：使用原生 MyBatis（XML 方式），适合需要精细控制 SQL 或不熟悉 Plus 的团队。建议配合 **MyBatis Generator** 或 **MyBatisX** 插件自动生成基础代码。
- **Lombok**：简化 Getter/Setter/Builder。
- **Validation**：使用 `@Valid` + Hibernate Validator 做参数校验。

### 4.2 MyBatis 使用规范

- Mapper 只做“单表/少表”的数据访问，复杂编排放到 application 层。
- 所有列表接口默认分页（PageHelper 或手动 Limit）。
- 对计数字段的并发更新使用原子 SQL（`SET like_count = like_count + 1`），并与交互记录写入放到同一事务里。

### 4.3 共库治理（强烈建议）

- 增量迁移：启用 Flyway/Liquibase，仅允许 `Vxxx__*.sql` 增量脚本。
- 禁止：DROP TABLE、修改既有字段语义、在线大字段变更。
- 索引治理：在上线前通过慢查询与 Explain 验证新增索引。

### 4.4 可观测性与稳定性

- 每个请求生成/透传 `traceId`（写入日志与响应）。
- 关键动作写入 `sys_operation_logs`（module/action/target_id/user_id）。
- LLM 调用加：超时、重试（幂等前提）、熔断/降级（返回“稍后重试”）。
- 频控：对 test-run/ai-optimize 类接口做用户级限流。

### 4.5 敏感信息安全

- `llm_config.api_key` 属于敏感字段：
  - 生产建议加密存储（至少应用层加解密 + KMS/环境变量密钥）。
  - 日志、异常链路禁止输出明文 key。

## 5. 给 AI 生成项目的“输入材料清单”（你要提前准备好）

为了让 AI 一次性生成高质量工程，请准备并在提示词里明确以下内容：

1) 技术栈与版本

- Java 版本（建议 17）
- Spring Boot 版本（建议 3.x）
- MyBatis 版本（及是否允许 MyBatis-Plus）
- 数据库：MySQL 8（脚本使用 `utf8mb4_0900_ai_ci`）

2) 数据库连接信息（仅在本地/测试环境使用）

- host/port/dbName/user/password
- 本模块使用的 schema 名称（与主系统一致）

3) 鉴权透传契约（最重要）

- 鉴权方式：JWT (Header `Authorization: Bearer ...`)
- **必须配置与主系统一致的配置**：
  - `JWT_SECRET`: (从 Python `auth_utils.py` 获取)
  - `JWT_ALGORITHM`: `HS256`
- Token Claims 字段：`sub`(userId), `username`, `roles`, `deptId`(可选)

4) 分享范围的落库约定（按 2.2 约定式实现，暂不建新表）

- 明确三种 scope 的判定逻辑与查询条件

5) API 清单与字段

- 列表筛选项：标签、目录、关键词、分享范围、作者、排序字段
- 分页策略与默认 pageSize
- DTO 字段与 JSON 示例

6) 与报告模块的关联方式

- 是否允许直接写 `sys_entity_relations` 来表达“应用到报告”
- reportId 的来源（`report_name.id`）

7) 非功能指标

- 预期并发/QPS、允许的响应时间
- 是否需要 Redis 缓存（热榜/目录树/标签）

## 6. 推荐给 AI 的“项目生成提示词模板”

（直接复制以下内容给 Java 后端 AI）

> **Role**: Senior Java Architect
> **Task**: Generate a Spring Boot backend for a Prompt Management System.
> **Context**: 
> 1. This system shares the database with an existing Python project.
> 2. **SQL Script Path**: `/root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_v2.sql` (Use this to generate Entity/Mapper)
> 3. **Auth**: JWT based. Must use `JWT_SECRET = "你的加密私钥_请务必修改为复杂的随机字符串"` (HS256) to validate tokens from Python app.
> 4. **DB Connection**: Host `192.168.3.10`, Port `3306`, DB `generating_reports_test`, User `root`, Pass `xinan@2024`.
> 
> **Tech Stack**:
> - Spring Boot 2.7+
> - **MyBatis (Native XML)**: Use MyBatis Generator/MyBatisX for base code.
> - **PageHelper**: For pagination.
> - **Lombok**: For POJO.
> - **MySQL Driver**: 8.0+
> 
> **Architecture (Simplified for Speed)**:
> - `api`: Controller + DTO
> - `service`: Business Logic
> - `mapper`: MyBatis Interface + XML
> - `common`: Global Exception, Result<T>, JwtAuthFilter, UserContext
> 
> **Key Requirement**:
> - Implement `JwtAuthenticationFilter` to parse header `Authorization: Bearer ...` and set `UserContext`.
> - Reuse existing tables (`ai_prompts`, `sys_departments`, `users`, etc.). **DO NOT create new tables.**
> - Use "Convention over Configuration" for sharing scopes (Private/Dept/Global) as defined in the plan.

## 7. 里程碑（建议）

- M1：完成鉴权上下文接入 + Prompt CRUD + 可见性查询
- M2：完成交互（点赞/收藏/复用）+ 统计与热度排序
- M3：完成 LLM test-run/ai-optimize + 对话历史落库
- M4：完成“应用到报告”关联与审计 + 稳定性（限流/熔断/监控）

