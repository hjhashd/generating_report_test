# Redis 引入与 Docker 灰度部署计划（面向并发、会话稳定与多用户隔离）

## 1. 背景与目标

### 1.1 背景
当前后端为 FastAPI，生产环境以 Docker Compose 的 `prod` profile 启动（见 [docker-compose.yml](file:///root/zzp/langextract-main/generate_report_test/docker-compose.yml)）。系统存在多处“进程内内存状态”，在并发、重启、未来多进程/多实例扩容时会放大风险。

### 1.2 你关心的核心问题
- AI 上下文会话稳定性：多轮对话是否会断、是否会串号。
- 前端轮询稳定性：异步任务进度轮询在并发/重启/扩容时是否丢状态。
- 多用户隔离：多用户下是否会读到他人的任务/会话/数据。
- 并发与性能：单进程（或少量 worker）能否承载更多 SSE/轮询/后台任务。

### 1.3 引入 Redis 的目标（按优先级）
1) 把“必须一致”的状态从内存迁出：任务状态、会话上下文。
2) 为未来扩容（多 worker / 多实例）铺路：请求落到任何进程都能读到同一状态。
3) 在不破坏现有接口的前提下渐进迁移：Redis 可用则用，不可用可降级。
4) 后续可扩展：缓存热点读接口、限流保护重接口。

## 2. 当前项目现状（关键调研点）

