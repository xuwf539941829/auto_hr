#!/bin/bash

echo ">>> 后台启动 Web UI 控制台..."
streamlit run app.py &
UI_PID=$!
sleep 3
echo ">>> Web UI 已启动 (PID: $UI_PID)，您可以在浏览器中访问"

echo ">>> 启动 AI 招聘引擎..."
# 若要修改岗位名称，请带上 --job 参数，例如 python webBossAI.py --job="售后工程师"
python webBossAI.py

# 脚本退出时清理后台的 Streamlit 进程
kill $UI_PID
