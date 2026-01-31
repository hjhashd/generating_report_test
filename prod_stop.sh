#!/bin/bash
# 停止生产环境

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

echo "🛑 正在停止生产环境..."

docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

echo "✅ 生产环境已停止。"
