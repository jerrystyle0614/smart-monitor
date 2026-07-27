#!/bin/bash
# 停止 Smart Monitor Bot：Cloudflare Tunnel + webhook server
cd "$(dirname "$0")"

echo "[Smart Monitor] 停止服務..."

[ -f .tunnel.pid ] && kill "$(cat .tunnel.pid)" 2>/dev/null && echo "  ✅ Tunnel 已停止" || true
rm -f .tunnel.pid

[ -f .server.pid ] && kill "$(cat .server.pid)" 2>/dev/null && echo "  ✅ Server 已停止" || true
rm -f .server.pid

OLD_PID=$(lsof -ti:8000 2>/dev/null || true)
[ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null && echo "  ✅ Port 8000 已清除" || true

pkill -f "cloudflared tunnel run smart-monitor" 2>/dev/null || true

echo "[Smart Monitor] 🛑 服務已完全停止"
