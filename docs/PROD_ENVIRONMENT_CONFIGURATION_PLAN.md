# 生产环境配置整改计划

> **文档状态**：已执行  
> **执行日期**：2026-03-09  
> **执行人**：Trae AI Assistant  
> **关联文件**：`/root/zzp/langextract-main/ljt/note-prompt/.env`

## 问题概述

当前生产环境存在前端容器请求后端测试环境的问题。具体表现为：前端生产环境配置的 API 地址指向了后端开发/测试环境的端口，而非生产环境端口。

## 执行记录

### 已完成的修改

**修改时间**：2026-03-09  
**修改文件**：`/root/zzp/langextract-main/ljt/note-prompt/.env`

**修改内容**：
```bash
# 修改前（错误配置）
PYTHON_API_URL=http://192.168.3.10:34521  # 指向 Python 测试环境
JAVA_API_URL=http://192.168.3.10:18081    # 指向 Java 测试环境

# 修改后（正确配置）
PYTHON_API_URL=http://192.168.3.10:12543  # 指向 Python 生产环境
JAVA_API_URL=http://192.168.3.10:12544    # 指向 Java 生产环境
```

**修改说明**：在配置文件中添加了修改注释，标注了原配置和新配置的对应关系，方便后续溯源。

---

**修改时间**：2026-03-09  
**修改文件**：`/root/zzp/langextract-main/ljt/prompt-system-backend/prod_service.sh`

**修改原因**：原脚本依赖手动执行 `mvn clean package` 生成 JAR 包，且不支持代码更新检测。

**修改内容**：
1. **自动构建**：在 `find_jar()` 函数中增加自动构建逻辑，找不到 JAR 时自动执行 `mvn clean package -DskipTests`
2. **Maven Wrapper 支持**：优先使用项目自带的 `mvnw`，无需系统安装 Maven
3. **代码更新检测**：自动检测 `src/` 目录下的 `.java` 文件是否比 JAR 更新，如果是则自动重新构建
4. **日志输出修复**：将所有提示消息输出到 stderr，避免混入 JAR 路径

**使用方式**：
```bash
cd /root/zzp/langextract-main/ljt/prompt-system-backend
./prod_service.sh start
```

脚本会自动：
- 首次运行：检测无 JAR → 自动构建 → 启动服务
- 代码更新后：检测到更新 → 重新构建 → 重启服务
- 无改动时：直接启动（跳过构建）

### 待执行步骤

- [ ] 重启前端生产容器使配置生效
- [ ] 验证配置是否正确加载
- [ ] 测试 API 连通性

---

## 问题背景

## 影响范围

此问题影响以下两个后端服务：
1. **Python 后端服务** (generate_report_test)
2. **Java 后端服务** (prompt-system-backend)

---

## 环境架构说明

### 1. Python 后端服务

#### 文件位置
- 开发/测试启动脚本：`/root/zzp/langextract-main/generate_report_test/restart_service.sh`
- 生产启动脚本：`/root/zzp/langextract-main/generate_report_test/start-prod.sh`
- Docker Compose 配置：`/root/zzp/langextract-main/generate_report_test/docker-compose.yml`
- 生产 Docker Compose 配置：`/root/zzp/langextract-main/generate_report_test/docker-compose.prod.yml`

#### 端口映射
| 环境 | 宿主机端口 | 容器内部端口 | 说明 |
|------|-----------|-------------|------|
| 开发/测试 | 34521 | 34521 | 用于开发调试 |
| 生产 | 12543 | 34521 | 对外提供生产服务 |

#### 问题点
前端 `.env` 文件当前配置：
```bash
PYTHON_API_URL=http://192.168.3.10:34521  # 指向测试环境
```
应修改为：
```bash
PYTHON_API_URL=http://192.168.3.10:12543  # 指向生产环境
```

---

### 2. Java 后端服务

#### 文件位置
- 开发/测试启动脚本：`/root/zzp/langextract-main/ljt/prompt-system-backend/restart_service.sh`
- 生产启动脚本：`/root/zzp/langextract-main/ljt/prompt-system-backend/prod_service.sh`
- 开发环境配置：`/root/zzp/langextract-main/ljt/prompt-system-backend/.env`
- 生产环境配置：`/root/zzp/langextract-main/ljt/prompt-system-backend/prod.env`
- Docker Compose 配置：`/root/zzp/langextract-main/ljt/prompt-system-backend/docker-compose.java.yml`

#### 端口映射
| 环境 | 端口 | 配置文件 | 说明 |
|------|------|---------|------|
| 开发/测试 | 18081 | `.env` | 用于开发调试 |
| 生产 | 12544 | `prod.env` | 对外提供生产服务 |

#### 问题点
前端 `.env` 文件当前配置：
```bash
JAVA_API_URL=http://192.168.3.10:18081  # 指向测试环境
```
应修改为：
```bash
JAVA_API_URL=http://192.168.3.10:12544  # 指向生产环境
```

---

### 3. 前端服务

#### 文件位置
- 前端项目目录：`/root/zzp/langextract-main/ljt/note-prompt/`
- 开发启动脚本：`/root/zzp/langextract-main/ljt/note-prompt/start-dev.sh`
- 生产启动脚本：`/root/zzp/langextract-main/ljt/note-prompt/start-prod.sh`
- 部署脚本：`/root/zzp/langextract-main/ljt/note-prompt/deploy.sh`
- 环境配置文件：`/root/zzp/langextract-main/ljt/note-prompt/.env`
- 开发 Docker Compose：`/root/zzp/langextract-main/ljt/note-prompt/docker-compose.dev.yml`
- 生产 Docker Compose：`/root/zzp/langextract-main/ljt/note-prompt/docker-compose.prod.yml`
- Nginx 配置模板：`/root/zzp/langextract-main/ljt/note-prompt/docker/nginx/default.conf.template`

