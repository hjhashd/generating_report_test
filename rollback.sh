#!/bin/bash
set -e

# 确保脚本在项目目录下执行
cd "$(dirname "$0")" || exit 1

echo "⏮️  Starting Rollback Workflow..."

# 确保拉取最新的 tags
echo "☁️  Fetching latest tags from remote (backup)..."
git fetch backup --tags

echo "📋 Recent backup tags:"
# 列出最近 10 个以 backup- 开头的 Git 标签
# 使用 sort -V 进行版本排序（如果格式固定，sort -r 也可以）
tags=($(git tag -l "backup-*" | sort -r | head -n 10))

if [ ${#tags[@]} -eq 0 ]; then
    echo "❌ No backup tags found."
    exit 1
fi

# 显示菜单
for i in "${!tags[@]}"; do
    echo "$((i+1)). ${tags[$i]}"
done

# 允许输入序号选择版本
read -p "🔢 Select a version to rollback to (enter number): " selection

# 验证输入
if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt "${#tags[@]}" ]; then
    echo "❌ Invalid selection. Aborting."
    exit 1
fi

index=$((selection-1))
TARGET_TAG="${tags[$index]}"

echo "🔄 Rolling back to tag: $TARGET_TAG"

# 自动 git checkout 到该标签
# 注意：这会导致 detached HEAD 状态
git checkout "$TARGET_TAG"

echo "✅ Code reverted to $TARGET_TAG"

# 重启生产环境容器
echo "🚀 Restarting production environment..."
./start-prod.sh

echo "🎉 Rollback complete!"
echo "⚠️  Note: You are now in 'detached HEAD' state."
echo "💡 To return to the main development branch later, run: git checkout $(git branch --show-current 2>/dev/null || echo 'main')"
