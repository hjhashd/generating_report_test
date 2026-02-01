# Deployment Workflow Guide

本文档介绍了基于 Docker + Git Tag 的轻量级 CI/CD 工作流，适用于本项目的开发与生产环境部署。

## 📁 核心文件说明

| 文件名 | 说明 |
|--------|------|
| `docker-compose.yml` | 统一的 Docker 编排文件，使用 `profiles` 区分 dev/prod 环境。 |
| `start-dev.sh` | **开发环境启动脚本**。挂载本地代码，支持热重载。 |
| `start-prod.sh` | **生产环境启动脚本**。构建并锁定镜像，挂载生产数据卷。 |
| `deploy.sh` | **一键部署脚本**。自动 Commit、打 Tag、Push、重启生产环境。 |
| `rollback.sh` | **一键回滚脚本**。选择历史 Tag 并回滚生产环境。 |

## 🚀 常用操作

### 1. 启动开发环境
在本地开发时使用。代码修改会实时生效。

```bash
./start-dev.sh
```
*   访问地址: `http://localhost:34521`
*   日志: 脚本会自动 tail 日志，按 `Ctrl+C` 退出日志查看（容器会在后台继续运行）。

### 2. 部署到生产环境
当你完成开发并准备发布时使用。

```bash
./deploy.sh
```
**脚本流程：**
1.  **检查代码**: 如果有未提交的更改，会提示输入 Commit Message 并自动提交。
2.  **创建备份**: 自动创建一个时间戳标签 (例如 `backup-20231027-103000`)。
3.  **推送远程**: 将代码和标签推送到远程仓库 (origin)。
4.  **发布上线**: 重新构建镜像并重启生产容器。

### 3. 回滚版本
如果生产环境出现问题，可以使用此脚本快速回滚到之前的版本。

```bash
./rollback.sh
```
**脚本流程：**
1.  列出最近 10 个备份标签 (`backup-*`)。
2.  输入序号选择要回滚的版本。
3.  脚本会自动 `git checkout` 到该标签。
4.  自动重启生产环境。

**注意**: 回滚后 Git 会处于 `detached HEAD` 状态。若要恢复开发，请执行 `git checkout main`。

### 4. 仅启动生产环境 (不部署)
如果你只想重启生产容器而不产生新的部署记录：

```bash
./start-prod.sh
```

### 5. 常见问题 (FAQ)

#### Q: 报错 `Permission denied (publickey)`？
**A**: 请确保你使用的 Linux 用户身份正确。本项目建议使用 `cqj` 用户进行操作，该用户已配置 GitHub SSH Key。如果是 `root` 用户，可能由于未配置 Key 导致推送失败。

#### Q: 报错 `port is already allocated`？
**A**: 这通常是因为旧的容器没有被正确清理。脚本已配置 `--remove-orphans` 来尝试解决此问题。如果仍然报错，可以手动运行 `docker ps` 查找占用 `12543` 端口的容器并停止它。

## ⚙️ 配置详情
我们在 `docker-compose.yml` 中使用了 Profiles：
*   `dev`: 对应服务 `app-dev`。挂载 `.:/app`，开启 `reload`。
*   `prod`: 对应服务 `app-prod`。挂载数据卷，使用生产数据库配置。

### 数据卷 (Production)
生产环境容器挂载了以下宿主机目录以持久化数据：
*   `.../report`
*   `.../inferrence`
*   `.../report_merge`
*   `.../editor_image`

代码目录**未挂载**到生产容器中，以确保运行的是镜像构建时的稳定代码版本。
