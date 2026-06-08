"""
analysis_runner.py — 單一使用者波段分析執行模組
對指定股票跑 fetch_candles + analyze_swing，回傳格式化訊息
"""

import datetime
import os
from enum import Enum
from typing import Optional

from daily_data import fetch_candles
from swing_strategy import analyze_swing, SwingResult
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

    signal = _signal_line(result)
    ai_explanation = _ai_explain(stock_id, stock_name, result, mode, df)

    if mode == AnalysisMode.PREMARKET:
        title = f"📊 盤前分析｜{now_str}"
        message = (
            f"【{stock_id} {stock_name}】\n"
            f"昨收　{result.close} 元{cost_str}\n"
            f"MA20　{result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
            f"高點　{result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
            f"訊號　{signal}"
        )
    else:
        title = f"📈 盤後分析｜{now_str}"
        message = (
            f"【{stock_id} {stock_name}】\n"
            f"收盤　{result.close} 元{cost_str}\n"
            f"MA20　{result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
            f"高點　{result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
            f"訊號　{signal}"
        )

    if ai_explanation:
        message += f"\n\n💡 Smart 建議\n{ai_explanation}"

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


def _ai_explain(stock_id, stock_name, result, mode, df):
    # type: (str, str, SwingResult, AnalysisMode, object) -> str
    """
    用一次 Claude API 呼叫，對 swing 結果生成白話解釋。
    失敗時靜默回傳空字串，不影響主訊息。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    try:
        import anthropic
        import pandas as pd

        # 整理警報文字
        alert_lines = ""
        for a in result.alerts:
            alert_lines += f"- {a.title}：{a.message}\n"
        if not alert_lines:
            alert_lines = "- 無警示\n"

        time_label = "盤前" if mode == AnalysisMode.PREMARKET else "盤後"
        price_label = "昨收" if mode == AnalysisMode.PREMARKET else "今日收盤"

        # 今日（最後一筆）開/高/低/量（成交量由股轉張：÷ 1000）
        today_row = df.iloc[-1]
        today_open   = float(today_row.get("open",   0))
        today_high   = float(today_row.get("high",   0))
        today_low    = float(today_row.get("low",    0))
        today_volume = int(today_row.get("volume",   0)) // 1000  # 股 → 張

        # 平均量（近20日，排除今日）
        recent = df.tail(21).iloc[:-1] if len(df) > 1 else df
        avg_volume = int(recent["volume"].mean()) // 1000 if len(recent) > 0 else 0  # 股 → 張
        volume_ratio = (today_volume / avg_volume * 100) if avg_volume > 0 else 0

        # 完整近20日 K 線（日期、開、高、低、收、量（張））
        kline_rows = df.tail(20)
        kline_lines = "日期\t開\t高\t低\t收\t量(張)\n"
        for _, row in kline_rows.iterrows():
            kline_lines += (
                f"{str(row.get('date',''))[:10]}\t"
                f"{row.get('open',0)}\t{row.get('high',0)}\t"
                f"{row.get('low',0)}\t{row.get('close',0)}\t"
                f"{int(row.get('volume',0)) // 1000:,}\n"
            )

        prompt = (
            f"你是台股投資助理，用白話文向不懂技術分析的散戶解釋以下{time_label}分析結果。\n\n"
            f"【股票】{stock_name}（{stock_id}）\n\n"
            f"【技術指標】\n"
            f"{price_label}：{result.close} 元\n"
            f"今日開盤：{today_open} 元　最高：{today_high} 元　最低：{today_low} 元\n"
            f"成交量：{today_volume:,} 張（近20日均量 {avg_volume:,} 張，約均量的 {volume_ratio:.0f}%）\n"
            f"MA20：{result.ma20:.2f} 元（偏離 {result.pct_from_ma20:+.2f}%）\n"
            f"近20日最高收盤：{result.high20} 元（從高點下跌 {result.pullback_pct:.2f}%）\n\n"
            f"【近20日 K 線】\n"
            f"{kline_lines}\n"
            f"【系統偵測到的訊號】\n{alert_lines}\n"
            f"請用白話文分析（5～8 句話）：\n"
            f"1. 今日 K 線型態（長黑、長紅、跳空、十字線等）代表什麼意思\n"
            f"2. 成交量是否異常（爆量、量縮），代表什麼\n"
            f"3. 從近20日 K 線看出什麼走勢型態（頭肩頂、三角收斂、雙底等，若無明顯型態也要說明）\n"
            f"4. 為什麼會亮紅燈或黃燈（若有）\n"
            f"5. 投資人應該注意什麼\n\n"
            f"語氣平穩，不要製造恐慌，不要給明確買賣建議，直接輸出說明文字即可（不用標題、不用編號）。"
        )

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"[analysis] AI 解釋失敗（忽略）：{e}")
        return ""
