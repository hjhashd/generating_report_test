#!/bin/bash
# 启动开发环境，支持代码实时挂载

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

echo "🚀 Starting Development Environment..."

# 停止生产容器（如果存在），避免资源竞争
docker-compose --profile prod stop

# 启动开发容器
# --build 确保每次启动都尝试构建（利用缓存）
# -d 后台运行
docker-compose --profile dev up -d --build

echo "✅ Development environment started!"
echo "👉 App URL: http://localhost:34521"
echo "📝 Tailing logs (Ctrl+C to exit logs, container will keep running)..."
docker-compose --profile dev logs -f
