# AI 对话隔离与并发优化计划（基于现有实现的审计结果）

目标：在不改变当前业务语义的前提下，确保 **对话之间不串号（按会话隔离）**，并能在 **几十人同时在线（SSE + 流式生成）** 的情况下保持稳定可用、可扩容、可观测。

审计范围聚焦在 `/api/ai` 路径下的对话/提示词相关能力，入口路由为 [lyf_router.py](file:///root/zzp/langextract-main/generate_report_test/routers/lyf_router.py)。

---

## 1. 现状梳理（你关心的两点：隔离 & 并发）

### 1.1 路由与实现分叉：同一业务存在两套“对话实现”

`/api/ai` 下同时暴露了两套聊天能力（同属 “Prompt” 语义，但隔离模型不同）：

- 旧实现（仍对外暴露）：[prompt_chat_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api.py) → [prompt_chat.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat.py)
  - 以 `user_id` 作为 key 存 “进程内内存” 历史（同一用户的多个窗口会互相污染）
  - 无 `session_id` 概念，隔离粒度是“用户”，不是“会话”
  - 重启/多 worker 时历史丢失或不一致

- 新实现（主要对话）：[prompt_chat_api_v2.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api_v2.py) → [prompt_chat_async.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py)
  - 以 `session_id` 为核心，消息与上下文落库（`ai_chat_sessions / ai_chat_messages / ai_chat_context_state`）
  - 接口层会通过 `get_session_meta(session_id, user_id)` 做归属校验，防止跨用户访问
  - 支持“摘要 + 窗口内消息”的上下文策略：见 [ContextManager](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py)

结论（隔离）：**新实现已经具备“按 session 隔离”的基础能力**；但由于旧接口仍暴露，且部分实现细节存在“隔离依赖于接口层”的脆弱点，需要进一步加固。

---

### 1.2 新实现（v2）隔离现状评估

已具备：

- “会话归属校验”在接口层显式执行：例如 [prompt_chat_api_v2.py:chat_stream_endpoint](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api_v2.py#L42-L92)
  - 传入 `session_id` 时校验归属，不通过直接 404
  - 不传 `session_id` 时创建新会话并返回 `session_id`
- 历史消息按 `session_id` 读取，摘要状态按 `session_id` 维护：见 [PromptChat.get_messages](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py#L317-L348)、[ContextManager.get_active_payload](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py#L38-L77)

主要风险点（隔离）：

- Service 层 `chat_stream(session_id, query)` 不携带 `user_id`，也不自校验 `session_id` 归属（它假设调用方已校验）：见 [PromptChat.chat_stream](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py#L676-L748)
  - 如果未来有其它入口复用该方法、或出现调用链绕过接口层校验，会带来跨用户读写同一 session 的风险（属于“防线单点”问题）
- 旧接口仍对外暴露：同一用户多窗口并行时，旧接口会把所有窗口写进同一条内存会话，造成“窗口互相污染”

结论（隔离）：**v2 目前“基本做对了”，但仍需要：**
1) 关闭/下线旧入口，避免业务层出现两套隔离模型；  
2) 将“归属校验”下沉到 Service 层，避免只依赖路由层。

---

### 1.3 并发现状评估（几十人同时在线）

当前生产启动方式基本是单 worker：见 [docker-compose.yml](file:///root/zzp/langextract-main/generate_report_test/docker-compose.yml#L51-L94)、[Dockerfile](file:///root/zzp/langextract-main/generate_report_test/Dockerfile#L1-L28)

关键并发控制点：

- v2 主对话 LLM 调用有全局信号量 `MAX_CONCURRENCY=8`：见 [Config.MAX_CONCURRENCY](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/db_async_config.py#L8-L45)、[PromptChat.__init__](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py#L16-L26)
  - 优点：保护上游 LLM（避免瞬时把 LLM 打挂）
  - 代价：当 30~50 个用户同时发起生成时，会出现“排队等待吐字”的体验，且若前面有网关超时，排队会变成请求失败

- 数据库连接池：`pool_size=10, max_overflow=5`：见 [db_async_config.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/db_async_config.py#L48-L61)
  - 对“几十个并发 SSE 连接 + 频繁读写消息”的场景可能偏紧，尤其当其它业务也共用同库

重大并发风险点（需要优先关注）：

1) **摘要生成不受信号量保护**  
`compress_if_needed()` 内部会调用 `_generate_summary()` 直接请求模型，但没有走 `PromptChat.semaphore`：见 [ContextManager.compress_if_needed](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py#L79-L131)、[ContextManager._generate_summary](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py#L132-L138)
   - 在高并发下会形成“后台压缩风暴”（每个会话都在 create_task 里触发一次），导致 LLM 被额外放大流量打满

2) **多个 async 接口里执行同步 OpenAI 流式调用，会阻塞事件循环**  
例如：
   - [prompt_test_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_test_api.py) 内部 `for chunk in test_service.run_test_stream(...)`，而 `run_test_stream` 使用同步 OpenAI client：见 [prompt_test.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_test.py#L11-L44)
   - [prompt_optimize_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_optimize_api.py) 内部 `for chunk in prompt_optimize_service.optimize_stream(...)`，而 `optimize_stream` 同样是同步 OpenAI client：见 [prompt_optimize.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_optimize.py#L19-L52)
   - 结果：在单 worker 情况下，这类接口一旦被并发调用，会拖慢甚至“卡死”其它真正 async 的 SSE（包括 v2 对话）

结论（并发）：如果你说的“几十人并发”包含对话/优化/测试同时使用，当前实现存在显著的事件循环阻塞风险与后台摘要风暴风险；单靠 `MAX_CONCURRENCY=8` 不足以保证稳定。

---

## 2. 风险清单（按优先级）

### P0（高概率/高影响，建议先处理）

- 旧对话接口仍暴露，且以 `user_id` 为会话 key，天然会话污染：[prompt_chat_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api.py)、[prompt_chat.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat.py)
- 摘要生成未受并发保护，可能在高并发下放大 LLM QPS：[context_manager.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py)
- async 接口执行同步 OpenAI 流式，阻塞事件循环：  
  [prompt_test_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_test_api.py) + [prompt_test.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_test.py)；  
  [prompt_optimize_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_optimize_api.py) + [prompt_optimize.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_optimize.py)

### P1（中概率/中影响，建议纳入同一轮优化）

- Service 层关键方法不携带 `user_id`，隔离依赖接口层（防线单点）：[prompt_chat_async.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py#L676-L748)
- 缺少“按用户/按 IP 的 SSE 并发数限制、速率限制”，易被滥用导致资源耗尽（目前未见统一限流层）
- 数据库/Redis/LLM 的连接与超时参数未统一（例如 v2 AsyncOpenAI 未显式传入 httpx 超时配置），故障时可能表现为长时间挂起

### P2（低概率/长期演进）

- `session_id` 自增可枚举（虽有归属校验，仍建议逐步引入 `client_session_uuid` 或分享/引用用 UUID）
- 秘钥/密码管理存在硬编码默认值风险：见 [db_async_config.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/db_async_config.py#L8-L15)、[auth_utils.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/auth_utils.py#L165-L172)、[docker-compose.yml](file:///root/zzp/langextract-main/generate_report_test/docker-compose.yml#L71-L82)

---

## 3. 优化路线图（不改语义，先稳定，再扩容）

### 阶段 A：先把“隔离模型统一”与“事件循环不阻塞”做扎实（推荐优先）

1) 统一对话入口（避免两套隔离模型并存）
   - 生产环境对外只保留 v2（`/api/ai/chat/v2/...`）
   - 旧接口（`/api/ai/chat/...`）做下线/灰度：至少在网关层或路由层禁用，或仅管理员可用

2) 修复 async 端点阻塞问题（确保单 worker 也能抗几十 SSE）
   - 对同步 OpenAI 流式的能力（prompt_test / prompt_optimize 等），二选一：
     - 方案 1：将端点改成 `def` + 同步 generator（让框架线程池承载）
     - 方案 2：将底层改为 `AsyncOpenAI` + async generator（统一为真正异步）

3) 摘要/标题生成纳入统一并发治理
   - 摘要生成走统一并发阈值（可与主生成分开：主生成 8、摘要 1~2、标题 1~2）
   - 给摘要任务增加失败兜底：失败不影响主对话完成；并确保 create_task 的异常可观测

验收标准（阶段 A）：
   - 50 个并发 SSE 连接时，服务仍能接受请求、能持续吐字（可排队但不能整体卡死）
   - 压测期间无大量 “Task exception was never retrieved” 类日志
   - 不同 session 的历史加载与继续对话不互相污染

---

### 阶段 B：把“隔离防线”从接口层下沉到 Service/DAO（防止未来回归）

1) Service 层接口统一要求 `user_id`（关键入口都做归属校验）
   - 对任何写 `ai_chat_messages / ai_chat_context_state` 的路径，在 service 内先校验 session 归属

2) 数据库索引与查询形态梳理（为高并发读写做准备）
   - 对高频查询建议具备（按现有 SQL 形态推断）：
     - `ai_chat_sessions(user_id, update_time)` 或 `ai_chat_sessions(user_id, id)`
     - `ai_chat_messages(session_id, id)`、`ai_chat_messages(session_id, round_index)`
     - `ai_chat_context_state(session_id)`（PK）
   - 确认 `content` 字段类型（建议 LONGTEXT），避免大回复写入失败

3) 数据清理策略
   - 会话软删与消息软删字段（代码已做字段存在性探测：`is_deleted`），建议明确统一策略与清理任务

验收标准（阶段 B）：
   - “任何直接调用 service 方法”的入口也不会越权读写别人的 session
   - DB 慢查询显著减少，连接池稳定，不出现频繁 pool timeout

---

### 阶段 C：扩容到多 worker / 多实例（承载能力上台阶）

前置条件：阶段 A + B 完成（尤其是“阻塞修复”和“关键状态落地”）。

1) 启用多 worker（例如 uvicorn/gunicorn workers）
   - SSE 本质是长连接，单 worker 能接很多连接，但 CPU/IO 抖动时需要多 worker 分摊
   - 多 worker 之前必须确保“对话状态不依赖进程内内存”

2) 统一状态外置（Redis/DB）
   - 当前 v2 对话已落库；其它模块若仍用进程内会话（仓库已有 Redis 迁移方案文档），需对齐隔离 key 必含 `user_id`
   - 参考已有文档：[REDIS_INTRO_DOCKER_PLAN.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/REDIS_INTRO_DOCKER_PLAN.md)

