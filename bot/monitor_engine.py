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
    datetime.time(8, 50),   # 盤前
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


def _fetch_candles_for_analysis(stock_id: str, days: int, is_premarket: bool):
    """用 yfinance 抓歷史日K供分析用，盤後補上 Fugle 即時報價作為當日收盤。"""
    try:
        import yfinance as yf
        import pandas as pd

        ticker = yf.Ticker(f"{stock_id}.TW")
        period = f"{max(days // 20, 2)}mo"
        df = ticker.history(period=period)
        if df is None or df.empty:
            return None

        df = df.dropna(subset=["Close"])
        df = df.reset_index()
        df["date"] = df["Date"].astype(str).str[:10]
        df["open"] = df["Open"]
        df["high"] = df["High"]
        df["low"] = df["Low"]
        df["close"] = df["Close"]
        df["volume"] = (df["Volume"] / 1000).round().astype(int)
        df = df[["date", "open", "high", "low", "close", "volume"]].tail(days)

        # 盤後才補當日即時報價（確保今日收盤價正確）
        if not is_premarket:
            try:
                live_price = fetch_price(stock_id)
                if live_price and live_price > 0:
                    today = datetime.date.today().isoformat()
                    if df.iloc[-1]["date"] < today:
                        import numpy as np
                        new_row = pd.DataFrame([{
                            "date": today,
                            "open": live_price,
                            "high": live_price,
                            "low": live_price,
                            "close": live_price,
                            "volume": 0,
                        }])
                        df = pd.concat([df, new_row], ignore_index=True).tail(days)
                    else:
                        df.loc[df.index[-1], "close"] = live_price
            except Exception:
                pass

        return df

    except Exception as e:
        print(f"[monitor] {stock_id} yfinance K線取得失敗：{e}")
        return None


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
    def __init__(self, stores, clients, discord):
        # stores: {"line": UserStore, ...} OR a bare UserStore (backward compat)
        # clients: {"line": LineClient, ...} OR a bare client (backward compat)
        if isinstance(stores, dict):
            self._stores = stores
            self._clients = clients
            self._store = stores.get("line") or next(iter(stores.values()))
            self._line = clients.get("line") or next(iter(clients.values()))
        else:
            # Legacy positional: MonitorEngine(store, client, discord)
            self._store = stores
            self._line = clients
            self._stores = {"line": stores}
            self._clients = {"line": clients}
        self._discord = discord
        self._running = False
        self._thread = None
        self._analysis_fired = set()  # 記錄今日已觸發的分析，格式："YYYY-MM-DD HH:MM"

    def _get_client(self, platform: str):
        return self._clients.get(platform, self._line)

    def _get_store(self, platform: str):
        return self._stores.get(platform, self._store)

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

        觸發條件：now >= 分析時間 且 now < 分析時間 + 15 分鐘
        （允許 server 重啟後補推，避免在觸發窗口內重啟導致漏推）
        """
        from bot.analysis_runner import AnalysisMode
        now = datetime.datetime.now(_TZ_OFFSET)
        now_mins = now.hour * 60 + now.minute
        for t in _ANALYSIS_TIMES:
            fire_key = "{} {}".format(now.strftime('%Y-%m-%d'), t.strftime('%H:%M'))
            t_mins = t.hour * 60 + t.minute
            # 已到達分析時間，且在 15 分鐘補推窗口內
            if t_mins <= now_mins < t_mins + 15 and fire_key not in self._analysis_fired:
                mode = AnalysisMode.PREMARKET if t == _ANALYSIS_TIMES[0] else AnalysisMode.POSTMARKET
                return True, mode, fire_key
        return False, None, ""

    def _run_analysis_all(self, mode) -> None:
        """對所有平台的 MONITORING 使用者執行分析並推播"""
        for platform, store in self._stores.items():
            client = self._get_client(platform)
            self._run_analysis_for_store(store, client, mode)

    def _run_analysis_for_store(self, store, client, mode) -> None:
        """對指定 store 的所有 MONITORING 使用者執行分析並推播"""
        from bot.analysis_runner import AnalysisMode
        from bot.analysis.engine import AnalysisEngine
        from bot.data.market_context import fetch_market_context, format_market_context

        users = store.get_all_monitoring_users()
        if not users:
            return

        is_premarket = (mode == AnalysisMode.PREMARKET)
        mode_label = "盤前" if is_premarket else "盤後"
        print(f"[monitor] 執行{mode_label}分析，共 {len(users)} 位使用者")

        # 盤前才抓市場背景（所有使用者共用同一份）
        market_context_text = ""
        if is_premarket:
            try:
                ctx = fetch_market_context()
                market_context_text = format_market_context(ctx) if ctx else ""
                if market_context_text:
                    print("[monitor] 盤前市場背景已取得")
            except Exception as e:
                print(f"[monitor] 市場背景取得失敗：{e}")

        engine = AnalysisEngine(use_cache=True)

        for uid in users:
            try:
                watchlist = store.get_watchlist(uid)
            except Exception as e:
                print(f"[monitor] 處理使用者 {uid} 失敗：{e}")
                continue
            if not watchlist:
                continue
            for stock in watchlist:
                try:
                    stock_id = stock.get("stock_id")
                    stock_name = stock.get("stock_name", "")
                    if not stock_id:
                        continue

                    df = _fetch_candles_for_analysis(stock_id, days=20, is_premarket=is_premarket)
                    if df is None or len(df) == 0:
                        print(f"[monitor] {stock_id} K 線資料取得失敗，跳過")
                        continue

                    current_price = float(df.iloc[-1].get("close", 0))

                    lines = ["日期\t\t開盤\t\t高\t\t低\t\t收盤\t\t成交量"]
                    for _, row in df.iterrows():
                        lines.append(
                            "{}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:,}".format(
                                str(row.get("date", ""))[:10],
                                row.get("open", 0), row.get("high", 0),
                                row.get("low", 0), row.get("close", 0),
                                int(row.get("volume", 0)),
                            )
                        )
                    candle_data = "\n".join(lines)

                    if is_premarket:
                        result = engine.analyze_pre_market(
                            stock_id=stock_id,
                            stock_name=stock_name,
                            candle_data=candle_data,
                            current_price=current_price,
                            market_context_text=market_context_text,
                        )
                    else:
                        result = engine.analyze_post_market(
                            stock_id=stock_id,
                            stock_name=stock_name,
                            candle_data=candle_data,
                            current_price=current_price,
                        )

                    if not result:
                        print(f"[monitor] {stock_id} 分析結果為空，跳過")
                        continue

                    message = self._format_scheduled_message(
                        stock_id, stock_name, current_price, result,
                        mode_label=mode_label,
                        market_context_text=market_context_text if is_premarket else "",
                    )
                    client.push(uid, message)
                    self._discord.send(
                        f"{mode_label}分析 - {stock_name}({stock_id})",
                        message,
                        0x3498DB if is_premarket else 0x9B59B6,
                    )

                except Exception as e:
                    import traceback
                    print(f"[monitor] {stock_id} 分析推播失敗 uid={uid}：{e}")
                    print(traceback.format_exc())

    def _format_scheduled_message(
        self, stock_id, stock_name, current_price, analysis,
        mode_label="盤前", market_context_text=""
    ):
        """格式化排程推播的分析訊息（盤前/盤後自動推播用）"""
        label = "目前價格" if mode_label == "盤前" else "今日收盤價"
        parts = [f"📊 {mode_label}分析 - {stock_name} ({stock_id})"]
        parts.append(f"{label}：{current_price:.2f} 元")
        parts.append("")

        if market_context_text:
            parts.append(market_context_text)
            parts.append("")

        technical = analysis.get("technical", {})
        if isinstance(technical, dict) and technical:
            parts.append("🔍 技術面")
            parts.append(f"- 趨勢：{technical.get('trend', '未知')}")
            s = technical.get("support")
            if s:
                parts.append(f"- 支撐：{s}")
            r = technical.get("resistance")
            if r:
                parts.append(f"- 壓力：{r}")
            mi = technical.get("market_impact")
            if mi:
                parts.append(f"- 市場連動：{mi}")
            ob = technical.get("open_bias")
            if ob:
                parts.append(f"- 開盤預判：{ob}")
            sm = technical.get("summary")
            if sm:
                parts.append(f"- 總結：{sm}")
            parts.append("")

        entry_exit = analysis.get("entry_exit", {})
        if isinstance(entry_exit, dict) and entry_exit:
            section = "💡 進出場建議" if mode_label == "盤前" else "🌅 明日展望"
            parts.append(section)
            ep = entry_exit.get("entry_price")
            if ep:
                parts.append(f"- {'建議進場' if mode_label == '盤前' else '建議監控'}價：{ep}")
            sl = entry_exit.get("stop_loss")
            if sl:
                parts.append(f"- 停損：{sl}")
            targets = entry_exit.get("exit_targets")
            if isinstance(targets, dict):
                parts.append(
                    f"- 目標：短期 {targets.get('short_term')} / 中期 {targets.get('medium_term')}"
                )
            rl = entry_exit.get("risk_level")
            if rl:
                parts.append(f"- 風險等級：{rl}")
            parts.append("")

        parts.append("⚠️ 本分析僅供參考，投資決策應自負其責")
        return "\n".join(parts)

    def _loop(self):
        """主迴圈：分析推播優先檢查，交易時段內才執行股價掃描"""
        while self._running:
            # 分析推播不受交易時段限制（08:30 盤前、13:35 盤後都需觸發）
            should_run, mode, fire_key = self._should_run_analysis()
            if should_run:
                self._analysis_fired.add(fire_key)
                self._run_analysis_all(mode)

            if is_trading_hours():
                # 交易時段：執行股價監控掃描
                try:
                    self._scan_all()
                except Exception as e:
                    print(f"[monitor] 掃描異常：{e}")
                self._sleep(POLL_INTERVAL_SEC)
            else:
                # 非交易時段：若在分析時間前後 15 分鐘內，繼續每 30 秒輪詢
                # 否則休眠到下次分析時間前 5 分鐘
                now = datetime.datetime.now(_TZ_OFFSET)
                now_mins = now.hour * 60 + now.minute
                near_analysis = any(
                    -5 <= (now_mins - (t.hour * 60 + t.minute)) < 15
                    for t in _ANALYSIS_TIMES
                )
                if near_analysis:
                    self._sleep(POLL_INTERVAL_SEC)
                else:
                    # 計算距離下一個分析時間還有幾秒
                    secs_to_analysis = None
                    for t in _ANALYSIS_TIMES:
                        t_mins = t.hour * 60 + t.minute
                        diff = t_mins - now_mins
                        if diff > 0:  # 今天尚未到達的分析時間
                            s = diff * 60 - now.second
                            if secs_to_analysis is None or s < secs_to_analysis:
                                secs_to_analysis = s
                    if secs_to_analysis is None:
                        # 今天所有分析時間都過了，等到明天第一個
                        t0 = _ANALYSIS_TIMES[0]
                        next_mins = (24 * 60 - now_mins) + t0.hour * 60 + t0.minute
                        secs_to_analysis = next_mins * 60 - now.second
                    # 提前 5 分鐘醒來
                    wake_secs = max(secs_to_analysis - 300, 60)
                    print(f"[monitor] 非交易時段，休眠 {int(wake_secs // 60)} 分鐘")
                    self._sleep(wake_secs)

    def _sleep(self, total_secs: float):
        """可中斷的休眠：每 0.5 秒檢查一次 self._running"""
        steps = int(total_secs / 0.5)
        for _ in range(steps):
            if not self._running:
                break
            time.sleep(0.5)

    def _scan_all(self):
        """掃描所有平台的 MONITORING 使用者並處理警報"""
        for platform, store in self._stores.items():
            client = self._get_client(platform)
            users = store.get_all_monitoring_users()
            for uid in users:
                try:
                    alerts = self._check_user_with_store(uid, store)
                    if alerts:
                        self._dispatch_with_client(uid, alerts, store, client)
                except Exception as e:
                    print(f"[monitor] 處理使用者 {uid}（{platform}）失敗：{e}")

    def _check_user_with_store(self, uid, store):
        """查詢所有監控股票的股價並比對條件，回傳觸發的警報列表"""
        watchlist = store.get_watchlist(uid)
        if not watchlist:
            return []

        alerts = []
        for stock_index, stock in enumerate(watchlist):
            stock_alerts = self._check_stock_with_store(uid, stock_index, stock, store)
            alerts.extend(stock_alerts)
        return alerts

    def _check_user(self, uid):
        """向下相容包裝"""
        return self._check_user_with_store(uid, self._store)

    def _check_stock_with_store(self, uid, stock_index, stock, store):
        """查詢單支股票的股價並比對條件，回傳觸發的警報列表"""
        stock_id = stock.get("stock_id")
        if not stock_id:
            return []

        stock_name = stock.get("stock_name", "")
        cost_raw = stock.get("cost_price")
        stop_raw = stock.get("stop_loss_moving")
        target1_raw = stock.get("target_stage_1")

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

        if (stop is not None
                and price <= stop
                and not store.get_alert_fired(uid, stock_index, "stop")):
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

        if (target1 is not None
                and price >= target1
                and not store.get_alert_fired(uid, stock_index, "target1")):
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

    def _check_stock(self, uid, stock_index, stock):
        """向下相容包裝"""
        return self._check_stock_with_store(uid, stock_index, stock, self._store)

    def _dispatch_with_client(self, uid, alerts, store, client):
        """將警報推播到指定 client 和 Discord，推播成功後才設定 fired 旗標"""
        for alert in alerts:
            client.push(uid, "{}\n\n{}".format(alert["title"], alert["message"]))
            self._discord.send(alert["title"], alert["message"], alert["color"])
            stock_index = alert.get("stock_index", 0)
            store.set_alert_fired(uid, stock_index, alert["fired_key"], True)

    def _dispatch(self, uid, alerts):
        """向下相容包裝"""
        self._dispatch_with_client(uid, alerts, self._store, self._line)
