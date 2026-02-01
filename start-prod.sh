#!/bin/bash
# 启动生产环境，支持镜像构建

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

echo "🚀 Starting Production Environment..."

# 停止开发容器（如果存在）
docker-compose --profile dev stop

# 启动生产容器
# --build 确保构建最新镜像
# -d 后台运行
# --remove-orphans 清理不再使用的孤儿容器
docker-compose --profile prod up -d --build --remove-orphans

echo "✅ Production environment started!"
echo "👉 App URL: http://$(hostname -I | awk '{print $1}'):12543"
