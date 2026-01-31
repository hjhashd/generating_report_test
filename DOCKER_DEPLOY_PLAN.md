# Docker 环境分离与部署方案汇总

## 1. 方案核心目标
本方案旨在解决以下核心痛点，实现现代化、标准化的运维流程：
1.  **环境彻底分离**：开发环境（热更、调试）与生产环境（稳定、隔离）使用同一套 Docker 配置基座，但通过覆盖文件区分行为。
2.  **代码库统一**：生产环境不再需要维护独立的 git 分支或物理目录，直接通过 Docker 镜像版本管理代码。
3.  **零风险回退**：生产环境基于“镜像标签（Tag）”部署。若新版本出现问题，修改配置指回旧版本 Tag 即可秒级回滚，无需代码层面的 revert 操作。
4.  **数据安全持久化**：生产环境虽然运行在容器内，但所有关键数据（报告、图片、合并结果）均直接挂载到宿主机的物理目录，确保容器销毁数据不丢。

---

## 2. 架构设计与文件清单

### 2.1 配置文件结构
| 文件名 | 作用域 | 核心职责 |
| :--- | :--- | :--- |
| `Dockerfile` | 通用 | 定义 Python 3.9 基础环境，安装依赖，构建应用镜像。 |
| `docker-compose.yml` | 通用 | 定义服务基础名称、网络、以及与环境无关的通用配置。 |
| `docker-compose.dev.yml` | **开发** | **挂载代码目录**（实现热重载）；映射端口 `34521`；开启调试模式。 |
| `docker-compose.prod.yml` | **生产** | **不挂载代码**（锁定镜像版本）；映射端口 `12543`；**挂载宿主机真实数据目录**；配置自动重启。 |
| `.env` | 配置 | 控制当前运行的镜像版本（TAG），实现版本切换。 |
| `server_config.py` | 代码 | 已改造为优先读取环境变量 `PORT`，适配容器化部署。 |

### 2.2 数据流向示意
```mermaid
graph TD
    User[用户请求] -->|端口 12543| Docker[Docker 容器 (生产环境)]
    Docker -->|读取代码| Image[镜像 (v1.0/v2.0)]
    Docker -->|读写数据| HostData[宿主机数据目录]
    
    subgraph 宿主机数据目录 [/root/zzp/langextract-main/generate_report]
        Report[report/]
        Inferrence[inferrence/]
        Merge[report_merge/]
        Images[editor_image/]
    end
```

---

## 3. 实现细节与优势

### 3.1 生产环境配置 (`docker-compose.prod.yml`)
我们特别定制了生产环境配置，以满足“内网环境”、“数据分离”和“双数据库”的需求：

```yaml
services:
  app:
    # 1. 端口隔离：容器内固定 34521，对外暴露 12543
    ports:
      - "12543:34521"
    
    # 2. 数据持久化：直接挂载你现有的生产环境数据目录
    volumes:
      - /root/zzp/langextract-main/generate_report/report:/app/report
      - /root/zzp/langextract-main/generate_report/inferrence:/app/inferrence
      # ... 其他目录同理
    
    # 3. 环境变量注入：直接在配置中管理敏感信息
    environment:
      - ENV=production
      - TZ=Asia/Shanghai
      
      # === 双数据库配置 ===
      # 报告系统库 (自动切换到生产库 generating_reports)
      - REPORT_DB_HOST=192.168.3.10
      - REPORT_DB_NAME=generating_reports
      
      # 提示词系统库 (Agent DB)
      - AGENT_DB_HOST=192.168.3.13
      - AGENT_DB_NAME=agent_report
    
    # 4. 自动保活
    restart: always
```

### 3.2 数据库兼容性设计
为了支持过渡期架构，我们重构了 `utils/sql_config.py`，实现了**双模运行**：
*   **本地开发/测试**：代码检测不到环境变量，自动使用默认值（连接测试库 `generating_reports_test`），**无需任何额外配置**。
*   **Docker 生产**：容器启动时注入 `REPORT_DB_NAME=generating_reports` 等变量，代码优先读取，自动连接生产库。

### 3.3 版本控制与回退机制
这是本方案最大的亮点。你不再依赖“回退代码文件”来恢复服务。

*   **发布新版**：
    1.  `docker build -t langextract-app:v2.0 .`
    2.  修改 `.env` -> `TAG=v2.0`
    3.  运行 `./prod_start.sh`
*   **紧急回退**：
    1.  修改 `.env` -> `TAG=v1.0`
    2.  运行 `./prod_start.sh` (**瞬间恢复到上一个稳定状态**)

---

## 4. 操作指南 (快捷脚本)

为简化操作，已为您准备了 4 个快捷脚本（已赋予执行权限）：

### 开发环境 (Development)
代码修改立即生效，支持热重载。
*   **启动**: `./dev_start.sh` (运行在 34521 端口)
*   **停止**: `./dev_stop.sh`

### 生产环境 (Production)
代码锁定在镜像中，数据持久化在宿主机。
*   **启动**: `./prod_start.sh` (运行在 12543 端口，支持自动重启)
*   **停止**: `./prod_stop.sh`

### 手动发布流程
1.  **构建镜像**: `docker build -t langextract-app:v1.0 .`
2.  **切换版本**: 修改 `.env` 文件，设置 `TAG=v1.0`
3.  **应用更新**: `./prod_start.sh`

---

## 5. 总结
这个方案完美契合了你的需求：
*   ✅ **同一套代码库**：无需维护两个文件夹。
*   ✅ **环境分离**：开发用配置 A，生产用配置 B。
*   ✅ **数据安全**：生产数据直接写在宿主机物理盘，不进容器。
*   ✅ **无忧回退**：基于镜像标签的版本管理，运维从此不再提心吊胆。
