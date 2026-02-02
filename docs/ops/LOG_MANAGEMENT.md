# 日志管理规范 (Log Management)

本文档记录了 `generate_report_test` 项目的日志分布及其查看方式，以便 AI 助手和开发者快速定位问题。

## 1. 环境日志分布

项目目前区分了 **生产环境 (Production)** 和 **测试环境 (Test/Dev)**，日志文件已完全分离：

| 环境 | 启动方式 | 日志文件路径 | 说明 |
| :--- | :--- | :--- | :--- |
| **生产环境** | `./deploy.sh` (Docker) | `logs/prod_report.log` | 容器内部 `/app/report.log` 的映射 |
| **测试环境** | `./restart_service.sh` | `test_report.log` | 宿主机进程直接输出 |

## 2. 常用操作命令

### 2.1 生产环境日志
*   **查看文件**: `tail -f logs/prod_report.log`
*   **Docker 实时日志**: `docker-compose --profile prod logs -f app-prod`

### 2.2 测试环境日志
*   **查看文件**: `tail -f logs/test_report.log`

## 3. 注意事项
*   **用户权限**: 运行 `./deploy.sh` 必须使用 `cqj` 用户，否则会因为 SSH 密钥权限问题导致 Git 推送失败。
*   **日志冲突**: 不要手动修改 `docker-compose.yml` 中的日志挂载路径，以免破坏日志分离机制。
*   **历史日志**: 原有的根目录 `report.log` 已废弃，不再接收新日志。
