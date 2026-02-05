# Java 后端运维与环境部署规划文档

## 1. 核心目标与原则

本规划旨在为“提示词管理系统（Java后端）”建立一套与现有 Python 主系统完全对齐的运维体系。遵循以下核心原则：

1.  **复用现有基础设施**：沿用 Python 项目的数据库、网络策略和目录结构规范。
2.  **环境严格隔离**：
    *   **开发环境 (Dev)**：采用“脚本化本地启动”模式（类比 `restart_service.sh`），便于调试与热更。
    *   **生产环境 (Prod)**：采用“Docker 容器化”模式（类比 `DOCKER_DEPLOY_PLAN.md`），确保稳定性与环境一致性。
3.  **配置与代码分离**：通过环境变量（Environment Variables）控制不同环境的数据库连接、端口和日志行为。

---

## 2. 环境划分与拓扑

### 2.1 端口规划

为了避免端口冲突并保持规范，建议如下分配：

| 服务/环境 | 内部端口 (Container/App) | 宿主机端口 (Host) | 说明 |
| :--- | :--- | :--- | :--- |
| **Python 主系统** | 34521 | **12543** (Prod) / 34521 (Dev) | 现有服务 |
| **Java 提示词系统** | 8080 | **12544** (Prod) / 8080 (Dev) | **新增服务**，开发环境端口可自定义 |

### 2.2 目录挂载规范 (生产环境)

Java 后端同样遵循“数据落盘”原则，容器销毁不丢数据。建议在宿主机 `/root/zzp/langextract-main/prompt_system_backend` 下建立以下目录映射：

*   `/logs` -> 挂载容器内的 `/app/logs` (统一日志归档)
*   `/config` -> 挂载容器内的 `/app/config` (可选，用于放置临时覆盖配置)

---

## 3. 开发环境最佳实践 (Dev)

虽然 Java 开发通常使用 IDE，但为了统一运维习惯，我们将提供一个 Shell 脚本封装，复刻 Python 的 `restart_service.sh` 体验。

### 3.1 启动方式
在项目根目录提供 `restart_service.sh` (Java版)：

**核心逻辑：**
1.  检查 JDK 环境 (JDK 17+)。
2.  加载本地 `.env` 或默认配置。
3.  使用 Maven Wrapper 启动 (推荐) 或 `java -jar` 启动。
4.  自动 tail 日志。

**脚本行为参考：**
```bash
# 伪代码示例
export SPRING_PROFILES_ACTIVE=dev
export SERVER_PORT=8080
mvnw spring-boot:run
```

### 3.2 配置文件 (`application-dev.yml`)
*   **数据库**：连接 `192.168.3.10` 的 `generating_reports_test` (测试库)。
*   **日志**：输出到控制台 + 本地 `logs/` 目录。
*   **热重载**：建议配置 `spring-boot-devtools` 实现代码修改后的自动重启。

---

## 4. 生产环境最佳实践 (Prod - Docker)

生产环境完全复用 Python 项目的 Docker 治理思路，使用 Docker Compose 进行编排。

### 4.1 Dockerfile 设计 (多阶段构建)
为了减小镜像体积并规范构建流程，采用 Multi-stage Build：

1.  **Build Stage** (Maven Image): 负责编译代码，生成 JAR 包。
2.  **Run Stage** (OpenJDK Slim Image): 仅包含 JRE，复制 JAR 包运行。

### 4.2 Docker Compose 配置
建议在现有的 `docker-compose.prod.yml` 中新增服务，或新建 `docker-compose-java.yml`。

**配置要点：**
```yaml
services:
  prompt-backend:
    image: prompt-system-backend:${TAG:-latest}
    ports:
      - "12544:8080" # 宿主机 12544 映射容器 8080
    volumes:
      - ./logs:/app/logs # 日志持久化
      - /etc/localtime:/etc/localtime:ro # 时区同步
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - DB_HOST=192.168.3.10
      - DB_NAME=generating_reports # 生产库
      - JWT_SECRET=${JWT_SECRET} # 复用 Python 端的 Secret
    restart: always
```

### 4.3 部署脚本 (`deploy.sh`)
复刻 Python 项目的 `deploy.sh` 逻辑：
1.  **Git Check**：检查未提交代码。
2.  **Build**：本地构建 Docker 镜像 (`docker build -t ...`)。
3.  **Tag & Push**：打 Git Tag 并推送。
4.  **Restart**：执行 `docker-compose up -d` 重启服务。

---

## 5. 统一配置清单 (Java 后端需适配)

为了确保 Java 后端能无缝融入现有体系，**必须**在代码中实现对以下环境变量的支持：

| 环境变量名 | 默认值 (Dev) | 生产值 (Prod) | 作用 |
| :--- | :--- | :--- | :--- |
| `SPRING_PROFILES_ACTIVE` | `dev` | `prod` | 激活 Spring Boot 对应配置 |
| `SERVER_PORT` | `8080` | `8080` (容器内) | 服务端口 |
| `DB_HOST` | `192.168.3.10` | `192.168.3.10` | 数据库主机 |
| `DB_NAME` | `generating_reports_test` | `generating_reports` | **关键：自动切换库名** |
| `DB_USER` | `root` | `root` | 数据库用户 |
| `DB_PASSWORD` | `xinan@2024` | `xinan@2024` | 数据库密码 |
| `JWT_SECRET` | (硬编码测试值) | (通过 Env 注入) | 鉴权密钥 |

---

## 6. 实施步骤

1.  **初始化项目**：生成 Spring Boot 项目结构。
2.  **编写 `Dockerfile`**：确保可以构建出最小化运行镜像。
3.  **编写 `restart_service.sh`**：实现开发环境一键启动。
4.  **编写 `docker-compose.yml`**：定义生产环境运行参数。
5.  **验证互通**：
    *   Java 后端启动后，使用 Postman 携带 Python 后端生成的 Token 访问，验证 JWT 解析通过。
    *   验证 Java 后端写入的数据（如 Prompt），Python 后端能读取（共库验证）。

此文档旨在指导 Java 开发人员复刻现有的高效运维模式，确保新旧系统在运维层面的一致性和低维护成本。