### 2.1 AI 会话上下文目前为“进程内内存字典”
- 写作生成：全局 `CHAT_SESSIONS = {}`，以 `task_id` 作为会话键（见 [ai_generate_langchain.py](file:///root/zzp/langextract-main/generate_report_test/utils/zzp/ai_generate_langchain.py#L44-L48)）。
- 润色优化：同样存在全局 `CHAT_SESSIONS = {}`（见 [ai_adjustment.py](file:///root/zzp/langextract-main/generate_report_test/utils/zzp/ai_adjustment.py#L74-L78)）。
- 联网搜索：存在全局 `SEARCH_CHAT_SESSIONS`（见 [ai_search.py](file:///root/zzp/langextract-main/generate_report_test/utils/lyf/ai_search.py#L52-L55)）。

结论：
- 单进程时：只要 `task_id` 绝对唯一，通常不串；但服务重启会丢上下文。
- 多进程/多实例时：同一 `task_id` 的请求落到不同进程会“断上下文”。

### 2.2 前端轮询任务状态目前为“进程内内存字典”
导入接口使用内存 `task_status_store` 维护状态（源码也提示生产建议 Redis/DB）：
- `task_status_store = {}`（见 [import_doc_to_db_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_doc_to_db_api.py#L18-L20)）
- 轮询接口：`/check_import_status/{task_id}`（见 [import_doc_to_db_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_doc_to_db_api.py#L125-L140)）
- 文档流程说明：见 [FRONTEND_REPORT_FLOW.md](file:///root/zzp/langextract-main/generate_report_test/docs/features/FRONTEND_REPORT_FLOW.md#L48-L85)

结论：
- 服务重启会丢任务状态。
- 多进程/多实例会出现“查不到任务”或状态不一致。

### 2.3 多用户隔离基础已具备，但状态层仍需加强
项目已基于 JWT 获取 `current_user.id`（见 [dependencies.py](file:///root/zzp/langextract-main/generate_report_test/routers/dependencies.py#L15-L41)），部分接口已做“只查自己任务”的校验（见 [import_doc_to_db_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/import_doc_to_db_api.py#L132-L139)）。

结论：
- 认证/鉴权链路已有基础。
- 需要把“任务状态 / 会话上下文”的存储 Key 命名强制带上 `user_id`，从存储层彻底杜绝串号。

## 3. 总体方案：统一 Redis 管理 + 可控灰度迁移

### 3.1 统一管理原则（避免“到处随便加 Redis”导致不可控）
1) 所有 Redis Key 必须有统一前缀（环境/项目维度）和命名规范（业务维度）。
2) 所有存储必须显式 TTL（避免永不清理导致内存不可控）。
3) 所有“会话/任务”类 Key 必须包含 `user_id`（多租户隔离）。
4) 分阶段启用：先任务状态，再会话上下文，再缓存/限流。
5) 迁移期必须支持降级（Redis 不可用时不影响现有接口可用性）。

### 3.2 Key 命名规范（建议强制执行）
统一前缀：
- `${REDIS_PREFIX}`（例如 `langextract`）
- `${ENV}`（例如 `prod/dev`）

建议 Key 模板：
- 导入任务状态：`${prefix}:${env}:task:import:${user_id}:${task_id}`
- AI 写作会话：`${prefix}:${env}:chat:generate:${user_id}:${task_id}`
- AI 润色会话：`${prefix}:${env}:chat:optimize:${user_id}:${task_id}`
- AI 搜索会话：`${prefix}:${env}:chat:search:${user_id}:${task_id}`

TTL 建议：
- 任务状态：24h（或 48h，根据业务习惯）
- 会话上下文：2h（或 6h，视平均对话长度）

容量边界建议：
- 每个会话最多保留 20 轮（40 条 message），超出截断（避免单用户无限增长）。

### 3.3 能力开关矩阵（灰度与回滚核心）
建议用环境变量控制（迁移期必须保留）：
- `REDIS_ENABLED=0/1`（总开关，默认 0）
- `REDIS_TASK_STATUS_ENABLED=0/1`（任务状态迁移）
- `REDIS_CHAT_SESSION_ENABLED=0/1`（会话迁移）
- `REDIS_CACHE_ENABLED=0/1`（缓存，可选）
- `REDIS_RATE_LIMIT_ENABLED=0/1`（限流，可选）

降级策略：
- Redis 连接失败：任务状态、会话等自动退回内存（迁移期）；并记录告警日志。
- 生产稳定后：可把“退回内存”改为“直接报错/只读”，防止静默退化。

## 4. Docker 引入 Redis：部署规划（不影响现有服务）

### 4.1 总体设计
- 在现有 `docker-compose.yml` 中新增 `redis` 服务，复用 `app_network`。
- 默认不对宿主机暴露 6379 端口（减少误用与安全风险）。
- 使用持久化卷保存 AOF/RDB 数据，避免容器重启丢状态。
- 强制密码认证，密码从 `.env` 注入（不要写死在 compose 文件里，也不要提交到仓库）。

### 4.2 推荐 Redis 配置（生产）
- 镜像：`redis:7.2-alpine`
- 持久化：开启 AOF（appendonly yes）
- 安全：`requirepass` + 仅容器网络可访问
- 健康检查：`redis-cli -a $REDIS_PASSWORD ping`

### 4.3 Compose 变更要点（示例片段，仅用于按图施工）
把以下逻辑合并到 [docker-compose.yml](file:///root/zzp/langextract-main/generate_report_test/docker-compose.yml) 的 services 下（示例使用环境变量占位符）：

```yaml
services:
  redis:
    image: redis:7.2-alpine
    container_name: langextract-redis
    command:
      - sh
      - -c
      - |
        redis-server \
          --appendonly yes \
          --requirepass "${REDIS_PASSWORD}" \
          --save 900 1 \
          --save 300 10 \
          --save 60 10000
    volumes:
      - redis_data:/data
    networks:
      - app_network
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 10

volumes:
  redis_data:
```

说明：
- `--save` 只是兜底（RDB），核心依赖 AOF。
- 不映射端口意味着只能同 compose 网络内访问（更安全）。

### 4.4 后端容器的环境变量规划
在 `app-prod` 的 `environment` 里追加（示例）：

```yaml
environment:
  REDIS_ENABLED: "0"
  REDIS_TASK_STATUS_ENABLED: "0"
  REDIS_CHAT_SESSION_ENABLED: "0"
  REDIS_HOST: redis
  REDIS_PORT: "6379"
  REDIS_PASSWORD: "${REDIS_PASSWORD}"
  REDIS_DB: "0"
  REDIS_PREFIX: "langextract"
```

说明：
- 初次上线 `REDIS_ENABLED=0`，实现“先部署不启用”，零业务风险。
- Redis 密码放 `.env`，并确保不提交到仓库。

## 5. 灰度迁移路线图（一步步改，不把旧接口搞挂）

### 阶段 0：仅部署 Redis（不启用）
目标：验证 Redis 容器、网络、密码、持久化都 OK。

步骤：
1) 在生产 compose 中加入 `redis` 服务，启动后确认健康检查为 healthy。
2) 应用容器保持 `REDIS_ENABLED=0`，不触发任何业务行为改变。

验收：
- Redis 容器健康。
- app 无感知，所有接口行为完全一致。

回滚：
- 直接移除/停掉 redis 服务即可，对业务无影响。

### 阶段 1：迁移“导入任务状态轮询”到 Redis（优先推荐）
目标：解决轮询状态丢失、服务重启丢任务、未来多进程查不到任务的问题。

建议实现策略（迁移期）：
- 写入：优先写 Redis，同时（可选）写一份内存（双写），便于快速回退。
- 读取：优先读 Redis；读不到时再回退读内存。
- Key：强制包含 `user_id`。
- TTL：24h。

验收场景：
1) 发起 `/Import_Doc/`，确认轮询能持续读到进度。
2) 导入过程中重启 app 容器，轮询仍能拿到状态。

