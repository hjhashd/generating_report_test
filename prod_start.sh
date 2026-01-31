#!/bin/bash
# 启动生产环境 (镜像锁定模式)

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

# 1. 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，正在创建默认配置..."
    echo "TAG=latest" > .env
fi

# 加载环境变量以显示当前版本
source .env

echo "🚀 正在启动生产环境..."
echo "📦 使用镜像版本: langextract-app:${TAG:-latest}"
echo "💾 数据目录: 已挂载宿主机生产数据"
echo "🔌 端口: 12543 (映射容器 34521)"

# 检查端口 12543 是否被占用
echo "🔎 检查端口 12543 占用情况..."
PID=$(netstat -tunlp 2>/dev/null | grep ":12543 " | awk '{print $7}' | cut -d'/' -f1)
if [ -n "$PID" ]; then
    echo "⚠️ 发现进程 $PID 正在占用端口 12543，尝试清理..."
    if kill -9 "$PID" 2>/dev/null; then
        echo "✅ 已强制杀死占用端口的进程 $PID"
    else
        echo "❌ 无法杀死进程 $PID，请尝试以 root 身份运行或手动处理。"
        # 这里不退出，因为可能是 docker-proxy 占用的，docker-compose down 会处理它
        # 但如果是其他独立进程，下面启动可能会失败
    fi
else
    echo "✅ 端口 12543 未被占用"
fi

# 显式构建镜像 (规避 docker-compose 的元数据检查问题)
# 只要本地有 python:3.9-slim，这一步通常能成功
echo "🔨 正在构建镜像..."
if docker build -t langextract-app:${TAG:-latest} .; then
    echo "✅ 镜像构建成功"
else
    echo "❌ 镜像构建失败，尝试使用旧镜像启动..."
fi

# 启动服务
# 使用 --no-build 确保直接使用我们刚才构建好的镜像，不再触发联网检查
if docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build; then
    echo "✅ 生产环境已启动！"
    echo "👉 访问地址: http://$(hostname -I | awk '{print $1}'):12543"
    echo "📝 查看日志: docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"
else
    echo "❌ 启动失败！请检查上方报错信息。"
    echo "提示：如果是镜像拉取失败，可能是网络问题或镜像源配置有误。"
    exit 1
fi
