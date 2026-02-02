#!/bin/bash

echo "正在停止 app.py 服务..."

# 查找并杀死 app.py 相关进程
echo "正在搜索 app.py 运行中的进程..."
PIDS=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')

if [ -n "$PIDS" ]; then
    echo "找到运行中的 app.py 进程，PID: $PIDS"
    echo "正在停止进程..."
    
    # 先尝试优雅停止 (SIGTERM)
    for PID in $PIDS; do
        echo "正在停止进程 $PID..."
        kill $PID
    done
    
    # 等待进程结束
    sleep 3
    
    # 检查是否还有进程在运行，如果有则强制杀死
    REMAINING_PIDS=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')
    if [ -n "$REMAINING_PIDS" ]; then
        echo "强制停止剩余进程: $REMAINING_PIDS"
        for PID in $REMAINING_PIDS; do
            kill -9 $PID
        done
        sleep 1
    fi
    
    echo "app.py 服务已停止"
else
    echo "未找到运行中的 app.py 进程"
fi

echo "完成"
