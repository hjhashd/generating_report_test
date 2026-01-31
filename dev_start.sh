#!/bin/bash
# 启动开发环境 (热重载模式)

# 确保脚本在项目目录下执行
cd "$(dirname "$0")"

echo "🚀 正在启动开发环境..."
echo "📂 挂载当前代码目录，支持热更新"
echo "🔌 端口: 34521"

# 强制重新构建 (确保依赖更新) 并启动
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d

echo "✅ 开发环境已启动！"
echo "👉 访问地址: http://localhost:34521"
echo "📝 查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f"
