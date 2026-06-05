"""
monitor_engine.py — 背景監控引擎
每 30 秒輪詢所有 MONITORING 使用者的股價，條件觸發時推播 LINE + Discord
"""

import threading
import time
import os
import requests

POLL_INTERVAL_SEC = 30


def fetch_price(stock_id: str):
    """從 Fugle REST API 查詢最新股價（收盤或即時價），失敗回傳 None"""
    api_key = os.environ.get("FUGLE_API_KEY")
    if not api_key or not stock_id:
        return None
    try:
        r = requests.get(
            f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{stock_id}",
            headers={"X-API-KEY": api_key},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("closePrice") or data.get("lastPrice")
    except Exception as e:
        print(f"[monitor] 查詢 {stock_id} 失敗：{e}")
    return None


class MonitorEngine:
    def __init__(self, store, line, discord):
        self._store = store
        self._line = line
        self._discord = discord
        self._running = False
        self._thread = None

    def start(self):
        """啟動背景監控執行緒"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[monitor] 背景監控引擎已啟動")

    def stop(self):
        """停止背景監控執行緒"""
        self._running = False
        print("[monitor] 背景監控引擎已停止")

    def _loop(self):
        """主迴圈：每 POLL_INTERVAL_SEC 秒執行一次掃描"""
        while self._running:
            try:
                self._scan_all()
            except Exception as e:
                print(f"[monitor] 掃描異常：{e}")
            time.sleep(POLL_INTERVAL_SEC)

    def _scan_all(self):
        """掃描所有 MONITORING 使用者並處理警報"""
        users = self._store.get_all_monitoring_users()
        for uid in users:
            try:
                alerts = self._check_user(uid)
                if alerts:
                    self._dispatch(uid, alerts)
            except Exception as e:
                print(f"[monitor] 處理使用者 {uid} 失敗：{e}")

    def _check_user(self, uid):
        """查詢股價並比對條件，回傳觸發的警報列表"""
        cfg = self._store.get_config(uid)
        if not cfg:
            return []

        stock_id = cfg.get("stock_id")
        stock_name = cfg.get("stock_name", "")
        cost = cfg.get("cost_price")
        stop = cfg.get("stop_loss_moving")
        target1 = cfg.get("target_stage_1")

        price = fetch_price(stock_id)
        if price is None:
            return []

        alerts = []

        # 停損條件：股價 <= 停損價，且尚未觸發過
        if (stop is not None
                and price <= stop
                and not self._store.get_alert_fired(uid, "stop")):
            self._store.set_alert_fired(uid, "stop", True)
            pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
            alerts.append({
                "title": "⚠️ 停損觸發",
                "message": (
                    f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                    f"已跌破停損價 {stop} 元，建議評估出場。"
                ),
                "color": 0xE74C3C,
            })

        # 目標一條件：股價 >= 目標一價，且尚未觸發過
        if (target1 is not None
                and price >= target1
                and not self._store.get_alert_fired(uid, "target1")):
            self._store.set_alert_fired(uid, "target1", True)
            pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
            alerts.append({
                "title": "🎯 目標一達成",
                "message": (
                    f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                    f"已達目標一 {target1} 元，可考慮獲利了結。"
                ),
                "color": 0x2ECC71,
            })

        return alerts

    def _dispatch(self, uid, alerts):
        """將警報同時推播到 LINE 和 Discord"""
        for alert in alerts:
            self._line.push(uid, f"{alert['title']}\n\n{alert['message']}")
            self._discord.send(alert["title"], alert["message"], alert["color"])
