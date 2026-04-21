#!/bin/bash

echo ">>> 前台启动 FastAPI 与自动化引擎..."
# FastAPI 会在启动后，通过后台线程连接 Playwright，并自动拉起前端 UI。
uvicorn webBossAI:app --port 8000
