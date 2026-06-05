"""
test_daily_data.py — daily_data 模組單元測試
使用 mock 取代真實 Fugle REST 呼叫，不需 API Key
"""

import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from daily_data import fetch_candles


def _make_mock_candles(n: int = 60) -> list[dict]:
    """產生 n 筆假日 K 資料"""
    return [
        {
            "date": f"2026-04-{i+1:02d}",
            "open": 65.0,
            "high": 66.0,
            "low": 64.0,
            "close": 65.5 + i * 0.1,
            "volume": 1000 + i * 10,
        }
        for i in range(n)
    ]


@patch.dict(os.environ, {"FUGLE_API_KEY": "test-key"})
def test_fetch_candles_returns_dataframe():
    """fetch_candles 應回傳含必要欄位的 DataFrame"""
    mock_data = _make_mock_candles(60)

    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": mock_data}

        df = fetch_candles("3312", days=60)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 60


@patch.dict(os.environ, {"FUGLE_API_KEY": "test-key"})
def test_fetch_candles_sorted_ascending():
    """回傳的 DataFrame 應依日期升冪排序（最舊在前）"""
    mock_data = _make_mock_candles(10)

    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": mock_data}

        df = fetch_candles("3312", days=10)

    assert df["date"].is_monotonic_increasing


@patch.dict(os.environ, {"FUGLE_API_KEY": "test-key"})
def test_fetch_candles_raises_on_api_error():
    """Fugle REST 回傳空資料或例外時，應 raise RuntimeError"""
    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.side_effect = Exception("API error")

        with pytest.raises(RuntimeError, match="無法取得"):
            fetch_candles("3312", days=60)


@patch.dict(os.environ, {"FUGLE_API_KEY": "test-key"})
def test_fetch_candles_raises_on_empty_data():
    """Fugle REST 回傳空列表時，應 raise RuntimeError"""
    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": []}

        with pytest.raises(RuntimeError, match="無法取得"):
            fetch_candles("3312", days=60)
