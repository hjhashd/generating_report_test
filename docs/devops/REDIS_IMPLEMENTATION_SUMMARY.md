# Redis 实施情况与维护指南

本文档详细总结了项目引入 Redis 后的架构变化、实现细节以及维护指南。

## 1. 核心架构变更

为了解决状态丢失、支持多实例扩容，我们从“纯内存状态管理”迁移到了“Redis + 内存双模管理”。

### 1.1 拓扑结构
*   **App 容器** (`app-dev`/`app-prod`)：运行 FastAPI 后端。
*   **Redis 容器** (`langextract-redis`)：运行 Redis 7.2 (Alpine)，仅在 Docker 网络内部暴露端口，不对宿主机开放。
*   **通信**：App 通过 Docker 网络别名 `redis` 连接到 Redis 服务。

### 1.2 数据持久化
*   **挂载路径**：`./redis_data:/data`
*   **持久化策略**：AOF (Append Only File) + RDB 混合模式，确保容器重启后数据不丢失。

---

## 2. 核心实现机制

我们采用了一种**“渐进式 + 可降级”**的实现模式，确保在 Redis 故障或未启用时，系统能自动回退到内存模式运行。

### 2.1 统一客户端 (`utils/redis_client.py`)
*   **单例模式**：使用连接池 (`ConnectionPool`) 管理连接，避免频繁创建销毁。
*   **健康检查**：初始化时自动 Ping，若失败则返回 `None`，触发上层业务降级。
*   **环境变量控制**：严格遵循 `REDIS_ENABLED` 开关。

### 2.2 任务状态管理 (`TaskStatusManager`)
*   **文件位置**：`routers/import_doc_to_db_api.py`
*   **用途**：管理文档导入进度的轮询状态。
*   **Key 格式**：`${REDIS_PREFIX}:${ENV}:task:import:${user_id}:${task_id}`
    *   示例：`langextract:dev:task:import:1001:uuid-1234`
*   **数据结构**：Hash (便于更新单个字段如 `progress` 或 `step`)。
*   **逻辑**：
    1.  检查 `REDIS_TASK_STATUS_ENABLED` 开关。
    2.  若开启且 Redis 可用，优先读写 Redis。
    3.  若 Redis 写失败，打错误日志（暂不回退写内存，避免数据不一致）。
    4.  若 Redis 读失败或未开启，读写内存字典 `memory_store`。

### 2.3 会话上下文管理 (`ChatSessionManager`)
*   **文件位置**：`utils/chat_session_manager.py`
*   **用途**：管理 AI 写作、润色、搜索的多轮对话历史。
*   **Key 格式**：`${REDIS_PREFIX}:${ENV}:${session_type}:${task_id}`
    *   写作示例：`langextract:dev:chat:generate:uuid-5678`
    *   润色示例：`langextract:dev:chat:optimize:uuid-9012`
    *   搜索示例：`langextract:dev:chat:search:uuid-3456`
*   **数据结构**：String (JSON 序列化的 LangChain Message List)。
    *   使用 `messages_to_dict` 和 `messages_from_dict` 进行序列化。
*   **覆盖范围**：
    *   AI 写作：`utils/zzp/ai_generate_langchain.py`
    *   AI 润色：`utils/zzp/ai_adjustment.py`
    *   AI 搜索：`utils/lyf/ai_search.py`

---

## 3. 配置与环境变量

所有配置均通过 `.env` 文件注入，支持热切换。

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `REDIS_ENABLED` | `0` | **总开关**。设为 `1` 才会尝试连接 Redis。 |
| `REDIS_TASK_STATUS_ENABLED` | `0` | **子开关**。是否将导入任务状态存入 Redis。 |
| `REDIS_CHAT_SESSION_ENABLED` | `0` | **子开关**。是否将 AI 会话存入 Redis。 |
| `REDIS_HOST` | `redis` | Docker 服务名，开发环境通常为 `redis` 或 `localhost`。 |
| `REDIS_PORT` | `6379` | 端口。 |
| `REDIS_PASSWORD` | - | 必填，生产环境必须设置强密码。 |
| `REDIS_PREFIX` | `langextract` | Key 前缀，防止 Key 冲突。 |
| `ENV` | `dev` | 环境标识 (`dev`/`prod`)，用于隔离 Key。 |

---

## 4. 维护与排查指南

### 4.1 常用检查命令

**进入 Redis 容器查看数据：**
```bash
# 1. 进入容器
docker exec -it langextract-redis sh

# 2. 连接 CLI
redis-cli -a <你的密码>

# 3. 常用操作
PING                   # 检查存活
KEYS langextract:*     # 查看所有相关 Key
TTL <key>              # 查看过期时间
HGETALL <key>          # 查看 Hash 数据（任务状态）
GET <key>              # 查看 String 数据（会话历史）
FLUSHDB                # 清空当前库（慎用！）
```

### 4.2 常见问题排查

**Q1: 服务日志报错 "Redis connection ping failed"**
*   **原因**：Redis 容器未启动，或密码配置不匹配。
*   **解决**：检查 `docker ps` 确认容器状态；检查 `.env` 中的 `REDIS_PASSWORD` 是否与 `docker-compose.yml` 一致。

**Q2: 更新代码后，之前的会话找不到了**
*   **原因**：可能是 `REDIS_PREFIX` 或 `ENV` 环境变量变了，导致生成了新的 Key。
*   **解决**：检查环境变量配置；或者确认是否刚从内存模式切换到了 Redis 模式（内存数据不会自动迁移到 Redis）。

**Q3: 想要临时关闭 Redis**
*   **操作**：修改 `.env` 设置 `REDIS_ENABLED=0`，然后重启服务 (`./restart_service.sh`)。系统将无缝切换回内存模式（注意：切换瞬间会丢失旧的 Redis 数据访问）。

### 4.3 未来扩展建议
1.  **消息队列**：当前架构已为引入 Celery/ARQ 做好准备，只需复用 `utils/redis_client.py` 即可。
2.  **缓存层**：可利用 `redis_client` 为高频读接口（如模板列表）添加缓存装饰器。
