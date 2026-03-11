#!/bin/bash
# 启动生产环境，支持镜像构建

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

# 确保日志目录存在
mkdir -p logs
# 启动前清空生产环境日志
> logs/prod_report.log
echo "🧹 已清空旧生产日志: logs/prod_report.log"

echo "🚀 Starting Production Environment..."

# 取消代理设置，避免 Docker 构建时连接问题
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"
echo "🌐 已取消代理设置"

# 启动生产容器
# --build 确保构建最新镜像
# -d 后台运行
# --remove-orphans 清理不再使用的孤儿容器
docker compose --profile prod up -d --build --remove-orphans

echo "✅ Production environment started!"
echo "👉 App URL: http://$(hostname -I | awk '{print $1}'):12543"
echo ""
echo "🔍 查看生产环境实时日志 (直接复制下面命令):"
echo "tail -f $(pwd)/logs/prod_report.log"
echo ""
echo "💡 或者查看容器标准输出:"
echo "docker logs -f langextract-app-prod"
