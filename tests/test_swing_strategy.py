"""
test_swing_strategy.py — swing_strategy 模組單元測試
直接建構 DataFrame 測試，不需任何外部 API
"""

import pytest
import pandas as pd
from swing_strategy import SwingResult, analyze_swing
from notifier import COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_INFO


def _make_df(closes: list[float]) -> pd.DataFrame:
    """建構測試用 DataFrame，只需提供收盤價序列"""
    n = len(closes)
    return pd.DataFrame({
        "date": [f"2026-{i+1:02d}-01" for i in range(n)],
        "open":  closes,
        "high":  [c + 1 for c in closes],
        "low":   [c - 1 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_analyze_swing_returns_result():
    """analyze_swing 應回傳 SwingResult"""
    closes = [65.0] * 25
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    assert isinstance(result, SwingResult)
    assert result.close == pytest.approx(65.0)
    assert result.ma20 == pytest.approx(65.0)


def test_no_signal_when_above_ma_and_low_pullback():
    """均線上方且回撤小，應無警報（綠燈）"""
    closes = [60.0] * 19 + [65.0]  # 最新收盤高於 MA20
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    assert result.alerts == []


def test_red_alert_when_close_below_ma20():
    """收盤跌破 20MA 應觸發紅燈警報"""
    # 前 19 天收 70，最後一天跌到 60（遠低於 MA20 ≈ 69.5）
    closes = [70.0] * 19 + [60.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_RED in colors


def test_yellow_alert_when_close_near_ma20():
    """距 MA20 不足 2% 應觸發黃燈預警"""
    # MA20 ≈ 65.0，最新收盤 65.5（+0.77%，< 2% 警戒）
    closes = [65.0] * 19 + [65.5]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_YELLOW in colors


def test_red_alert_when_pullback_over_8pct():
    """從近 20 日高點回撤 ≥ 8% 應觸發紅燈"""
    # 近 20 日最高 80，最新收盤 73（回撤 8.75%）
    closes = [70.0] * 15 + [80.0] * 4 + [73.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_RED in colors


def test_yellow_alert_when_pullback_5_to_8pct():
    """從近 20 日高點回撤 5~8% 應觸發黃燈預警"""
    # 近 20 日最高 80，最新收盤 75（回撤 6.25%）
    closes = [70.0] * 15 + [80.0] * 4 + [75.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_YELLOW in colors


def test_insufficient_data_raises():
    """資料筆數不足 ma_days 時應 raise ValueError"""
    closes = [65.0] * 10  # 只有 10 筆，ma_days=20
    with pytest.raises(ValueError, match="資料不足"):
        analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                      pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
