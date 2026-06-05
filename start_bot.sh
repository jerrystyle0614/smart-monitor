#!/bin/bash
# 啟動 LINE Bot webhook server（需另開終端機跑 ngrok）
cd "$(dirname "$0")"
source .env
echo "[Smart Monitor Bot] 啟動 webhook server on port 8000..."
uvicorn bot.server:app --port 8000
