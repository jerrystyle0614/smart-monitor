"""test_fugle_client.py — FugleClient 單元測試"""
import os
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

os.environ.setdefault("FUGLE_API_KEY", "test_key_12345")

from bot.data.fugle_client import FugleClient


@pytest.fixture
def client():
    return FugleClient()


def test_get_quote_success(client):
    """get_quote 應回傳股票報價資訊"""
    # marketdata v1.0 回應為扁平結構
    mock_response = {"name": "台積電", "closePrice": 920.0, "changePercent": -0.84}
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    with patch("bot.data.fugle_client.requests.get", return_value=mock_resp):
        result = client.get_quote("2330")
    assert result is not None
    assert result["stock_id"] == "2330"
    assert result["stock_name"] == "台積電"
    assert result["close_price"] == 920.0
    assert result["change_pct"] == -0.84


def test_get_quote_api_failure(client):
    """get_quote API 失敗且無 mock 回退時回傳 None"""
    # 用不在 MOCK_QUOTES 的代號，確保失敗時不會回退到 mock 資料
    with patch("bot.data.fugle_client.requests.get", side_effect=Exception("API Error")):
        result = client.get_quote("0000")
    assert result is None


def test_verify_stock_by_code(client):
    """verify_stock 優先用代號查詢（marketdata v1.0 扁平結構）"""
    mock_response = {"name": "台積電", "closePrice": 920.0}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response
    with patch("bot.data.fugle_client.requests.get", return_value=mock_resp):
        result = client.verify_stock("2330")
    assert result is not None
    assert result["stock_id"] == "2330"
    assert result["stock_name"] == "台積電"


def test_verify_stock_not_found(client):
    """verify_stock 查不到時回傳 None"""
    with patch("bot.data.fugle_client.requests.get", side_effect=Exception("Not Found")):
        result = client.verify_stock("9999")
    assert result is None


def test_fetch_candles_success(client):
    """fetch_candles 應回傳 DataFrame（官方 fugle_marketdata SDK）"""
    candle_data = {
        "data": [
            {"date": "2026-01-01", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
            {"date": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1100},
        ]
    }
    mock_rest = MagicMock()
    mock_rest.stock.historical.candles.return_value = candle_data

    with patch("fugle_marketdata.RestClient", return_value=mock_rest):
        # 讓 _append_today_candle 的即時報價呼叫靜默失敗，回傳原 df
        with patch("bot.data.fugle_client.requests.get", side_effect=Exception("no intraday")):
            result = client.fetch_candles("2330", days=60)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2


def test_fetch_candles_failure(client):
    """fetch_candles 失敗時應拋出例外"""
    mock_rest = MagicMock()
    mock_rest.stock.historical.candles.side_effect = Exception("Download failed")
    with patch("fugle_marketdata.RestClient", return_value=mock_rest):
        with pytest.raises(Exception):
            client.fetch_candles("2330", days=60)


def test_load_stock_map_caches():
    """load_stock_map 應快取結果"""
    # 建立新的客戶端，確保 cache 為空
    fresh_client = FugleClient()
    with patch("bot.data.fugle_client.pd.read_csv") as mock_read:
        mock_read.return_value = pd.DataFrame({
            "code": ["2330", "2454"],
            "name": ["台積電", "聯發科"]
        })
        result1 = fresh_client.load_stock_map()
        call_count_after_first = mock_read.call_count
        result2 = fresh_client.load_stock_map()
        call_count_after_second = mock_read.call_count
    # 第一次呼叫應該讀取兩個 CSV（TWSE 和 TPEx）
    assert call_count_after_first == 2
    # 第二次呼叫使用快取，不再讀取
    assert call_count_after_second == 2
    assert "台積電" in result1
    assert result1["台積電"] == "2330"
