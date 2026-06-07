"""test_pre_market_service.py — PreMarketService 測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")

from bot.services.pre_market import PreMarketService


@pytest.fixture
def service():
    return PreMarketService()


def test_pre_market_service_has_one_step(service):
    """盤前分析服務應有 1 個步驟"""
    assert len(service.steps) == 1
    assert service.steps[0].field == "stock_id"


def test_on_complete_runs_analysis(service):
    """完成後應執行分析並推播"""
    mock_store = MagicMock()
    mock_store.get_plan.return_value = "basic"
    mock_line = MagicMock()

    draft = {
        "stock_id": {
            "stock_id": "2330",
            "stock_name": "台積電"
        }
    }

    with patch("bot.services.pre_market.run_analysis_for_user") as mock_analysis:
        mock_analysis.return_value = {
            "title": "📊 盤前分析",
            "message": "台積電技術面分析...",
            "alerts": [],
            "color": 0
        }
        with patch("bot.services.pre_market.push_to_line"):
            service.on_complete("U123", draft, mock_store, mock_line)

    mock_analysis.assert_called_once()
