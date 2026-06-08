"""
monitor_engine.py — 背景監控引擎
每 30 秒輪詢所有 MONITORING 使用者的股價，條件觸發時推播 LINE + Discord
"""

import json
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

# 每日分析推播的觸發時間（UTC+8）
_ANALYSIS_TIMES = [
    datetime.time(8, 30),   # 盤前
    datetime.time(13, 35),  # 盤後
]


def is_trading_hours() -> bool:
    """判斷現在是否為台股交易時段（週一到週五 09:00–13:30 UTC+8）。
    設定 FORCE_TRADING_HOURS=1 可在測試時強制視為交易時段。"""
    if os.environ.get("FORCE_TRADING_HOURS") == "1":
        return True
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
        self._analysis_fired = set()  # 記錄今日已觸發的分析，格式："YYYY-MM-DD HH:MM"

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

    def _should_run_analysis(self):
        """
        判斷現在是否應觸發分析推播。
        回傳 (should_run, mode, fire_key)
        """
        from bot.analysis_runner import AnalysisMode
        now = datetime.datetime.now(_TZ_OFFSET)
        for t in _ANALYSIS_TIMES:
            fire_key = f"{now.strftime('%Y-%m-%d')} {t.strftime('%H:%M')}"
            window = abs((now.hour * 60 + now.minute) - (t.hour * 60 + t.minute))
            if window <= 2 and fire_key not in self._analysis_fired:
                mode = AnalysisMode.PREMARKET if t == datetime.time(8, 30) else AnalysisMode.POSTMARKET
                return True, mode, fire_key
        return False, None, ""

    def _run_analysis_all(self, mode) -> None:
        """對所有 MONITORING 使用者執行波段分析並推播"""
        from bot.analysis_runner import run_analysis_for_user
        users = self._store.get_all_monitoring_users()
        if not users:
            return

        swing_cfg = {}
        try:
            with open("config.json", encoding="utf-8") as f:
                swing_cfg = json.load(f)
        except Exception:
            pass

        mode_label = "盤前" if "PREMARKET" in str(mode) else "盤後"
        print(f"[monitor] 執行{mode_label}分析，共 {len(users)} 位使用者")

        for uid in users:
            try:
                user_cfg = self._store.get_config(uid)
                result = run_analysis_for_user(user_cfg, swing_cfg, mode)
                if result is None:
                    continue
                self._line.push(uid, f"{result['title']}\n\n{result['message']}")
                self._discord.send(result["title"], result["message"], result["color"])
                for alert in result["alerts"]:
                    self._line.push(uid, f"{alert.title}\n\n{alert.message}")
                    self._discord.send(alert.title, alert.message, alert.color)
            except Exception as e:
                print(f"[monitor] 分析推播失敗 uid={uid}：{e}")

    def _loop(self):
        """主迴圈：交易時段每 30 秒掃描一次；非交易時段休眠到下次開盤"""
        while self._running:
            if not is_trading_hours():
                secs = seconds_until_next_open()
                print(f"[monitor] 非交易時段，休眠 {int(secs // 60)} 分鐘至下次開盤")
                self._sleep(secs)
                continue

            # 檢查是否到達分析推播時間（08:30 或 13:35 ±2 分鐘）
            should_run, mode, fire_key = self._should_run_analysis()
            if should_run:
                self._analysis_fired.add(fire_key)
                self._run_analysis_all(mode)

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
        """查詢所有監控股票的股價並比對條件，回傳觸發的警報列表"""
        watchlist = self._store.get_watchlist(uid)
        if not watchlist:
            return []

        alerts = []
        for stock_index, stock in enumerate(watchlist):
            stock_alerts = self._check_stock(uid, stock_index, stock)
            alerts.extend(stock_alerts)
        return alerts

    def _check_stock(self, uid, stock_index, stock):
        """查詢單支股票的股價並比對條件，回傳觸發的警報列表"""
        stock_id = stock.get("stock_id")
        if not stock_id:
            return []

        stock_name = stock.get("stock_name", "")
        cost_raw = stock.get("cost_price")
        stop_raw = stock.get("stop_loss_moving")
        target1_raw = stock.get("target_stage_1")

        # 敏感欄位解密後為字串，需轉為 float
        try:
            cost = float(cost_raw) if cost_raw is not None else None
        except (ValueError, TypeError):
            cost = None
        try:
            stop = float(stop_raw) if stop_raw is not None else None
        except (ValueError, TypeError):
            stop = None
        try:
            target1 = float(target1_raw) if target1_raw is not None else None
        except (ValueError, TypeError):
            target1 = None

        price = fetch_price(stock_id)
        if price is None:
            return []

        alerts = []

        # 停損條件：股價 <= 停損價，且尚未觸發過
        # 不在此處設定 fired 旗標，由 _dispatch 在推播成功後再設定
        if (stop is not None
                and price <= stop
                and not self._store.get_alert_fired(uid, stock_index, "stop")):
            pct = "{:+.2f}%".format((price - cost) / cost * 100) if cost else ""
            alerts.append({
                "title": "⚠️ 停損觸發",
                "message": (
                    "【{} {}】現價 {} 元 {}\n"
                    "已跌破停損價 {} 元，建議評估出場。\n\n"
                    "💡 如需刪除此監控，請輸入『狀態』查看監控清單，\n"
                    "然後輸入『刪除 {}』移除此股票。"
                ).format(stock_id, stock_name, price, pct, stop, stock_index + 1),
                "color": 0xE74C3C,
                "fired_key": "stop",
                "stock_index": stock_index,
            })

        # 目標一條件：股價 >= 目標一價，且尚未觸發過
        # 不在此處設定 fired 旗標，由 _dispatch 在推播成功後再設定
        if (target1 is not None
                and price >= target1
                and not self._store.get_alert_fired(uid, stock_index, "target1")):
            pct = "{:+.2f}%".format((price - cost) / cost * 100) if cost else ""
            alerts.append({
                "title": "🎯 目標一達成",
                "message": (
                    "【{} {}】現價 {} 元 {}\n"
                    "已達目標一 {} 元，可考慮獲利了結。\n\n"
                    "💡 如需刪除此監控，請輸入『狀態』查看監控清單，\n"
                    "然後輸入『刪除 {}』移除此股票。"
                ).format(stock_id, stock_name, price, pct, target1, stock_index + 1),
                "color": 0x2ECC71,
                "fired_key": "target1",
                "stock_index": stock_index,
            })

        return alerts

    def _dispatch(self, uid, alerts):
        """將警報同時推播到 LINE 和 Discord，推播成功後才設定 fired 旗標"""
        for alert in alerts:
            self._line.push(uid, "{}\n\n{}".format(alert["title"], alert["message"]))
            self._discord.send(alert["title"], alert["message"], alert["color"])
            # 推播完成後才標記已觸發，確保失敗時下次仍能重送
            stock_index = alert.get("stock_index", 0)
            self._store.set_alert_fired(uid, stock_index, alert["fired_key"], True)
