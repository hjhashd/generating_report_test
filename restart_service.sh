#!/bin/bash

# 1. 强制检查 root 身份
if [ "$EUID" -ne 0 ]; then
  echo "❌ 错误: 必须以 root 身份运行此脚本。"
  echo "请尝试使用: sudo $0"
  exit 1
fi

echo "🚀 正在启动 Docker 开发环境..."

# 2. 定义变量
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 设置服务端口环境变量，优先使用已有环境变量，默认 34521
export PORT=${PORT:-34521}
export ENV="development"

# 3. 切换到项目目录
echo "📂 进入项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR" || { echo "❌ 无法进入目录 $PROJECT_DIR"; exit 1; }

# 确保日志目录存在 (用于挂载或查看)
mkdir -p logs
# 启动前清空旧日志，确保日志文件干净
> logs/test_report.log
echo "🧹 已清空旧日志文件: logs/test_report.log"
mkdir -p redis_data

# 4. 停止占用端口的旧服务 (宿主机进程)
echo "🛑 检查端口 $PORT 占用情况..."
# 使用 lsof 或 netstat 获取 PID，处理可能的多个 PID 并过滤非数字
PIDS=$(lsof -t -i :$PORT 2>/dev/null || netstat -tunlp | grep ":$PORT " | awk '{print $7}' | cut -d'/' -f1 | grep -E '^[0-9]+$')

if [ -n "$PIDS" ]; then
    echo "⚠️ 发现宿主机进程 $PIDS 占用端口 $PORT，正在停止以释放端口给容器..."
    # 转换为单行并逐个 kill，避免参数解析错误
    for pid in $PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid"
            echo "✅ 已停止进程 $pid"
        fi
    done
    echo "✅ 所有相关宿主机进程已处理"
else
    echo "✅ 端口 $PORT 未被宿主机进程占用"
fi

# 5. Docker Compose 操作
if ! command -v docker &> /dev/null; then
    echo "❌ 未找到 docker 命令，请先安装 Docker。"
    exit 1
fi

echo "🐳 正在停止旧容器..."
docker compose --profile dev down --remove-orphans

echo "🐳 正在构建并启动开发容器 (app-dev, redis)..."
# 使用 --profile dev 启动开发环境服务
# --build 确保镜像包含最新代码依赖 (虽然 dev 挂载了代码，但依赖可能变动)
if docker compose --profile dev up -d --build; then
    echo "✅ 容器启动命令执行成功"
else
    echo "❌ 容器启动失败"
    exit 1
fi

# 6. 检查启动结果
echo "⏳ 等待服务初始化..."

# 循环检查端口，最多等待 30 秒
for i in {1..30}; do
    # 检查 Docker 容器状态
    CONTAINER_STATE=$(docker inspect -f '{{.State.Status}}' langextract-app-dev 2>/dev/null)
    
    if [ "$CONTAINER_STATE" == "running" ]; then
        # 容器运行中，检查端口是否已在宿主机监听
        if netstat -tunlp | grep ":$PORT " > /dev/null; then
            echo ""
            echo "✅ 开发环境服务启动成功！"
            echo "📊 Redis 数据目录: $PROJECT_DIR/redis_data"
            echo "👉 API 地址: http://localhost:$PORT"
            echo ""
            echo "🔍 查看实时日志 (直接复制下面命令):"
            echo "docker logs -f langextract-app-dev"
            echo ""
            exit 0
        fi
    elif [ "$CONTAINER_STATE" == "exited" ] || [ "$CONTAINER_STATE" == "dead" ]; then
        echo ""
        echo "❌ 容器启动后意外退出，请检查日志:"
        docker logs langextract-app-dev
        exit 1
    fi
    
    echo -n "."
    sleep 1
done

echo ""
echo "⚠️ 服务启动超时，但容器仍在运行中。请手动检查日志。"
echo ""
echo "� 查看实时日志 (直接复制下面命令):"
echo "docker logs -f langextract-app-dev"
echo ""
