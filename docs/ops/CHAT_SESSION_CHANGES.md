# 会话记录管理与上下文记忆：实现变更记录

本文档记录 `generate_report_test` 与前端 `note-prompt` 在“类似 GPT 网页端”的会话记录管理与上下文记忆能力上的实现与关键变更。

## 目标

- 支持多会话：每个会话独立保存消息历史与上下文状态
- 支持续聊：前端可通过 `session_id` 加载历史并继续对话
- 支持流式：对话接口使用 SSE 返回内容分片
- 资源优化：用户点击“新对话”不立刻写库，首次发消息才创建会话记录

## 后端接口与行为

### 1) 流式对话（SSE）

- 接口：`POST /api/ai/chat/v2/prompt_chat/stream`
- 入参：
  - `query`: string（必填）
  - `session_id`: number（可选；不传代表新会话）
- 行为：
  - 若不传 `session_id`：后端在收到首条消息时创建会话，并在 SSE 首帧返回 `meta.session_id`
  - 若传 `session_id`：后端校验该会话归属当前用户，不通过返回 404

### 2) 会话管理（用于会话列表/历史回放）

- `GET /api/ai/chat/v2/sessions`
  - 返回当前用户的会话列表（按更新时间倒序）
- `GET /api/ai/chat/v2/sessions/{session_id}/messages`
  - 返回会话消息历史（按时间正序）
- `PATCH /api/ai/chat/v2/sessions/{session_id}`
  - 重命名会话标题
- `DELETE /api/ai/chat/v2/sessions/{session_id}`
  - 若表存在 `status` 字段：软删除（`status=deleted`，数据库存储为 `-1`）
  - 否则：删除会话、消息、上下文状态记录

## 前端交互与行为（重要变更）

### 1) “新对话”不落库

- 用户点击“新对话”：
  - 前端仅切换到本地草稿态（清空对话区、移除 URL 上的 `session_id`）
  - 不请求后端创建会话记录
- 用户在草稿态发送第一条消息：
  - 前端调用流式接口且不带 `session_id`
  - 接收 SSE 首帧 `meta.session_id` 后，前端再把 `session_id` 写回 URL，并刷新会话列表

### 2) 会话列表支持“草稿态”

- 左侧列表顶部固定显示“新对话”入口（草稿态）
- 只有当用户真正发过消息并由后端创建会话后，该会话才会出现在数据库与会话列表中

## 上下文记忆机制

- 短期记忆：从 `ai_chat_messages` 中读取滑动窗口范围内的消息
- 长期记忆：从 `ai_chat_context_state.history_content` 注入摘要（作为 system 消息）
- 自动压缩：对话轮次超过阈值时，异步将前半段对话压缩进摘要，并推进窗口起点

## 配置对齐与稳定性

- 数据库连接使用环境变量 `REPORT_DB_*`（由 `.env` 或 docker-compose 注入）
- 对话会话相关逻辑不再在代码中自动创建数据库表结构（避免在已有生产表结构下产生误操作的风险）
- **状态映射**：代码层使用字符串状态（`active`, `deleted`），数据库层使用整数状态：
  - `active` -> `0` (进行中)
  - `completed` -> `1` (已保存)
  - `archived` -> `2` (已归档)
  - `deleted` -> `-1` (已删除)

## 可见效果

- 新对话不会生成“空会话”脏数据：只有真正开始聊天才写入会话与消息
- URL 具备可分享/可恢复能力：带 `session_id` 的页面可回放历史并继续聊
- 会话隔离明确：不同会话上下文不会互相污染
