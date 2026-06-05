"""
test_analyze.py — analyze 模組整合測試
mock daily_data 與 notifier，驗證輸出格式與推播邏輯
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from analyze import run_analysis, Mode


def _make_df(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "date": [f"2026-{i+1:02d}-01" for i in range(n)],
        "open":  closes,
        "high":  [c + 1 for c in closes],
        "low":   [c - 1 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def _make_config() -> dict:
    return {
        "stock_id": "3312",
        "stock_name": "弘憶",
        "cost_price": 64.86,
        "swing_ma_days": 20,
        "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0,
        "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }


def test_run_analysis_premarket_sends_notification(capsys):
    """盤前模式：run_analysis 應呼叫 notifier.send 一次"""
    closes = [65.0] * 25
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.PREMARKET)

    mock_notifier.send.assert_called_once()
    title, message, color = mock_notifier.send.call_args[0]
    assert "盤前分析" in title


def test_run_analysis_postmarket_sends_notification(capsys):
    """盤後模式：run_analysis 應呼叫 notifier.send 一次"""
    closes = [65.0] * 25
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.POSTMARKET)

    mock_notifier.send.assert_called_once()
    title, _, _ = mock_notifier.send.call_args[0]
    assert "盤後分析" in title


def test_run_analysis_red_alert_sends_extra_notification():
    """有紅燈警報時，應額外再呼叫一次 notifier.send"""
    # 收盤跌破 MA20 → 紅燈
    closes = [70.0] * 19 + [60.0]
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.POSTMARKET)

    # 1 次摘要 + 至少 1 次警報
    assert mock_notifier.send.call_count >= 2


def test_run_analysis_handles_fetch_error(capsys):
    """fetch_candles 失敗時，應印錯誤訊息，不 raise"""
    config = _make_config()

    with patch("analyze.fetch_candles", side_effect=RuntimeError("API 失敗")):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.PREMARKET)

    captured = capsys.readouterr()
    assert "失敗" in captured.out
    mock_notifier.send.assert_not_called()
