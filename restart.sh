#!/bin/bash

echo "正在重启 app.py 服务..."

# 查找并杀死 app.py 相关进程
echo "正在搜索 app.py 运行中的进程..."
PIDS=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')

if [ -n "$PIDS" ]; then
    echo "找到运行中的 app.py 进程，PID: $PIDS"
    echo "正在停止进程..."
    
    # 先尝试优雅停止
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
    
    echo "app.py 进程已停止"
else
    echo "未找到运行中的 app.py 进程"
fi

echo "清理旧的日志文件..."
rm nohup.out

echo "正在启动 app.py..."

# 启动新的 app.py 进程
nohup python app.py > nohup.out 2>&1 &

# 等待一下确保进程启动
sleep 2

# 检查进程是否成功启动
NEW_PID=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')
if [ -n "$NEW_PID" ]; then
    echo "app.py 已成功启动，PID: $NEW_PID"
    echo "正在显示日志输出，按 Ctrl+C 退出日志查看..."
    echo "----------------------------------------"
    tail -f nohup.out
else
    echo "错误：app.py 启动失败"
    echo "请检查 nohup.out 文件获取错误信息："
    cat nohup.out
    exit 1
fi 