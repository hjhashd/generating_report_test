#!/bin/bash

# 1. 强制检查 root 身份
if [ "$EUID" -ne 0 ]; then
  echo "❌ 错误: 必须以 root 身份运行此脚本。"
  echo "请尝试使用: sudo $0"
  exit 1
fi

echo "🚀 正在启动一键重启流程..."

# 2. 定义变量
# 获取脚本所在目录的绝对路径，确保不依赖硬编码路径
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 设置服务端口环境变量，优先使用已有环境变量，默认 34521
export PORT=${PORT:-34521}
# 显式声明环境为开发/测试环境
export ENV="development"

CONDA_ENV="LangExtract"

# 尝试多个可能的 Conda 路径
CONDA_PATHS=(
  "/opt/conda_envs/anaconda3/etc/profile.d/conda.sh"
  "/root/anaconda3/etc/profile.d/conda.sh"
  "/home/$(whoami)/anaconda3/etc/profile.d/conda.sh"
  "/opt/anaconda3/etc/profile.d/conda.sh"
)

CONDA_SH=""
for path in "${CONDA_PATHS[@]}"; do
  if [ -f "$path" ]; then
    CONDA_SH="$path"
    break
  fi
done

# 3. 切换到项目目录
echo "📂 进入项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR" || { echo "❌ 无法进入目录 $PROJECT_DIR"; exit 1; }

# 确保日志目录存在
mkdir -p logs

# 兼容性处理：创建指向 logs/test_report.log 的软链接，方便用户在根目录查看
if [ -L "test_report.log" ]; then
    rm "test_report.log"
elif [ -f "test_report.log" ]; then
    mv "test_report.log" "test_report.log.bak"
fi
ln -s logs/test_report.log test_report.log

# 4. 停止旧服务
echo "🛑 正在停止占用端口 $PORT 的旧服务..."
PID=$(netstat -tunlp | grep ":$PORT " | awk '{print $7}' | cut -d'/' -f1)
if [ -n "$PID" ]; then
    echo "发现进程 $PID 占用端口 $PORT，正在停止..."
    kill -9 "$PID"
else
    echo "端口 $PORT 未被占用，无需操作。"
fi
sleep 1

# 5. 激活环境 (优先 Conda, 其次 .venv)
if [ -f "$CONDA_SH" ]; then
    echo "🐍 正在尝试激活 Conda 环境: $CONDA_ENV"
    source "$CONDA_SH"
    if conda activate "$CONDA_ENV" 2>/dev/null; then
        echo "✅ 已激活 Conda 环境: $CONDA_ENV"
    else
        echo "⚠️ 未找到 Conda 环境 $CONDA_ENV"
        if [ -d "../.venv" ]; then
            echo "🌳 发现本地 .venv，正在激活..."
            source "../.venv/bin/activate"
        else
            echo "⚠️ 未找到本地 .venv，尝试使用系统环境..."
        fi
    fi
else
    if [ -d "../.venv" ]; then
        echo "🌳 发现本地 .venv，正在激活..."
        source "../.venv/bin/activate"
    else
        echo "⚠️ 未找到 conda 配置文件且无 .venv，尝试使用系统环境..."
    fi
fi

# 6. 后台启动服务
echo "⚙️ 正在后台启动服务 (端口: $PORT)..."
# 注意：我们将日志重定向到了 logs/test_report.log
nohup uvicorn new_report:app --host 0.0.0.0 --port $PORT > logs/test_report.log 2>&1 &

# 7. 检查启动结果
echo "⏳ 等待服务初始化..."

# 循环检查端口，最多等待 15 秒
for i in {1..15}; do
    if netstat -tunlp | grep ":$PORT " > /dev/null; then
        echo ""
        echo "✅ 服务启动成功！"
        echo "📍 访问地址: http://$(hostname -I | awk '{print $1}'):$PORT"
        echo "----------------------------------------"
        echo "📝 最新日志输出 (tail -n 10 logs/test_report.log):"
        tail -n 10 logs/test_report.log
        exit 0
    fi
    sleep 1
    echo -n "."
done

echo ""
echo "❌ 服务启动检测超时或失败，请检查 logs/test_report.log 内容。"
    echo "----------------------------------------"
    # 如果文件存在则读取，否则提示
    if [ -f logs/test_report.log ]; then
        tail -n 20 logs/test_report.log
    else
        echo "日志文件未生成。"
    fi
    exit 1
fi
