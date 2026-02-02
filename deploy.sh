#!/bin/bash
set -e

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

echo "📦 Starting Deployment Workflow..."

# 0. 权限检查：确保是以 cqj 用户运行
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" != "cqj" ]; then
    echo "❌ Error: This script must be run as user 'cqj'. Current user is '$CURRENT_USER'."
    echo "💡 Please switch user: su - cqj"
    exit 1
fi

# 1. 自动检测本地是否有未提交的代码
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Uncommitted changes detected."
    # 提示输入说明并 commit
    read -p "📝 Enter commit message: " msg
    if [ -z "$msg" ]; then
        echo "❌ Commit message cannot be empty. Aborting."
        exit 1
    fi
    git add .
    git commit -m "$msg"
    echo "✅ Changes committed."
else
    echo "✅ No uncommitted changes found. Skipping commit."
fi

# 2. 自动创建一个带时间戳的 Git 标签
TAG_NAME="backup-$(date +%Y%m%d-%H%M%S)"
echo "🏷️  Creating git tag: $TAG_NAME"
git tag "$TAG_NAME"

# 3. 将代码和标签推送到远程仓库
echo "☁️  Pushing code and tags to remote (backup)..."
# 获取当前分支名称
CURRENT_BRANCH=$(git branch --show-current)
git push backup "$CURRENT_BRANCH"
git push backup "$TAG_NAME"

# 4. 调用 start-prod.sh 重启生产容器
echo "🔄 Restarting production container..."
./start-prod.sh

echo "🎉 Deployment successfully completed!"
echo "🔖 Backup Tag: $TAG_NAME"
