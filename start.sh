#!/bin/bash
# Docker 镜像同步工具 - Web 服务启动脚本

echo "🚀 启动 Docker 镜像同步工具 Web 服务..."
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3，请先安装 Python 3.6+"
    exit 1
fi

# 检查是否安装了依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 正在安装依赖..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败，请手动执行: pip3 install -r requirements.txt"
        exit 1
    fi
fi

# 启动服务
echo "✅ 启动 Web 服务..."
echo "📍 访问地址: http://localhost:8080"
echo "按 Ctrl+C 停止服务"
echo ""

python3 app.py
