@echo off

echo ^>^>^> 后台启动 Web UI 控制台...
start "AI Web UI" streamlit run app.py

timeout /t 3

echo ^>^>^> 启动 AI 招聘引擎...
rem 若要修改岗位名称，请带上 --job 参数，例如 python webBossAI.py --job="售后工程师"
python webBossAI.py