#### 前端代理机制
前端通过 Nginx 反向代理将请求转发到后端服务：
- `/api/python/` → Python 后端
- `/api/java/` → Java 后端

Nginx 使用环境变量 `PYTHON_API_URL` 和 `JAVA_API_URL` 来确定后端地址。

---

## 整改步骤

### 第一步：修改前端环境配置

**文件**：`/root/zzp/langextract-main/ljt/note-prompt/.env`

**修改内容**：
```bash
# 修改前
PYTHON_API_URL=http://192.168.3.10:34521
JAVA_API_URL=http://192.168.3.10:18081

# 修改后
PYTHON_API_URL=http://192.168.3.10:12543
JAVA_API_URL=http://192.168.3.10:12544
```

### 第二步：重启前端生产容器

执行以下命令重启前端生产环境：
```bash
cd /root/zzp/langextract-main/ljt/note-prompt
./start-prod.sh
```

或执行完整部署流程：
```bash
cd /root/zzp/langextract-main/ljt/note-prompt
./deploy.sh
```

### 第三步：验证配置生效

1. 检查前端容器环境变量：
```bash
docker exec note-prompt-prod env | grep API_URL
```

2. 检查 Nginx 配置是否正确加载：
```bash
docker exec note-prompt-prod cat /etc/nginx/conf.d/default.conf | grep -A2 "proxy_pass"
```

3. 测试 API 连通性：
```bash
# 测试 Python 后端
curl http://192.168.3.10:12543/api/health

# 测试 Java 后端
curl http://192.168.3.10:12544/api/health
```

---

## 配置对照表

### 后端服务端口对照

| 服务 | 开发/测试端口 | 生产端口 | 开发配置文件 | 生产配置文件 |
|------|--------------|---------|-------------|-------------|
| Python | 34521 | 12543 | `generate_report_test/docker-compose.yml` | `generate_report_test/docker-compose.prod.yml` |
| Java | 18081 | 12544 | `ljt/prompt-system-backend/.env` | `ljt/prompt-system-backend/prod.env` |

### 前端 API 地址配置对照

| 环境变量 | 修改前值（错误） | 修改后值（正确） | 状态 |
|---------|-----------------|-----------------|------|
| PYTHON_API_URL | http://192.168.3.10:34521 | http://192.168.3.10:12543 | ✅ 已修改 |
| JAVA_API_URL | http://192.168.3.10:18081 | http://192.168.3.10:12544 | ✅ 已修改 |

**配置文件路径**：`/root/zzp/langextract-main/ljt/note-prompt/.env`

---

## 注意事项

1. **修改时机**：建议在后端生产服务已启动并正常运行后再修改前端配置并重启。

2. **回滚准备**：修改前备份当前 `.env` 文件，以便出现问题时快速回滚。

3. **验证顺序**：
   - 先确认后端生产服务正常运行
   - 再修改前端配置
   - 最后重启前端容器

4. **网络连通性**：确保前端容器能够访问 `192.168.3.10` 的 `12543` 和 `12544` 端口。

---

## 相关文件清单

### Python 后端相关
- `/root/zzp/langextract-main/generate_report_test/restart_service.sh` - 开发环境启动脚本
- `/root/zzp/langextract-main/generate_report_test/start-prod.sh` - 生产环境启动脚本
- `/root/zzp/langextract-main/generate_report_test/docker-compose.yml` - Docker Compose 配置
- `/root/zzp/langextract-main/generate_report_test/docker-compose.prod.yml` - 生产 Docker Compose 配置

### Java 后端相关
- `/root/zzp/langextract-main/ljt/prompt-system-backend/restart_service.sh` - 开发环境启动脚本
- `/root/zzp/langextract-main/ljt/prompt-system-backend/prod_service.sh` - 生产环境启动脚本
- `/root/zzp/langextract-main/ljt/prompt-system-backend/.env` - 开发环境配置
- `/root/zzp/langextract-main/ljt/prompt-system-backend/prod.env` - 生产环境配置
- `/root/zzp/langextract-main/ljt/prompt-system-backend/docker-compose.java.yml` - Docker Compose 配置

### 前端相关
- `/root/zzp/langextract-main/ljt/note-prompt/.env` - **已修改的配置文件**（2026-03-09 更新 API 地址指向生产环境）
- `/root/zzp/langextract-main/ljt/note-prompt/start-dev.sh` - 开发环境启动脚本
- `/root/zzp/langextract-main/ljt/note-prompt/start-prod.sh` - 生产环境启动脚本
- `/root/zzp/langextract-main/ljt/note-prompt/deploy.sh` - 部署脚本
- `/root/zzp/langextract-main/ljt/note-prompt/docker-compose.dev.yml` - 开发 Docker Compose
- `/root/zzp/langextract-main/ljt/note-prompt/docker-compose.prod.yml` - 生产 Docker Compose
- `/root/zzp/langextract-main/ljt/note-prompt/docker/nginx/default.conf.template` - Nginx 配置模板
