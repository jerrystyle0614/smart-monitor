#!/bin/bash
# 啟動 LINE Bot webhook server + Cloudflare Tunnel
cd "$(dirname "$0")"
source .env

echo "[Smart Monitor Bot] 啟動 Cloudflare Tunnel (smart.aurabizon.com)..."
cloudflared tunnel run smart-monitor &
TUNNEL_PID=$!

# 等待 Tunnel 建立連線（最多 15 秒）
echo "[Smart Monitor Bot] 等待 Tunnel 連線..."
for i in $(seq 1 15); do
    if curl -s --max-time 2 https://smart.aurabizon.com/health > /dev/null 2>&1; then
        echo "[Smart Monitor Bot] Tunnel 已就緒"
        break
    fi
    sleep 1
done

echo "[Smart Monitor Bot] 啟動 webhook server on port 8000..."
python3 -m uvicorn bot.server:app --port 8000

# uvicorn 結束後一併關閉 tunnel
kill $TUNNEL_PID 2>/dev/null
