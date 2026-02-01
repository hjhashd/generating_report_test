# 多用户改造差距分析与任务计划（基于 user_auth_plan.md）

> 说明：本文件仅为“现状评估 + 改造任务清单”，暂不修改任何代码。  
> 评估范围主要集中在 `routers/` 下的业务接口以及 `utils/lyf/auth_utils.py`、`utils/zzp` 下与报告相关的核心逻辑。

## 1. 扫描范围与方法

- IDE 的代码索引当前未就绪，本次分析通过逐个文件人工扫描完成。
- 已重点检查的文件包括但不限于：
  - 认证相关：
    - [auth_utils.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/auth_utils.py#L1-L205)
    - [auth_utils_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/auth_utils_api.py#L1-L102)
  - 报告查询与浏览：
    - [query_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_report_api.py#L1-L55)
    - [browse_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/browse_report_api.py#L1-L151)
    - [editor_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/editor_api.py#L1-L314)
  - 报告结构与类型：
    - [query_modul_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_modul_api.py#L1-L65)
    - [query_catalogue_type_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_catalogue_type_api.py#L1-L94)
    - [import_catalogueShopping_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_catalogueShopping_api.py#L1-L62)
  - 报告创建、导入、合并与删除：
    - [import_doc_to_db_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_doc_to_db_api.py#L1-L217)
    - [create_catalogue_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/create_catalogue_api.py#L1-L78)
    - [report_merge_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/report_merge_api.py#L1-L228)
    - [delete_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/delete_report_api.py#L1-L125)
  - 模型与提示词、素材选择：
    - [inferrence_choose_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/inferrence_choose_api.py#L1-L280)
    - [insert_llm_config_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/insert_llm_config_api.py#L1-L69)
    - [delete_llm_config_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/delete_llm_config_api.py#L1-L76)
    - [ai_generate_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/ai_generate_api.py#L1-L121)
    - [ai_search_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/ai_search_api.py#L1-L110)
    - [query_prompts_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_prompts_api.py#L1-L115)
  - 报告列表查询底层：
    - [query_report.py](file:///root/zzp/langextract-main/generate_report_test/utils/zzp/query_report.py#L1-L100)

## 2. 认证与用户标识现状

### 2.1 已有能力

- 已实现统一的认证底层逻辑：
  - `utils/lyf/auth_utils.py` 提供：
    - `register_user_logic`：注册用户，分配默认角色。
    - `login_user_logic` / `authenticate_user`：登录校验、记录登录轨迹。
    - `create_access_token` / `verify_token`：JWT 的生成与校验，Payload 包含 `sub`(用户ID)、`username`、`roles` 等。
- 已暴露基础认证接口：
  - [auth_utils_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/auth_utils_api.py#L15-L95)
    - `POST /auth/register`
    - `POST /auth/login`
    - `POST /auth/logout`
- 与 `user_auth_plan.md` 一致：后续所有需要识别用户身份的接口应通过解析 Header 中的 `Authorization: Bearer <token>`，以 `sub` 作为当前操作者 ID。

### 2.2 现存问题（共性）

- 大量业务路由中仅在请求体中传入 `agentUserId` 字段，多数情况下：
  - 要么完全未使用；
  - 要么只是传给底层函数或写入日志；
  - **没有**任何统一的 JWT 校验或用户注入。
- 当前所有非认证类路由均未使用“统一的依赖/中间件”（如 `require_user`、`require_admin`）来校验登录状态或角色。
- 这意味着：
  - 任何人只要能访问接口并伪造 `agentUserId`，就有可能读取或操作其他用户的数据。
  - 没有实现 “每个人只能看到/操作自己的资源” 的要求。

> 改造方向：后续需要在路由层统一引入基于 JWT 的依赖注入（例如 `current_user: CurrentUser = Depends(require_user)`），废弃前端提供的 `agentUserId` 作为可信身份标识，仅视为兼容字段或彻底移除。

## 3. 报告查询与浏览相关接口

### 3.1 报告列表查询（查看所有报告）

- 文件：
  - 路由：[query_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_report_api.py#L1-L55)
  - 底层查询：[query_report.py](file:///root/zzp/langextract-main/generate_report_test/utils/zzp/query_report.py#L25-L80)
- 现状：
  - 请求模型 `QueryReport` 中包含 `agentUserId`，但接口实现中从未使用该字段。
  - 直接调用 `get_all_reports_list()`，底层 SQL 查询为：
    - `SELECT ... FROM report_name n JOIN report_type t ...`，**没有任何 user_id 条件**。
  - 返回结果为“所有报告列表”，前端直接展示。
- 风险：
  - 不同用户调用 `/Query_report/` 会看到同一份全量报告列表。
  - 无法满足“每个人只能查自己的报告并显示在前端”的目标。
- 计划中的改造任务（仅记录，不实现代码）：
  - [x] 在 `report_name` 或关联表中增加“属主用户字段”（如 `owner_user_id`），并迁移历史数据的归属方案。 (确认使用 `user_id`)
  - [x] 将 `get_all_reports_list(user_id)` 改造为按用户过滤的查询：
    - SQL 中增加 `WHERE n.owner_user_id = :user_id` 或等价逻辑。
  - [x] `Query_report_endpoint` 不再信任请求体中的 `agentUserId`，而是从已验证的 JWT 中获取 `sub` 作为 `user_id`。
  - [x] 前端层面明确：报告列表接口展示的始终是“当前登录用户自己的报告列表”，不再有“全局共享列表”入口（如需共享，另设计权限模型）。

### 3.2 报告结构与模块查询

- 文件：
  - [query_modul_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_modul_api.py#L1-L60)
  - [query_catalogue_type_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_catalogue_type_api.py#L1-L94)
  - [import_catalogueShopping_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_catalogueShopping_api.py#L1-L62)
- 现状：
  - 这些接口的请求模型普遍包含 `agentUserId`，但实现中：
    - `Query_modul_endpoint` 直接调用 `query_and_print_report_stats()`，未使用 `agentUserId`。
    - `Query_catalogue_endpoint` 直接调用 `get_categories_and_types()`，未使用 `agentUserId`。
    - `Import_catalogue_endpoint` 调用 `get_specific_category_tree(...)`，仍未使用 `agentUserId`。
  - 返回的结果通常是“报告类型/章节超市”等全局维度的数据。
- 风险与待决策点：
  - 如果“报告类型/章节模板/章节超市”被设计为**全局共享资源**，那么保持无用户区分是合理的，但需要清晰记录。
  - 如果未来需要支持“每个用户有自己的报告类型或章节模板”，当前实现缺乏 user_id 维度。
- 计划中的改造任务：
  - 在设计层明确：哪些资源是“全局共享”（如公共模板），哪些是“用户私有”（如用户自建模板）。
  - 对需要私有化的资源：
    - 数据表增加 `owner_user_id` 或 `tenant_id` 字段。
    - 底层查询函数增加 `user_id` 参数并按用户过滤。
    - 路由统一从 JWT 解析用户，而不是信任 `agentUserId`。

### 3.3 报告创建、导入与合并

- 文件：
  - 导入 Word 报告： [import_doc_to_db_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_doc_to_db_api.py#L1-L217)
  - 创建目录并生成最终报告： [create_catalogue_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/create_catalogue_api.py#L1-L78)
  - 合并子报告为整份报告： [report_merge_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/report_merge_api.py#L1-L228)
  - 删除报告： [delete_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/delete_report_api.py#L1-L125)
- 现状：
  - 所有请求模型均包含 `agentUserId`，但路由实现几乎都**未使用**该字段：
    - 导入接口 `/Import_Doc/`：只负责接收文件、写入临时目录、触发 `process_document(type_name, report_name, file_path, ...)`，过程没有 user_id 概念。
    - 创建目录 `/Create_Catalogue/`：调用 `generate_merged_report_from_json(report.catalogue_json, report.agentUserId)`，此处将 `agentUserId` 透传到底层，但路由层并未验证用户身份。
    - 合并报告 (`/merge_report_file/`)：
      - 现状：使用的是全局目录和数据库记录，没有按用户过滤。
    - 报告列表过滤 (`/Query_Merged_Reports/`)：
      - 现状：前端代码中传递 `agentUserId` (如 `(this.userInfo && this.userInfo.userId) || 1001`)，但后端未强制鉴权。
      - 重构建议：后端应完全忽略前端传的 `agentUserId`，直接从 JWT Token 中解析出 `user_id`，并强制增加 `owner_user_id` 过滤，仅返回该用户的报告。前端目前的传参仅作为后端彻底迁移前的占位。
    - 报告删除 (`/Delete_Merged_Reports_Batch/`)：
      - 现状：支持批量删除，但未校验数据归属权。
      - 重构建议：这是高危操作。后端在执行删除前，必须校验 `delete_list` 中的每一个 `reportId` 是否确实属于当前 Token 对应的用户。严禁仅通过请求体中的 ID 来删除他人的报告。
    - 批量删除报告 (`/delete_report_batch/`)：
      - 删除逻辑 `delete_report_task(type, name)` 未体现 user_id 维度。
- 风险：
  - 报告的创建、导入、合并、删除操作均是“全局空间”上的操作：
    - 任意用户只要知道某个 `type`/`name` 或记录 ID，就有机会操作不属于自己的报告。
  - 不满足“每个用户只能管理自己报告”的安全需求。
- 计划中的改造任务：
  - 报告实体层面：
    - 为 `report_name`、`merged_report` 等表补充 `owner_user_id` 字段。
    - 历史数据的归属策略（如统一归属到初始管理员账户）。
  - 导入/生成/合并/删除逻辑：
    - 所有核心函数签名统一增加 `user_id` 参数。
    - 在 SQL 或文件路径层面保证按用户隔离：
      - 可以是“同一张表 + owner_user_id 条件过滤”；
      - 也可以是“文件路径按用户分目录”，例如 `/report_root/{user_id}/{type_name}/...`。
  - 路由层：
    - 不再使用请求体中的 `agentUserId` 作为真实身份，而是由 JWT 决定当前用户。
    - 在执行任何“写操作”（导入、合并、删除）之前，统一校验“该报告是否属于当前用户”。

### 3.4 报告浏览与在线编辑

- 文件：
  - 浏览报告： [browse_report_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/browse_report_api.py#L1-L136)
  - 在线编辑： [editor_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/editor_api.py#L1-L314)
- 现状：
  - `BrowseReport` 请求模型中有 `agentUserId`，但浏览逻辑只是基于 `type_name`、`report_name` 拼物理路径：
    - 基础路径使用全局 `REPORT_DIR` 和 `MERGE_DIR`。
    - 未根据用户做任何路径隔离或权限检查。
  - `EditorRequest` / `SaveContentRequest` 中的 `agentUserId` 也未参与任何权限判断：
    - 只要给出正确的 `type_name`、`report_name`、`file_name`，就可以读取或覆盖对应 Word/HTML 文件。
- 风险：
  - 在当前实现下，**任意登录状态（甚至未登录状态）**下，只要前端可以构造请求，就能读取/修改所有报告内容。
  - 直接暴露物理路径和文件结构，缺乏 per-user 隔离。
- 计划中的改造任务：
  - 文件与报告实体的映射统一整理：
    - 建议通过数据库记录“某个逻辑报告属于谁、对应哪些文件路径”，不在接口层拼物理路径。
  - 访问控制：
    - 所有浏览/编辑接口必须先通过 JWT 拿到 `user_id`，再根据“报告归属”做权限判断。
    - 至少要确保“用户只能浏览/编辑自己名下的报告”，管理员可拥有额外权限。
  - 文件存储结构调整：
    - 优选在 `REPORT_DIR`/`MERGE_DIR` 下增加按用户划分的一级目录，例如：`REPORT_DIR/{user_id}/{type_name}/...`。
    - 旧数据的迁移方案需要单独规划（可后置）。

## 4. 模型配置、提示词与素材管理

### 4.1 LLM 配置管理

- 文件：
  - [insert_llm_config_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/insert_llm_config_api.py#L1-L69)
  - [delete_llm_config_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/delete_llm_config_api.py#L1-L76)
- 现状：
  - 请求模型包含 `agentUserId`，但：
    - 保存配置时仅调用 `save_custom_config(model_name, api_key, base_url)`，未传入用户信息。
    - 删除配置时仅按 `config_id` 调用 `delete_config(config_id)`，不区分用户。
  - 当前所有 LLM 配置是全局共享空间，没有 owner 概念。
- 风险：
  - 不同用户可能互相覆盖或删除彼此的模型配置。
  - 不符合“多用户系统应具备各自配置空间”的期望。
- 计划中的改造任务：
  - 数据库层为 LLM 配置表增加 `owner_user_id` 字段。
  - `save_custom_config` / `delete_config` 等函数签名增加 `user_id` 参数并按用户过滤。
  - 路由层从 JWT 获取当前用户 ID，确保：
    - 插入配置时记录 owner；
    - 删除时仅能删除自己名下的配置（管理员除外）。

### 4.2 提示词与“章节超市”

- 文件：
  - 提示词接口： [query_prompts_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/query_prompts_api.py#L1-L115)
  - 与提示词/LLM 模型相关的选择接口： [inferrence_choose_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/inferrence_choose_api.py#L1-L280)
- 现状：
  - `query_prompts_api.py` 中的三个接口：
    - `query_latest_prompts`、`search_prompts`、`query_hot_trending_prompts` 均以全局方式查询提示词。
    - `agentUserId` 仅作为透传，不参与查询条件。
  - `inferrence_choose_api.py` 中：
    - `get_all_files_with_folders(top_n, user_id)`、`add_folder(folder_name, user_id)`、`add_file(..., user_id)`、`del_file(file_id, user_id)`、`get_model_names(user_id)` 等函数已经显式使用 `user_id`。
    - 说明：**素材结构和模型配置的部分逻辑已具备 per-user 维度**。
- 风险与改造点：
  - 提示词当前属于全局共享资源，是否需要 per-user 维度尚未明确：
    - 如果以后希望“用户可以管理自己的私有提示词库”，需要调整数据模型与查询条件。
  - 即使素材/提示词保持全局共享，接口也应该至少要求登录并在日志中明确记录 `user_id`，满足基本审计需求。
- 计划中的改造任务：
  - 设计层面先决策：
    - 公共提示词与用户私有提示词的区分方式。
  - 若需要用户维度：
    - 提示词表增加 `owner_user_id` 及可选 `is_public` 字段。
    - 查询接口增加基于用户和公开标记的过滤逻辑。

### 4.3 推理素材与上传文件

- 文件：
  - 素材选择与上传： [inferrence_choose_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/inferrence_choose_api.py#L86-L223)
- 现状：
  - 查询/新增/删除文件、文件夹等操作，在调用底层函数时都传入了 `req.agentUserId`，若底层实现正确，理论上已具备 per-user 隔离能力。
  - 但 `/upload_file/` 接口仅根据 `folder_name` 拼接本地路径 `inferrence/{folder_name}`，未携带用户信息：
    - 文件系统路径层面仍然是全局共享。
- 风险：
  - 如果多个用户共用同名 `folder_name`，可能导致冲突或互相访问文件。
- 计划中的改造任务：
  - 将上传路径扩展为 `inferrence/{user_id}/{folder_name}` 或等价方案。
  - 与数据库中的文件记录表达方式对齐，保证“数据库视图”和“磁盘路径”都是按用户隔离。

## 5. AI 生成与搜索接口

- 文件：
  - [ai_generate_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/ai_generate_api.py#L1-L121)
  - [ai_search_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/ai_search_api.py#L1-L110)
- 现状：
  - `ai_generate_api.py`：
    - 在调用 `Chat_generator_stream`、`optimize_text_stream`、`ai_summary_stream` 时都会传入 `user_id=request.agentUserId`。
    - 路由层依然未验证 `agentUserId` 的真实性。
  - `ai_search_api.py`：
    - `agentUserId` 仅用于日志字段 `user_id`，不参与实际搜索逻辑。
- 风险：
  - 日志与任务记录中的用户标识可被伪造，影响审计与配额控制。
- 计划中的改造任务：
  - 所有 AI 生成/搜索类接口都统一从 JWT 获取用户 ID。
  - 如有“调用次数配额”“计费”等需求，必须绑定真实用户。

## 6. 全局改造原则与后续步骤（概要）

> 本节只列高层原则，具体每个接口的改造会在后续步骤中逐条落地。

- 身份来源统一：
  - 所有需要识别用户的接口必须通过 JWT（`Authorization: Bearer <token>`）获得当前用户信息。
  - 请求体中的 `agentUserId` 仅作为历史兼容字段，最终应去除或只做日志用。
- 数据模型补全：
  - 对于“应该按用户隔离”的实体（报告、合并报告、LLM 配置、私有提示词、推理素材等），统一增加 `owner_user_id` 字段。
- 文件系统与数据库一致：
  - 报告存储目录、推理素材目录等物理路径需要与用户维度保持一致，避免“磁盘全局共享，数据库按用户”的不一致状态。
- 路由层的权限控制：
  - 引入统一依赖，如 `require_user`、`require_admin`，在路由定义处声明接口要求的角色，避免在业务内部散落判断。
- 渐进改造策略：
  - 优先改造“读取类接口”，确保“每个人只能看到自己的报告/配置”；
  - 再改造“写入、删除类接口”，确保用户只能操作自己的资源；
  - 最后再考虑角色体系（管理员可跨用户查看/管理）和更细粒度的权限控制。

本文件后续将作为多用户重构的“差距清单”，与原始的 `user_auth_plan.md` 配合使用：  
- `user_auth_plan.md`：描述“目标架构与最佳实践”；  
- 本文件：描述“现状与缺口 + 按模块拆分的改造任务”。  
后续每完成一处改造，可在此文件中勾选对应任务或补充实施细节。

---

## 7. 第一阶段实施路线（建议，可逐项打勾）

> 目标：在不大改整体架构的前提下，先让“报告相关接口”具备最基本的多用户隔离能力，尤其是“每个人只能查/管自己的报告”。

### 7.1 基础设施准备

- [x] 在数据库中为关键实体增加用户维度字段：
  - `report_name` 表增加 `owner_user_id`（或等价字段）。(已确认存在 `user_id` 字段)
  - 已存在的“合并报告/生成结果”表（如果有）同样增加 `owner_user_id`。
  - LLM 配置、提示词、推理素材等如需要用户隔离，也预留 `owner_user_id`。
- [ ] 为历史数据确定归属方案：
  - 简单方案：统一归属到一个管理员账号（如 `admin`）。
  - 如已有操作日志，可按“首次/最近操作人”推导归属。

> 说明：这一阶段主要是“加字段 + 补数据”，不要求马上接入代码。

### 7.2 认证依赖与当前用户获取方式

- [x] 在 `utils/lyf/auth_utils.py` 基础上，新增统一的“获取当前用户”工具（示意）：
  - 例如：`get_current_user` / `require_user`，负责：
    - 从 Header 中解析 JWT。
    - 调用 `verify_token` 校验合法性与过期时间。
    - 查询数据库确认用户存在且 `is_active`。
    - 将用户对象或精简后的 `CurrentUser`（id、username、roles）返回。
- [x] 在 `routers` 层引入依赖注入：
  - FastAPI 风格：在路由函数签名中增加 `current_user = Depends(require_user)`。
  - 后续所有需要登录的接口统一使用该依赖，而不是自己解析 Token。
- [ ] 明确“无需登录的接口”清单：
  - 例如：`/auth/login`、健康检查 `/health`。
  - 其余默认视为“需要登录”，避免遗漏。

> 这一部分实现完，就有了统一的“当前登录用户”注入机制，为后面所有改造提供基础。

### 7.3 报告列表与浏览：按用户隔离（与“只能看自己的报告”强相关）

- [ ] 报告列表接口 `/Query_report/`：
  - 将 `get_all_reports_list()` 改为接收 `user_id` 参数，例如 `get_all_reports_list(user_id: int)`。
  - SQL 中增加 `WHERE n.owner_user_id = :user_id` 条件。
  - 在 `Query_report_endpoint` 中：
    - 使用 `current_user.id` 调用底层函数。
    - 保持原有返回结构不变（前端无需感知多用户逻辑）。
- [ ] 报告浏览接口 `/Browse_Report/` & `/Browse_MD_Report/`：
  - 在进入逻辑前通过 `current_user` 注入当前用户。
  - 把“报告文件路径”的构造与数据库记录绑定：
    - 建议通过数据库先确认“该 `type_name` + `report_name` 是否属于当前用户”；
    - 再从记录中取文件路径，而不是仅凭入参拼接物理路径。
  - 如暂时不改底层存储结构，可先在 SQL 层做用户过滤，防止跨用户读取。
- [ ] 在线编辑接口 `/Get_Content/` & `/Save_Content/`：
  - 在调用 `get_file_path(...)` 前，先通过数据库确认“该 Word 文件对应的报告是否属于当前用户”。
  - 如果不属于当前用户，直接返回权限不足错误（例如 `report_generation_status = 1`，附加“无权限访问此报告”说明）。

> 完成这一小节后，“查报告列表 + 打开具体报告 + 在线编辑”这条链路就具备了按用户隔离的最小闭环。

### 7.4 报告创建、导入、合并与删除：绑定 owner

- [ ] 创建目录接口 `/Create_Catalogue/`：
  - `generate_merged_report_from_json` 内部在创建报告记录时，将 `owner_user_id` 设置为 `current_user.id`。
  - 避免直接信任前端请求中的 `agentUserId`。
- [ ] 导入接口 `/Import_Doc/`：
  - `process_document` 在入库时写入 `owner_user_id = current_user.id`。
  - 如当前物理路径无法按用户分目录，可先只在数据库层区分 owner，后续再迁移文件结构。
- [ ] 合并与删除接口：
  - `/merge_report_file/`、`/Delete_Merged_Reports_Batch/`、`/delete_report_batch/` 均需增加“归属校验”：
    - 在执行操作之前，根据传入的 `type/name` 或 `id` 查询记录。
    - 校验 `owner_user_id == current_user.id`（或当前用户为管理员）。
    - 不满足则拒绝操作。

> 这一节完成后，用户之间将无法互相“误删/误合并”彼此的报告。

### 7.5 LLM 配置与提示词（按需选择）

- [ ] LLM 配置：
  - `save_custom_config` / `delete_config` 增加 `user_id` 参数，按用户维度读写。
  - 查询 LLM 模型的接口（如 `query_llm_models_endpoint`）仅返回当前用户名下的模型配置。
- [ ] 提示词：
  - 若决定支持“私有提示词”：
    - 提示词表增加 `owner_user_id` 和 `is_public` 字段。
    - 查询接口默认返回：
      - 当前用户自己的私有提示词；
      - 所有标记为 `is_public = 1` 的公共提示词。
- [ ] 推理素材：
  - 上传路径调整为 `inferrence/{user_id}/{folder_name}`，与数据库记录中的 `user_id` 对齐。

> 这一块与“报告归属”相比优先级略低，可在报告链路稳定后再做。

### 7.6 风险控制与回滚策略（建议）

- [ ] 所有涉及“增加字段”的数据库变更，提前写好 SQL 脚本和回滚脚本。
- [ ] 为生产库导出当前核心表的结构与数据快照（至少包含报告与配置相关表）。
- [ ] 在灰度环境先接入 JWT 校验与 owner 约束：
  - 使用同样的数据结构，先在测试/预发布环境验证一轮；
  - 确认不会出现“老数据全部看不到”或“误判归属”的极端情况。

---

## 8. 后续阶段展望（与 user_auth_plan.md 呼应）

在第一阶段完成“按用户隔离 + 基本权限校验”后，可以再逐步实现 `user_auth_plan.md` 中提到的进阶能力：

- 角色与权限（RBAC）：
  - 在 `users` 和 `roles` 体系基础上，实现：
    - `require_admin` 等更细粒度的依赖。
    - 区分普通用户与管理员在报告管理、用户管理上的能力。
- 用户管理接口：
  - `GET /api/users`、`POST /api/users`、`PATCH /api/users/{id}`、`DELETE /api/users/{id}` 等。
  - 用于在后台统一管控用户状态（启用/禁用）、角色分配等。
- 日志与审计：
  - 针对“报告创建/删除/导入/合并”等关键操作记录审计日志，至少包含：
    - 操作者 ID、时间、操作类型、目标对象。
  - 可与现有日志体系结合，按需增加结构化日志。

这些内容暂不展开到接口级别，等第一阶段落地后，再根据实际使用情况细化。

