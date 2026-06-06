"""
test_analysis_runner.py — analysis_runner 單元測試
mock fetch_candles 和 analyze_swing，驗證訊息格式化邏輯
"""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from bot.analysis_runner import run_analysis_for_user, AnalysisMode


def _make_df():
    """建立 25 筆假日 K 資料"""
    dates = pd.date_range("2026-01-01", periods=25, freq="B").strftime("%Y-%m-%d").tolist()
    closes = [60.0 + i * 0.2 for i in range(25)]
    return pd.DataFrame({
        "date": dates, "open": closes, "high": closes,
        "low": closes, "close": closes, "volume": [1000] * 25,
    })


def test_premarket_returns_title_and_message():
    """盤前分析應回傳包含標題和訊息的 dict"""
    cfg = {
        "stock_id": "3312", "stock_name": "弘憶",
        "cost_price": 64.0,
    }
    swing_cfg = {
        "swing_ma_days": 20, "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0, "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }
    with patch("bot.analysis_runner.fetch_candles", return_value=_make_df()):
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
    assert result is not None
    assert "title" in result
    assert "message" in result
    assert "3312" in result["message"] or "弘憶" in result["message"]
    assert "alerts" in result


def test_postmarket_returns_title_and_message():
    """盤後分析應回傳包含標題和訊息的 dict"""
    cfg = {
        "stock_id": "2330", "stock_name": "台積電",
        "cost_price": 900.0,
    }
    swing_cfg = {
        "swing_ma_days": 20, "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0, "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }
    with patch("bot.analysis_runner.fetch_candles", return_value=_make_df()):
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.POSTMARKET)
    assert result is not None
    assert "盤後" in result["title"] or "分析" in result["title"]


def test_fetch_failure_returns_none():
    """fetch_candles 失敗時應回傳 None，不崩潰"""
    cfg = {"stock_id": "3312", "stock_name": "弘憶", "cost_price": 64.0}
    swing_cfg = {
        "swing_ma_days": 20, "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0, "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }
    with patch("bot.analysis_runner.fetch_candles", side_effect=RuntimeError("API 失敗")):
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
    assert result is None


def test_missing_stock_id_returns_none():
    """stock_id 為 None 時應回傳 None"""
    cfg = {"stock_id": None, "stock_name": "未知", "cost_price": 64.0}
    swing_cfg = {
        "swing_ma_days": 20, "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0, "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }
    result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
    assert result is None
