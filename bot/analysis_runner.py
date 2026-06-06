"""
analysis_runner.py — 單一使用者波段分析執行模組
對指定股票跑 fetch_candles + analyze_swing，回傳格式化訊息
"""

import datetime
from enum import Enum
from typing import Optional

from daily_data import fetch_candles
from swing_strategy import analyze_swing
from notifier import COLOR_INFO, COLOR_YELLOW, COLOR_RED


class AnalysisMode(Enum):
    PREMARKET  = "premarket"
    POSTMARKET = "postmarket"


# 波段分析參數預設值（當使用者 config 未提供時使用）
_DEFAULT_SWING_CFG = {
    "swing_ma_days": 20,
    "swing_lookback_days": 20,
    "swing_pullback_warn_pct": 5.0,
    "swing_pullback_pct": 8.0,
    "swing_ma_warn_pct": 2.0,
}


def run_analysis_for_user(
    user_cfg: dict,
    swing_cfg: dict,
    mode: AnalysisMode,
) -> Optional[dict]:
    """
    對單一使用者的股票執行波段分析。

    Args:
        user_cfg:  使用者監控設定（stock_id, stock_name, cost_price）
        swing_cfg: 波段分析參數
        mode:      PREMARKET 或 POSTMARKET

    Returns:
        dict: {"title": str, "message": str, "alerts": list, "color": int}
        None: stock_id 缺失或 API 呼叫失敗
    """
    stock_id   = user_cfg.get("stock_id")
    stock_name = user_cfg.get("stock_name", "")
    cost       = user_cfg.get("cost_price")

    if not stock_id:
        return None

    cfg = {**_DEFAULT_SWING_CFG, **swing_cfg}

    try:
        df = fetch_candles(stock_id, days=60)
    except Exception as e:
        print(f"[analysis] 取得 {stock_id} 日 K 失敗：{e}")
        return None

    try:
        result = analyze_swing(
            df,
            lookback=cfg["swing_lookback_days"],
            ma_days=cfg["swing_ma_days"],
            pullback_warn=cfg["swing_pullback_warn_pct"],
            pullback_alert=cfg["swing_pullback_pct"],
            ma_warn=cfg["swing_ma_warn_pct"],
        )
    except ValueError as e:
        print(f"[analysis] {stock_id} 分析失敗：{e}")
        return None

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    cost_str = ""
    if cost:
        cost_str = f"（成本 {cost} 元，{(result.close - cost) / cost * 100:+.2f}%）"

    if mode == AnalysisMode.PREMARKET:
        title = f"📊 盤前分析｜{now_str}"
        signal = _signal_line(result)
        message = (
            f"【{stock_id} {stock_name}】\n"
            f"昨收　{result.close} 元{cost_str}\n"
            f"MA20　{result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
            f"高點　{result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
            f"訊號　{signal}"
        )
    else:
        title = f"📈 盤後分析｜{now_str}"
        signal = _signal_line(result)
        message = (
            f"【{stock_id} {stock_name}】\n"
            f"收盤　{result.close} 元{cost_str}\n"
            f"MA20　{result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
            f"高點　{result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
            f"訊號　{signal}"
        )

    # 整體顏色：有紅燈用紅、有黃燈用黃、否則用灰
    colors = [a.color for a in result.alerts]
    color = COLOR_RED if COLOR_RED in colors else (COLOR_YELLOW if COLOR_YELLOW in colors else COLOR_INFO)

    return {
        "title": title,
        "message": message,
        "alerts": result.alerts,
        "color": color,
    }


def _signal_line(result) -> str:
    """依警報列表回傳單行訊號摘要"""
    colors = [a.color for a in result.alerts]
    if COLOR_RED in colors:
        return "🔴 注意：有警示訊號，請謹慎"
    if COLOR_YELLOW in colors:
        return "🟡 留意：有預警訊號"
    return "✅ 無異常，可續抱"
