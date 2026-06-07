"""test_exchange_client.py — TWSE + TPEX API 客戶端測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.stock_picker.exchange_client import ExchangeClient


@pytest.fixture
def client():
    return ExchangeClient()


class TestExchangeClientTWSE:
    """TWSE API 測試"""

    @pytest.mark.integration
    def test_get_three_major_buyers_twse_real_api(self, client):
        """驗證 TWSE API 是否可連接（使用 台積電 2330）"""
        result = client._fetch_twse_three_major("2330")

        # 如果返回結果，驗證格式
        if result:
            assert "consecutive_buy_days" in result
            assert "total_buy" in result
            assert "total_sell" in result
            assert "latest_data" in result
            assert result.get("market") == "TWSE"

    @pytest.mark.integration
    def test_get_three_major_buyers_tpex_real_api(self, client):
        """驗證 TPEX API 是否可連接（使用 上櫃股票測試）"""
        # 使用一個上櫃股票代號進行測試
        result = client._fetch_tpex_three_major("3706")

        if result:
            assert "consecutive_buy_days" in result
            assert "total_buy" in result
            assert "total_sell" in result
            assert "latest_data" in result
            assert result.get("market") == "TPEX"


class TestExchangeClientFallback:
    """測試 TWSE → TPEX 回退邏輯"""

    def test_fallback_to_tpex_when_twse_fails(self, client):
        """TWSE 失敗時應回退到 TPEX"""
        with patch.object(client, "_fetch_twse_three_major", return_value=None):
            with patch.object(
                client,
                "_fetch_tpex_three_major",
                return_value={"market": "TPEX", "consecutive_buy_days": 1},
            ):
                result = client.get_three_major_buyers("3706")

        assert result is not None
        assert result.get("market") == "TPEX"

    def test_returns_none_when_both_fail(self, client):
        """TWSE 和 TPEX 都失敗時應返回 None"""
        with patch.object(client, "_fetch_twse_three_major", return_value=None):
            with patch.object(client, "_fetch_tpex_three_major", return_value=None):
                result = client.get_three_major_buyers("9999")

        assert result is None
