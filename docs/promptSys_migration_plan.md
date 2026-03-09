# PromptSys 功能增量迁移计划

## 0. 适用范围与对齐说明
- 本文是“从 promptSys 迁移到 generate_report_test”的实施计划，偏工程步骤与风险控制。
- 对接与协议以 [API_V2_GUIDE.md](file:///root/zzp/langextract-main/generate_report_test/docs/API_V2_GUIDE.md) 为准；对话全流程与会话隔离以 [CHAT_DIALOGUE_FLOW_PLAN.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/CHAT_DIALOGUE_FLOW_PLAN.md) 为准。
- 接口路径在不同工程/网关挂载下可能不同：`/chat/v2/...` 仅代表路由层 prefix 示例；当前 generate_report_test 对外实际路径以 `/api/ai/chat/v2/prompt_chat/stream` 为准（详见 API_V2_GUIDE）。

## 1. 现状分析与目标
目前 `generate_report_test` 项目中的 `routers/lyf_router.py` 及其引用的 `utils/lyf/prompt_chat.py` 是一个**旧版本的同步实现**，存在以下局限性：
- **数据易失**：使用内存 (`SessionManager`) 存储对话历史，重启即丢失。
- **并发能力弱**：核心逻辑为同步代码，高并发下可能阻塞。
- **功能缺失**：缺少数据库持久化、Token 精细管理 (`ContextManager`)、自动标题生成等 `promptSys` 中的高级功能。

**目标**：在不破坏现有功能的前提下，将 `promptSys` 的数据库持久化、异步流式处理和高级上下文管理功能增量迁移至 `generate_report_test`。

---

## 2. 迁移前置准备 (Phase 0)

### 2.1 依赖检查
`promptSys` 使用了异步数据库驱动 `aiomysql`，而 `generate_report_test` 目前仅有 `pymysql`。
- **动作**：需要在环境中安装 `aiomysql`。
  ```bash
  pip install aiomysql
  ```

### 2.2 数据库表结构同步
`promptSys` 依赖三张核心表，需要在目标数据库中创建（如果不存在）：
1. `ai_chat_sessions` (会话元数据)
2. `ai_chat_messages` (具体对话内容)
3. `ai_chat_context_state` (上下文窗口状态)

补充：
- 若你的环境已存在上述表，仅需确认字段满足 V2 的最小需求（例如 `ai_chat_messages.round_index`）。
- 会话隔离建议以 `session_id` 作为上下文主键，避免使用 `user_id` 直接充当会话标识导致污染。

---

## 3. 增量迁移步骤

### 阶段一：核心组件移植 (Core Migration)
**策略**：不要直接覆盖现有文件，而是创建新文件，保持 V1 (旧) 和 V2 (新) 并存。

1.  **移植数据库配置**
    - 创建 `utils/lyf/db_async_config.py`。
    - 参照 `promptSys/utils/base_prompt_ai.py`，配置 `AsyncSession` 和 `create_async_engine`。
    - **注意**：复用 `server_config.py` 中的环境变量（如 `REPORT_DB_USER` 等）。

2.  **移植核心工具类**
    - 从 `promptSys/utils/` 复制以下文件到 `generate_report_test/utils/lyf/`：
        - `chat_message_record.py` (负责写库)
        - `context_manager.py` (负责 Token 计算与窗口滑动)
    - **修改 import 路径**：确保它们指向新的 `db_async_config`。

### 阶段二：业务逻辑升级 (Service Upgrade)

1.  **创建 V2 版 Chat Service**
    - 创建 `utils/lyf/prompt_chat_async.py` (对应 `promptSys` 的 `prompt_chat.py`)。
    - **关键修改**：
        - 将 `from base_prompt_ai import ...` 改为使用新的 `db_async_config`。
        - 确保 `AsyncOpenAI` 的 `api_key` 和 `base_url` 读取 `server_config.py` 中的配置。
        - 保留 `promptSys` 中的 `chat_stream` 异步逻辑。

### 阶段三：路由层接入 (Router Integration)

1.  **创建 V2 版 Router**
    - 创建 `routers/prompt_chat_api_v2.py`。
    - 复制 `promptSys/routers/prompt_chat_api.py` 的内容。
    - 修改 import，指向 `utils/lyf/prompt_chat_async.py`。
    - **增强点**：确保 `Depends(require_user)` 能正确获取 `user_id`。

2.  **注册新路由**
    - 在 `routers/lyf_router.py` 中，**新增** V2 路由挂载，保留旧路由作为兜底。
    ```python
    # 原有路由保持不变 (V1)
    router.include_router(prompt_chat_api.router, prefix="/chat", tags=["LYF-Prompt-V1"])

    # 新增 V2 路由 (指向新功能)
    from routers import prompt_chat_api_v2
    router.include_router(prompt_chat_api_v2.router, prefix="/chat/v2", tags=["LYF-Prompt-V2-Async"])
    ```

---

## 4. 验证与切换 (Verification & Switch)

1.  **功能验证**：
    - 调用（示例）`/api/ai/chat/v2/prompt_chat/stream` 接口（以部署挂载为准）。
    - 验证数据库 `ai_chat_messages` 表是否新增了记录。
    - 验证多轮对话是否能正确回忆起上下文。

2.  **前端切换**：
    - 当 V2 接口验证稳定后，前端将请求路径从 `/chat/...` 切换到 `/chat/v2/...`。

3.  **清理 (Cleanup)**：
    - 确认无流量访问 V1 接口后，删除旧的 `prompt_chat_api.py` 和 `utils/lyf/prompt_chat.py`。
    - 将 `prompt_chat_api_v2` 重命名为 `prompt_chat_api`。

## 5. 风险控制
- **依赖冲突**：`aiomysql` 与 `pymysql` 可共存，无冲突风险。
- **数据兼容**：V1 使用内存，V2 使用数据库。用户在切换瞬间会丢失 V1 的内存会话上下文（可接受，因为内存本来就会丢）。
- **配置隔离**：新旧代码使用不同的配置文件或类，互不干扰。
