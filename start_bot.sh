#!/bin/bash
# 啟動 LINE Bot webhook server + Cloudflare Tunnel
cd "$(dirname "$0")"
source .env

echo "[Smart Monitor Bot] 清除使用者資料..."
rm -rf users/
mkdir -p users/

echo "[Smart Monitor Bot] 啟動 Cloudflare Tunnel (smart.aurabizon.com)..."
cloudflared tunnel run smart-monitor &
TUNNEL_PID=$!

echo "[Smart Monitor Bot] 啟動 webhook server on port 8000..."
export CLEAR_ON_START=1
python3 -m uvicorn bot.server:app --port 8000

# uvicorn 結束後一併關閉 tunnel
kill $TUNNEL_PID 2>/dev/null
