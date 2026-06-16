#!/bin/bash
# 啟動 Smart Monitor Bot：Cloudflare Tunnel + webhook server
# 重開機後執行一次即可，關閉 terminal 也不影響運行
# 停止：kill $(cat .tunnel.pid) $(cat .server.pid)
cd "$(dirname "$0")"
source .env
export PYTHONUNBUFFERED=1

# ── 清掉舊的 process ──────────────────────────────────────────
echo "[Smart Monitor] 清除舊程序..."
# 先停止 launchd 管理的服務，避免與本腳本啟動的程序同時運行造成重複推播
PLIST=~/Library/LaunchAgents/com.smartmonitor.server.plist
[ -f "$PLIST" ] && launchctl unload "$PLIST" 2>/dev/null || true
[ -f .tunnel.pid ] && kill "$(cat .tunnel.pid)" 2>/dev/null || true; rm -f .tunnel.pid
[ -f .server.pid ] && kill "$(cat .server.pid)" 2>/dev/null || true; rm -f .server.pid
# 確保 port 8000 淨空
OLD_PID=$(lsof -ti:8000 2>/dev/null || true)
[ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null && sleep 1 || true

# ── 啟動 Cloudflare Tunnel ────────────────────────────────────
echo "[Smart Monitor] 啟動 Cloudflare Tunnel..."
mkdir -p log
nohup cloudflared tunnel run smart-monitor >> log/tunnel.log 2>&1 &
echo $! > .tunnel.pid

# ── 啟動 webhook server ───────────────────────────────────────
echo "[Smart Monitor] 啟動 webhook server on port 8000..."
nohup python3 -m uvicorn bot.server:app --port 8000 >> log/server.log 2>&1 &
echo $! > .server.pid

# ── 等待 server 就緒（最多 15 秒）────────────────────────────
echo "[Smart Monitor] 等待 server 就緒..."
for i in $(seq 1 15); do
    if curl -s --max-time 1 http://localhost:8000/health > /dev/null 2>&1; then
        echo "[Smart Monitor] ✅ Server 已就緒 (PID $(cat .server.pid))"
        break
    fi
    sleep 1
done

# ── 等待 Tunnel 就緒（最多 15 秒）────────────────────────────
echo "[Smart Monitor] 等待 Tunnel 就緒..."
for i in $(seq 1 15); do
    if curl -s --max-time 2 https://smart.aurabizon.com/health > /dev/null 2>&1; then
        echo "[Smart Monitor] ✅ Tunnel 已就緒 (PID $(cat .tunnel.pid))"
        echo "[Smart Monitor] 🚀 全部啟動完成！"
        exit 0
    fi
    sleep 1
done

echo "[Smart Monitor] ⚠️  Tunnel 尚未回應，請查看 log/tunnel.log"
echo "[Smart Monitor]    Server log: log/server.log"
