"""
monitor_engine.py — 背景監控引擎
每 30 秒輪詢所有 MONITORING 使用者的股價，條件觸發時推播 LINE + Discord
"""

import threading
import time
import os
import datetime
import requests

POLL_INTERVAL_SEC = 30

# 台股交易時段（UTC+8）：週一到週五 09:00–13:30
_MARKET_OPEN  = datetime.time(9, 0)
_MARKET_CLOSE = datetime.time(13, 30)
_TZ_OFFSET    = datetime.timezone(datetime.timedelta(hours=8))


def is_trading_hours() -> bool:
    """判斷現在是否為台股交易時段（週一到週五 09:00–13:30 UTC+8）"""
    now = datetime.datetime.now(_TZ_OFFSET)
    if now.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE


def seconds_until_next_open() -> float:
    """計算距離下一個台股開盤還有幾秒（最多等到下週一 09:00）"""
    now = datetime.datetime.now(_TZ_OFFSET)
    # 找下一個週一到週五的 09:00
    candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    # 跳過週末
    while candidate.weekday() >= 5:
        candidate += datetime.timedelta(days=1)
    return (candidate - now).total_seconds()


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
        """啟動背景監控執行緒，若已在執行中則略過（防止重複啟動）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[monitor] 背景監控引擎已啟動")

    def stop(self):
        """停止背景監控執行緒，並等待執行緒結束（最多 35 秒）"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=35)
        print("[monitor] 背景監控引擎已停止")

    def _loop(self):
        """主迴圈：交易時段每 30 秒掃描一次；非交易時段休眠到下次開盤"""
        while self._running:
            if not is_trading_hours():
                secs = seconds_until_next_open()
                print(f"[monitor] 非交易時段，休眠 {int(secs // 60)} 分鐘至下次開盤")
                self._sleep(secs)
                continue
            try:
                self._scan_all()
            except Exception as e:
                print(f"[monitor] 掃描異常：{e}")
            self._sleep(POLL_INTERVAL_SEC)

    def _sleep(self, total_secs: float):
        """可中斷的休眠：每 0.5 秒檢查一次 self._running"""
        steps = int(total_secs / 0.5)
        for _ in range(steps):
            if not self._running:
                break
            time.sleep(0.5)

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
        # 不在此處設定 fired 旗標，由 _dispatch 在推播成功後再設定
        if (stop is not None
                and price <= stop
                and not self._store.get_alert_fired(uid, "stop")):
            pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
            alerts.append({
                "title": "⚠️ 停損觸發",
                "message": (
                    f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                    f"已跌破停損價 {stop} 元，建議評估出場。"
                ),
                "color": 0xE74C3C,
                "fired_key": "stop",
            })

        # 目標一條件：股價 >= 目標一價，且尚未觸發過
        # 不在此處設定 fired 旗標，由 _dispatch 在推播成功後再設定
        if (target1 is not None
                and price >= target1
                and not self._store.get_alert_fired(uid, "target1")):
            pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
            alerts.append({
                "title": "🎯 目標一達成",
                "message": (
                    f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                    f"已達目標一 {target1} 元，可考慮獲利了結。"
                ),
                "color": 0x2ECC71,
                "fired_key": "target1",
            })

        return alerts

    def _dispatch(self, uid, alerts):
        """將警報同時推播到 LINE 和 Discord，推播成功後才設定 fired 旗標"""
        for alert in alerts:
            self._line.push(uid, f"{alert['title']}\n\n{alert['message']}")
            self._discord.send(alert["title"], alert["message"], alert["color"])
            # 推播完成後才標記已觸發，確保失敗時下次仍能重送
            self._store.set_alert_fired(uid, alert["fired_key"], True)
