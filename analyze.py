"""
analyze.py — 波段分析入口
手動執行或由排程觸發，執行盤前（08:30）或盤後（13:35）分析
用法：
    python analyze.py --pre     盤前分析
    python analyze.py --post    盤後分析
    python analyze.py           依當前時間自動判斷
"""

import json
import sys
import datetime
from enum import Enum

from daily_data import fetch_candles
from notifier import DiscordNotifier, COLOR_INFO, COLOR_GREEN, COLOR_YELLOW, COLOR_RED
from swing_strategy import analyze_swing, SwingResult
from strategy import Alert


class Mode(Enum):
    PREMARKET  = "premarket"
    POSTMARKET = "postmarket"


def _detect_mode() -> Mode:
    """依當前時間自動判斷盤前或盤後"""
    now = datetime.datetime.now().time()
    cutoff = datetime.time(13, 0)
    return Mode.POSTMARKET if now >= cutoff else Mode.PREMARKET


def _format_premarket(stock_name: str, stock_id: str, result: SwingResult) -> tuple[str, str]:
    """回傳盤前分析的 (title, message)"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"📊 盤前分析｜{now_str}"

    signal_line = "✅ 無異常，可續抱"
    if any(a.color == COLOR_RED for a in result.alerts):
        signal_line = "🔴 注意：有警示訊號，請謹慎"
    elif any(a.color == COLOR_YELLOW for a in result.alerts):
        signal_line = "🟡 留意：有預警訊號"

    message = (
        f"【{stock_id} {stock_name}】\n"
        f"  昨收  {result.close} 元\n"
        f"  MA20  {result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%，"
        f"{'均線上方' if result.pct_from_ma20 >= 0 else '均線下方'}）\n"
        f"  高點  {result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
        f"  訊號  {signal_line}"
    )
    return title, message


def _format_postmarket(stock_name: str, stock_id: str, result: SwingResult, prev_close: float) -> tuple[str, str]:
    """回傳盤後分析的 (title, message)"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"📊 盤後分析｜{now_str}"

    # 計算今日漲跌幅
    pct_change = round((result.close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    # 依距均線位置給出明日操作建議
    if result.pct_from_ma20 >= 2.0:
        tomorrow = f"續抱，若跌破 {result.ma20:.2f} 考慮減碼"
    elif 0 <= result.pct_from_ma20 < 2.0:
        tomorrow = f"留意：明日若跌破 {result.ma20:.2f} 元（MA20）建議減碼"
    else:
        tomorrow = f"警示：已跌破 MA20（{result.ma20:.2f} 元），評估出場"

    message = (
        f"【{stock_id} {stock_name}】\n"
        f"  今收  {result.close} 元（{pct_change:+.2f}%）\n"
        f"  MA20  {result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
        f"  高點  {result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
        f"  明日  {tomorrow}"
    )
    return title, message


def run_analysis(config: dict, notifier: DiscordNotifier, mode: Mode) -> None:
    """
    執行一次波段分析並推播結果。

    Args:
        config:   config.json 載入的設定 dict
        notifier: DiscordNotifier 實例
        mode:     PREMARKET 或 POSTMARKET
    """
    stock_id   = config["stock_id"]
    stock_name = config["stock_name"]
    ma_days    = config["swing_ma_days"]
    lookback   = config["swing_lookback_days"]

    # 抓取日 K 資料，失敗時印錯誤並提早返回
    try:
        df = fetch_candles(stock_id, days=lookback + 10)
    except RuntimeError as e:
        print(f"[錯誤] 抓取 {stock_id} 日 K 失敗：{e}")
        return

    # 執行波段指標計算，資料不足時印錯誤並提早返回
    try:
        result = analyze_swing(
            df,
            lookback=lookback,
            ma_days=ma_days,
            pullback_warn=config["swing_pullback_warn_pct"],
            pullback_alert=config["swing_pullback_pct"],
            ma_warn=config["swing_ma_warn_pct"],
        )
    except ValueError as e:
        print(f"[錯誤] 分析失敗：{e}")
        return

    # 取前一日收盤，供盤後計算今日漲跌幅
    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else result.close

    # 依模式組摘要標題與內容
    if mode == Mode.PREMARKET:
        title, message = _format_premarket(stock_name, stock_id, result)
        summary_color = COLOR_INFO
    else:
        title, message = _format_postmarket(stock_name, stock_id, result, prev_close)
        summary_color = COLOR_INFO

    # 終端機輸出摘要
    print(f"\n{'═'*45}")
    print(f"{title}")
    print(f"{'─'*45}")
    print(message)
    print(f"{'═'*45}\n")

    # 推播摘要訊息
    notifier.send(title, message, summary_color)

    # 額外推播各個警報訊號（紅燈、黃燈各自獨立推播）
    for alert in result.alerts:
        print(f"[警報] {alert.title}")
        notifier.send(alert.title, alert.message, alert.color)


def _load_config(path: str = "config.json") -> dict:
    """載入 JSON 設定檔"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--pre" in args:
        mode = Mode.PREMARKET
    elif "--post" in args:
        mode = Mode.POSTMARKET
    else:
        mode = _detect_mode()

    config   = _load_config()
    notifier = DiscordNotifier()
    run_analysis(config, notifier, mode)
