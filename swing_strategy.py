"""
swing_strategy.py — 波段指標計算與訊號判斷
接收日 K DataFrame，計算 MA20 與近 20 日高點回撤，回傳 SwingResult
"""

from dataclasses import dataclass, field

import pandas as pd

from notifier import COLOR_INFO, COLOR_YELLOW, COLOR_RED
from strategy import Alert


@dataclass
class SwingResult:
    """波段分析結果"""
    close: float           # 最新收盤價
    ma20: float            # 20 日均線
    high20: float          # 近 20 日最高收盤
    pct_from_ma20: float   # 距 MA20 偏離 %（正=上方，負=下方）
    pullback_pct: float    # 從高點回撤 %
    alerts: list[Alert] = field(default_factory=list)


def analyze_swing(
    df: pd.DataFrame,
    lookback: int,
    ma_days: int,
    pullback_warn: float,
    pullback_alert: float,
    ma_warn: float,
) -> SwingResult:
    """
    計算波段技術指標並判斷訊號。

    Args:
        df:             日 K DataFrame（date, open, high, low, close, volume）
        lookback:       高點回撤的觀察天數（取近 N 日最高收盤）
        ma_days:        均線天數
        pullback_warn:  高點回撤黃燈門檻（%）
        pullback_alert: 高點回撤紅燈門檻（%）
        ma_warn:        距 MA 黃燈門檻（%），在均線上方但不足此值才觸發

    Returns:
        SwingResult，alerts 為空表示無異常

    Raises:
        ValueError: 資料筆數不足 ma_days
    """
    # 資料筆數不足時提早拋錯，避免計算出無意義的均線
    if len(df) < ma_days:
        raise ValueError(
            f"資料不足：需要至少 {ma_days} 筆，目前只有 {len(df)} 筆"
        )

    close_latest = float(df["close"].iloc[-1])
    ma20 = float(df["close"].tail(ma_days).mean())
    high20 = float(df["close"].tail(lookback).max())

    # 計算距均線偏離幅度與從高點回撤幅度
    pct_from_ma20 = round((close_latest - ma20) / ma20 * 100, 2)
    pullback_pct = round((high20 - close_latest) / high20 * 100, 2)

    alerts: list[Alert] = []

    # --- 均線訊號判斷 ---

    # 跌破 20MA → 紅燈：趨勢轉弱，提示出場
    if close_latest < ma20:
        alerts.append(Alert(
            title="跌破 20 日均線",
            message=(
                f"收盤 {close_latest} 元，已跌破 MA20（{ma20:.2f} 元）\n"
                f"偏離幅度 {pct_from_ma20:+.2f}%，波段趨勢轉弱，請注意出場時機。"
            ),
            color=COLOR_RED,
        ))
    # 在均線上方但距離不足 ma_warn% → 黃燈：即將測試支撐
    elif 0 <= pct_from_ma20 < ma_warn:
        alerts.append(Alert(
            title="均線支撐即將測試",
            message=(
                f"收盤 {close_latest} 元，距 MA20（{ma20:.2f} 元）僅 {pct_from_ma20:+.2f}%\n"
                f"若明日跌破 {ma20:.2f} 元，建議考慮減碼。"
            ),
            color=COLOR_YELLOW,
        ))

    # --- 高點回撤訊號判斷 ---

    # 回撤超過 pullback_alert% → 紅燈：動能明顯減弱
    if pullback_pct >= pullback_alert:
        alerts.append(Alert(
            title="高點回撤警示",
            message=(
                f"收盤 {close_latest} 元，距近 {lookback} 日高點（{high20} 元）"
                f"已回撤 {pullback_pct:.2f}%\n"
                f"超過 {pullback_alert}% 警戒線，動能減弱，請評估出場。"
            ),
            color=COLOR_RED,
        ))
    # 回撤介於 pullback_warn~pullback_alert% → 黃燈：接近警戒
    elif pullback_warn <= pullback_pct < pullback_alert:
        alerts.append(Alert(
            title="高點回撤預警",
            message=(
                f"收盤 {close_latest} 元，距近 {lookback} 日高點（{high20} 元）"
                f"已回撤 {pullback_pct:.2f}%\n"
                f"接近 {pullback_alert}% 警戒，請留意。"
            ),
            color=COLOR_YELLOW,
        ))

    return SwingResult(
        close=close_latest,
        ma20=ma20,
        high20=high20,
        pct_from_ma20=pct_from_ma20,
        pullback_pct=pullback_pct,
        alerts=alerts,
    )
