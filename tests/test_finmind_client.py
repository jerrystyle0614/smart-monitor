"""test_finmind_client.py — FinMind API 客戶端測試"""
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

os.environ.setdefault("FINMIND_API_KEY", "test_key_12345")

from bot.stock_picker.finmind_client import FinMindClient


@pytest.fixture
def client():
    return FinMindClient()


def test_init_sets_api_key(client):
    """初始化應讀取 API key"""
    assert client.api_key == "test_key_12345"


def test_get_three_major_buyers_success(client):
    """get_three_major_buyers 應回傳買賣超資料"""
    mock_response = {
        "data": [
            {
                "date": "2026-06-07",
                "stock_id": "2330",
                "buy": 500000000,
                "sell": 100000000,
            }
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_three_major_buyers("2330", days=3)

    assert result is not None
    assert "consecutive_buy_days" in result or "data" in result


def test_get_three_major_buyers_api_failure(client):
    """API 失敗時應回傳 None"""
    with patch("bot.stock_picker.finmind_client.requests.get", side_effect=Exception("API Error")):
        result = client.get_three_major_buyers("2330")
    assert result is None


def test_get_margin_status_success(client):
    """get_margin_status 應回傳融資融券資料"""
    mock_response = {
        "data": [
            {
                "Date": "2026-06-07",
                "stock_id": "2330",
                "MarginBalance": 5000000,
                "ShortBalance": 1000000,
            },
            {
                "Date": "2026-06-06",
                "stock_id": "2330",
                "MarginBalance": 4500000,
                "ShortBalance": 900000,
            }
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_margin_status("2330")

    assert result is not None
    assert isinstance(result, dict)


def test_get_margin_status_api_failure(client):
    """API 失敗時應回傳 None"""
    with patch("bot.stock_picker.finmind_client.requests.get", side_effect=Exception("API Error")):
        result = client.get_margin_status("2330")
    assert result is None


def test_get_all_stocks_basic_returns_list(client):
    """get_all_stocks_basic 應回傳股票列表"""
    mock_response = {
        "data": [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_all_stocks_basic()

    assert isinstance(result, list)
    assert len(result) >= 0
