# 对话系统全流程设计方案（会话隔离 / 记忆管理 / SSE 流式）

本文给前后端提供一套可落地的“完整对话流程”设计：从新建对话、发送消息、流式回包、落库、历史加载，到上下文窗口与摘要的隔离与不污染。  
参考了现有实现 [prompt_chat_api.py](file:///root/zzp/langextract-main/promptSys/routers/prompt_chat_api.py)，并修正其在“以 user_id 代替 session_id”造成的会话污染问题。

---

## 0. 现状与问题解释：为什么没有写入 ai_chat_sessions？

在参考实现 [prompt_chat_api.py](file:///root/zzp/langextract-main/promptSys/routers/prompt_chat_api.py#L20-L39) 中：

- 请求体只有 `query`，没有 `session_id`
- 服务端把 `user_id = str(current_user.id)` 直接当作“多轮对话标识”
- 因为没有“创建会话”这一层概念，服务端也就没有机会往 `ai_chat_sessions` 插入一条会话记录

这会导致两类现象：
- **刷新页面后前端记录没了**：前端的消息列表通常存在内存/本地状态中，刷新即丢；如果没有“从后端拉历史消息”的能力，看起来就像没落库。
- **但对话记忆还在**：服务端以 `user_id` 作为 key 保存上下文/摘要/窗口状态，用户不变 => key 不变 => 上下文一直延续，导致“同一用户所有窗口互相污染”。

---

## 1. 目标（必须满足）

- 真正的“会话隔离”：不同对话（session）互不影响，上下文不会串。
- 支持“刷新恢复”：刷新后仍能加载该 session 的历史消息。
- 支持“多窗口并行”：同用户多个对话窗口同时进行，互不污染。
- 支持 SSE 流式输出：边生成边展示，避免长等待。
- 可靠落库：用户消息和 assistant 消息都必须写入 `ai_chat_messages`，并能追溯。
- 上下文管理可控：窗口滑动 + 长期摘要，且摘要只作用于该 session。

---

## 2. 核心数据模型（建议）

### 2.1 表：ai_chat_sessions（会话表）

用途：存“对话这个容器”，用于列表、恢复、权限校验。

建议字段：
- `id`（PK，自增）
- `user_id`（索引）
- `title`（可为空；首轮异步生成后回填）
- `status`（active/archived/deleted，可选）
- `create_time` / `update_time`
- `client_session_uuid`（可选，用于前端幂等创建）

### 2.2 表：ai_chat_messages（消息表）

用途：存每一轮的 user/assistant 消息。

建议字段：
- `id`（PK，自增）
- `session_id`（索引）
- `round_index`（同会话内轮次，用于上下文窗口）
- `role`（user/assistant/system）
- `content`（LONGTEXT）
- `create_time`

### 2.3 表：ai_chat_context_state（上下文状态表）

用途：记录该会话的“长期摘要 + 窗口起点”，实现不污染。

建议字段：
- `session_id`（PK）
- `window_start_round`
- `history_content`（长期摘要）
- `update_time`

---

## 3. 后端接口设计（建议最小闭环）

### 3.1 创建新对话（推荐独立接口）

**POST** `/api/ai/chat/v2/sessions`

请求：
```json
{
  "title": "可选，前端手填或空"
}
```

响应：
```json
{
  "session_id": 123,
  "title": "新对话",
  "create_time": "..."
}
```

语义：
- 创建会话记录到 `ai_chat_sessions`
- 初始化 `ai_chat_context_state`（插入默认 window_start_round=1）
- 返回 `session_id` 给前端保存

### 3.2 获取会话列表

**GET** `/api/ai/chat/v2/sessions?status=active`

响应：
```json
[
  { "session_id": 123, "title": "xxx", "update_time": "..." }
]
```

### 3.3 获取历史消息

**GET** `/api/ai/chat/v2/sessions/{session_id}/messages?limit=200`

响应：
```json
[
  { "role": "user", "content": "...", "create_time": "..." },
  { "role": "assistant", "content": "...", "create_time": "..." }
]
```

### 3.4 流式对话（SSE）

**POST** `/api/ai/chat/v2/prompt_chat/stream`

请求（必须带 session_id）：
```json
{
  "session_id": 123,
  "query": "用户输入"
}
```

响应（SSE）：
- `data: {"content":"..."}`
- `data: [DONE]`

#### 重要约束
- 如果 `query` 为空或只有空白：直接 400（前后端都要拦）
- 服务端必须校验：`session_id` 必须归属 `current_user.id`

### 3.5 可选：重命名 / 归档 / 删除

- **PATCH** `/api/ai/chat/v2/sessions/{session_id}`（更新 title）
- **POST** `/api/ai/chat/v2/sessions/{session_id}/archive`
- **DELETE** `/api/ai/chat/v2/sessions/{session_id}`（软删/硬删按需）

---

## 4. 后端处理流程（推荐实现顺序）

### 4.1 创建会话

1. 插入 `ai_chat_sessions(user_id, title=默认“新对话”)`
2. 插入 `ai_chat_context_state(session_id, window_start_round=1, history_content=NULL)`
3. 返回 `session_id`

### 4.2 发送消息（非流式阶段：落库与构造上下文）

当收到（session_id, query）时：

1. 校验 session 所属 user_id
2. 计算 `current_round = max(round_index)+1`
3. 插入 user 消息到 `ai_chat_messages`
4. 查询 `ai_chat_context_state`：
   - 如果有 `history_content`，注入为 system（长期记忆）
   - 从 `window_start_round` 开始拉取窗口内消息（短期记忆）
5. 构造 messages 列表给模型

### 4.3 流式生成（SSE）

1. 调用模型 `stream=True`
2. 每个 token/chunk：
   - 通过 SSE 推送给前端
   - 同时累积到 `full_response`
3. stream 结束：
   - 插入 assistant 消息到 `ai_chat_messages`
   - 异步触发 `compress_if_needed(session_id, current_round)`

### 4.4 上下文压缩（不污染）

以“会话内轮次”为单位滑动窗口：

- 如果 `(current_round - window_start_round) >= SUMMARY_THRESHOLD`
  - 把前半部分消息（<= compress_end）聚合为 `text_to_sum`
  - 调用模型产出 `new_summary`
  - 更新 `ai_chat_context_state.history_content = new_summary`
  - 更新 `window_start_round = compress_end + 1`

该摘要只写入该 `session_id`，天然隔离。

---

## 5. 前端需要做什么（UI + 状态 + 请求/接收）

### 5.1 UI 改造（建议最小必要）

在 PromptStudio 对话区域增加：
- **会话列表（左侧/顶部）**
  - 显示 title + 更新时间
  - 点击切换 session
- **“新建对话”按钮**
  - 点击后创建新 session，并清空当前对话面板
- **“清空上下文/重置对话”按钮**
  - 本质是“创建新 session 并切换过去”
- 可选：重命名、归档

### 5.2 前端状态管理

必须持久化两个东西：
- `currentSessionId`：当前对话的 session_id
- `messages[]`：当前页面渲染的消息列表（可从后端拉取恢复）

建议策略：
- 路由带参：`/prompt-studio?session_id=123`
  - 刷新恢复最简单
  - 也方便多窗口：每个 tab 一个 URL
- 或 localStorage：`last_session_id`（不建议用于多窗口隔离）

### 5.3 前端请求流程（推荐）

#### 进入页面
1. 如果 URL 有 `session_id`：拉历史消息 `GET /sessions/{id}/messages`
2. 如果没有：
   - 自动创建新会话 `POST /sessions`
   - 将返回的 `session_id` 写入 URL

#### 用户发送一条消息
1. 前端拦截空输入（trim 为空则不发）
2. UI 先插入一条 user 消息（optimistic）
3. 发起 SSE 请求：
   - body 必须携带 `{ session_id, query }`
4. SSE 接收：
   - 每个 `content` 追加到“正在生成的 assistant 消息气泡”
   - 收到 `[DONE]` 标记生成结束
5. 完成后可选择：
   - 更新会话列表（刷新更新时间、title）

### 5.4 多窗口隔离规则

- **不同 tab 只要 session_id 不同，就不会互相污染**
- 避免“自动复用 last_session_id”导致多个 tab 共享同一个 session
- 最佳实践：以 URL 的 session_id 为准，不要全局单例 session

---

## 6. SSE 协议细节建议

为了让前端更好处理，建议统一输出结构：

- 内容：`data: {"type":"content","content":"..."}`
- 结束：`data: {"type":"done"}`
- 错误：`data: {"type":"error","message":"..."}`

（当前实现使用 `{"content":...}` + `[DONE]` 也可，但建议统一成带 type 的 JSON，便于扩展。）

---

## 7. 安全与一致性（必须）

- 权限：所有 `session_id` 相关接口都必须校验归属 `current_user.id`
- 并发：同一 session 的并发发送要么串行，要么后端拒绝/排队（避免 round_index 乱序）
- 幂等：创建会话可用 `client_session_uuid` 避免重复创建
- 输入校验：拒绝空 query；限制单次 query 最大长度
- 落库一致性：user 消息与 assistant 消息落库应保证最终一致（失败要有错误记录/重试策略）

---

## 8. 与现有代码的对齐点

当前参考实现 [prompt_chat_api.py](file:///root/zzp/langextract-main/promptSys/routers/prompt_chat_api.py) 的关键点是：
- SSE 输出格式（`data: ...\n\n`）
- 认证依赖（`require_user`）

需要修正的是：
- 用 `session_id` 作为对话主键，而不是 `user_id`
- 增加会话创建与历史读取闭环（否则刷新无法恢复）

