"""test_stock_monitor_service.py — StockMonitorService 測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")

from bot.services.stock_monitor import StockMonitorService


@pytest.fixture
def service():
    return StockMonitorService()


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def mock_line():
    return MagicMock()


def test_stock_monitor_service_has_correct_steps(service):
    """服務應有 4 個步驟"""
    assert len(service.steps) == 4
    assert service.steps[0].field == "stock_id"
    assert service.steps[1].field == "total_shares"
    assert service.steps[2].field == "cost_price"
    assert service.steps[3].field == "stop_loss_moving"
    assert service.steps[3].optional == True


def test_validate_stock_success(service):
    """驗證股票代號應成功"""
    step = service.steps[0]
    with patch("bot.services.stock_monitor.FugleClient") as MockFugle:
        mock_client = MagicMock()
        mock_client.verify_stock.return_value = {"stock_id": "2330", "stock_name": "台積電"}
        MockFugle.return_value = mock_client
        ok, value, msg = step.validate("2330")
    assert ok == True
    assert value["stock_id"] == "2330"


def test_validate_stock_not_found(service):
    """驗證股票不存在應失敗"""
    step = service.steps[0]
    with patch("bot.services.stock_monitor.FugleClient") as MockFugle:
        mock_client = MagicMock()
        mock_client.verify_stock.return_value = None
        MockFugle.return_value = mock_client
        ok, value, msg = step.validate("9999")
    assert ok == False


def test_validate_shares_success(service):
    """驗證張數應成功"""
    step = service.steps[1]
    ok, value, msg = step.validate("5")
    assert ok == True
    assert value == 5


def test_validate_shares_invalid(service):
    """驗證張數無效應失敗"""
    step = service.steps[1]
    ok, value, msg = step.validate("-5")
    assert ok == False
    ok, value, msg = step.validate("abc")
    assert ok == False


def test_validate_price_success(service):
    """驗證價格應成功"""
    step = service.steps[2]
    ok, value, msg = step.validate("900.50")
    assert ok == True
    assert value == 900.50


def test_validate_price_invalid(service):
    """驗證價格無效應失敗"""
    step = service.steps[2]
    ok, value, msg = step.validate("abc")
    assert ok == False


def test_on_complete_shows_confirmation(service, mock_store, mock_line):
    """完成後應顯示確認卡片"""
    mock_store.get_plan.return_value = "free"
    draft = {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": 5,
        "cost_price": 900.0,
        "stop_loss_moving": 850.0
    }
    with patch("bot.services.stock_monitor.FugleClient") as MockFugle:
        mock_client = MagicMock()
        mock_client.get_quote.return_value = {
            "stock_id": "2330",
            "stock_name": "台積電",
            "close_price": 920.0,
            "change_pct": 2.22
        }
        MockFugle.return_value = mock_client
        service.on_complete("U123", draft, mock_store, mock_line)
    mock_line.reply.assert_called()
    call_text = str(mock_line.reply.call_args_list)
    assert "2330" in call_text or "台積電" in call_text