回滚：
- `REDIS_TASK_STATUS_ENABLED=0`，恢复只读内存逻辑。

### 阶段 2：迁移 AI 会话上下文到 Redis（分功能逐个启用）
目标：多轮对话跨重启/跨进程稳定，不串号。

建议顺序：
1) 写作生成（同步 generator）
2) 润色优化（同步 generator）
3) 联网搜索（异步 + tool 调用链）

关键点：
- 必须把 `user_id` 纳入 Key；仅 `task_id` 不足以在多用户环境中从存储层彻底隔离。
- 必须设 TTL + 最大轮数（或最大 token 近似指标）。

验收场景：
- 同一用户同一 task_id 多次调用：上下文延续。
- 两个用户使用不同 task_id：互不影响。
- 服务重启后：上下文仍存在（直到 TTL 到期）。

回滚：
- `REDIS_CHAT_SESSION_ENABLED=0`，恢复内存会话。

### 阶段 3（可选）：缓存与限流
适用场景：
- 内网并发上升、轮询频繁、SSE 连接多，导致 CPU/IO 压力大。

建议做法：
- 缓存：对“读多写少”的查询接口设置短 TTL（10s~60s）。
- 限流：按 `user_id` 或 `ip` 限制并发 SSE 数、导入并发数、轮询频率。

## 6. 并发与扩容策略（Redis 为前置条件）

### 6.1 为什么 Redis 是扩容前置条件
你现在的会话/任务状态依赖进程内内存；一旦启用多 worker 或多实例，状态不共享会导致：
- 轮询查不到任务
- AI 上下文断裂

Redis 上线并迁移关键状态后，才能安全进行：
- uvicorn/gunicorn 多 worker
- 多实例水平扩容（多容器）

