#!/bin/bash
# 停止开发环境

# 确保脚本在项目目录下执行
cd "$(dirname "$0")"

echo "🛑 正在停止开发环境..."

docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

echo "✅ 开发环境已停止。"