验收标准（阶段 C）：
   - 多 worker 下同一 session 的连续对话不“断上下文”
   - 单个 worker 重启不影响整体服务

---

## 4. 压测与观测计划（建议你评判时重点看“验收口径”）

### 4.1 关键指标（必须量化）

- SSE：首 token 延迟（TTFT）、平均吞吐（token/s）、断连率
- LLM：并发占用、429/限流错误率、平均生成时长
- DB：连接池占用、慢查询数、写入失败率
- 服务端：事件循环卡顿（可用简单心跳任务/日志观察）、CPU、内存

### 4.2 压测场景（从简单到真实）

1) 仅 v2 对话：50 并发用户，每人 1 个 session，持续 2~5 分钟  
2) v2 对话 + 摘要触发：每人连续多轮对话，确保触发 `SUMMARY_THRESHOLD`  
3) 混合场景：对话 + optimize + test 同时跑（这是最容易暴露“阻塞事件循环”的场景）  
4) 异常场景：模拟 LLM 超时/断流，观察是否影响其它连接与是否堆积后台任务

---

## 5. 建议的“你来拍板”决策点（我建议你评判时就看这些）

1) 是否在生产对外**彻底下线旧 `/api/ai/chat`**（只保留 `/api/ai/chat/v2`）  
2) “几十人并发”的目标是否允许排队（例如最多同时生成 8 个，其余等待），还是要求“尽量同时响应”  
3) 摘要策略是否必须实时（对话结束立刻压缩），还是可以后台慢慢做（降低峰值压力）  
4) 是否准备进入多 worker / 多实例（如果准备，则必须更严格地消灭进程内状态）

---

## 6. 附：与当前实现强相关的代码入口索引

- `/api/ai` 总入口聚合：[lyf_router.py](file:///root/zzp/langextract-main/generate_report_test/routers/lyf_router.py)
- v2 对话路由（推荐主用）：[prompt_chat_api_v2.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api_v2.py)
- v2 对话 Service（落库 + SSE）：[prompt_chat_async.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py)
- 上下文窗口/摘要（当前存在并发治理缺口）：[context_manager.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/context_manager.py)
- 旧对话（会话污染风险）：[prompt_chat_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/prompt_chat_api.py)、[prompt_chat.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat.py)
- 同步 OpenAI 流式（阻塞风险源头）：[prompt_optimize.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_optimize.py)、[prompt_test.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_test.py)