### 6.2 SSE 与代理/网关注意事项
项目 SSE 已设置 `X-Accel-Buffering: no` 等头（见 [ai_generate_api.py](file:///root/zzp/langextract-main/generate_report_test/routers/ai_generate_api.py#L25-L30)）。如果前面有 Nginx/网关，仍需确认：
- 关闭响应缓冲
- 适当增大读超时（避免长连接被中断）

## 7. 监控与告警（最低配也要有）

### 7.1 Redis 侧指标
- 内存占用、key 数量、过期 key 命中率
- AOF 重写耗时
- 慢查询（slowlog）

### 7.2 应用侧指标（建议打点）
- Redis 连接错误次数（按分钟）
- 任务状态读写延迟
- SSE 活跃连接数
- 导入任务排队长度/平均耗时

## 8. 安全与配置管理

### 8.1 密码与敏感配置
- Redis 密码放 `.env`，不要写死在 compose，不要提交到 git。
- 生产环境建议使用独立的 `prod.env`（由运维保管），并通过 compose `env_file` 引入。

### 8.2 Key 隔离与环境隔离
- `REDIS_PREFIX + ENV` 必须出现在 Key 中，避免 dev/prod 串数据。

## 12. 执行记录（Change Log）

### 2026-02-05：阶段 0 & 阶段 1 部分完成
- [x] **基础设施部署**：
  - 更新 `docker-compose.yml`，新增 Redis 7 服务（Alpine）。
  - 配置持久化（AOF + RDB），数据挂载至 `./redis_data`。
  - 配置 `app-dev` 链接 Redis 容器。
  - 创建单例 Redis 客户端 `utils/redis_client.py`（带连接池与重试）。
- [x] **开发环境容器化**：
  - 编写 `restart_service.sh`，支持一键启动 `app-dev` + `redis` 组合。
  - 自动挂载代码与配置，支持热重载。
- [x] **阶段 1：导入任务状态迁移**：
  - 重构 `import_doc_to_db_api.py`，引入 `TaskStatusManager` 类。
  - 实现 Redis/Memory 双模式切换（依赖环境变量）。
  - Key 格式规范化：`${prefix}:${env}:task:import:${user_id}:${task_id}`。
  - 状态写入/查询接口已对接 Manager。
- [x] **待执行**：
  - 在 `.env` 中开启 `REDIS_ENABLED=1` 和 `REDIS_TASK_STATUS_ENABLED=1` 进行端到端验证。（已完成）
  - 推进阶段 2（会话上下文迁移）：
    - [x] AI 写作会话 (`ai_generate_langchain.py`)：已实现 `ChatSessionManager` 并验证。
    - [x] AI 润色会话 (`ai_adjustment.py`)：已实现 `ChatSessionManager` 并验证。
    - [x] AI 搜索会话 (`ai_search.py`)：已实现 `ChatSessionManager` 并验证。

## 9. 上线验证清单（按阶段逐项打勾）

### 阶段 0（仅部署）
- Redis 容器 healthy
- 重启 Redis 容器后数据仍存在（AOF 生效）

### 阶段 1（任务状态）
- 导入任务轮询在高频轮询下稳定
- 重启 app 后轮询仍可查询进度
- 多用户互相查询对方 task_id 返回“任务不存在”

### 阶段 2（会话）
- 同用户同 task_id 多轮对话上下文连续
- 服务重启后上下文保留（TTL 内）
- 不同用户绝不共享上下文（Key 强制隔离）

### 阶段 3（缓存/限流，可选）
- 缓存命中率可观且不影响数据正确性
- 限流触发时返回码与前端提示可接受，不影响核心流程

## 10. 回滚策略（必须提前演练）
- 回滚 Redis（阶段 0）：停掉 redis 服务即可。
- 回滚任务状态迁移（阶段 1）：`REDIS_TASK_STATUS_ENABLED=0`，恢复内存。
- 回滚会话迁移（阶段 2）：`REDIS_CHAT_SESSION_ENABLED=0`，恢复内存。

建议：每次只开一个开关，观察 30~60 分钟再进入下一阶段。

## 11. 你最担心的问题的“明确结论”
- 会不会影响 AI 上下文会话？
  - 按本计划迁移后，会话从“只在单进程有效”变成“跨重启/跨进程稳定”，前提是 Key 必须包含 `user_id` + `task_id` 并设置 TTL。
- 前端轮询稳定性？
  - 任务状态迁到 Redis 后，轮询命中任何实例都可查到同一状态，显著提升稳定性。
- 多用户会不会串号？
  - 只要存储层 Key 强制带 `user_id` 且接口层继续用 JWT 鉴权，多用户串号风险会明显降低；反而当前“仅 task_id + 内存字典”的方式更依赖前端不出错。
- 服务器一个进程处理不过来？
  - Redis 不直接提升推理吞吐，但它是多 worker/多实例扩容的前置条件；先稳定状态，再扩容处理能力。

