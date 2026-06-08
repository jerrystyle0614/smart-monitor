"""test_router.py — ServiceRouter 路由測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")

from bot.router import (
    ServiceRouter,
    handle_message,
    handle_follow,
    SERVICE_PERMISSIONS,
)


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def mock_line():
    return MagicMock()


def test_handle_follow_sends_welcome(mock_store, mock_line):
    """新使用者 follow 事件應 push 歡迎訊息與服務選單"""
    # get_plan 回 "free" 代表尚未初始化的新使用者
    mock_store.get_plan.return_value = "free"
    handle_follow("U123", mock_store, mock_line)
    assert mock_line.push.call_count >= 1
    pushed = "".join(str(c) for c in mock_line.push.call_args_list)
    assert "歡迎" in pushed


def test_handle_follow_skips_when_already_registered(mock_store, mock_line):
    """已初始化的使用者重複 follow 不應再推歡迎訊息（去重）"""
    mock_store.get_plan.return_value = "pro"
    handle_follow("U123", mock_store, mock_line)
    mock_line.push.assert_not_called()


def test_handle_message_cooldown_blocks(mock_store, mock_line):
    """被冷卻時應回覆提示"""
    mock_store.check_cooldown.return_value = True
    mock_store.get_current_service.return_value = None
    handle_message("U456", "hello", mock_store, mock_line, "token")
    mock_line.reply.assert_called()
    call_text = str(mock_line.reply.call_args)
    assert "太快" in call_text or "稍後" in call_text


def test_handle_message_permission_denied(mock_store, mock_line):
    """權限不足時應回覆升級訊息"""
    mock_store.check_cooldown.return_value = False
    mock_store.get_current_service.return_value = None
    mock_store.get_plan.return_value = "free"
    # 嘗試選擇盤前分析（需要 basic/pro）
    handle_message("U789", "2", mock_store, mock_line, "token")
    call_text = str(mock_line.reply.call_args_list)
    assert "升級" in call_text or "功能" in call_text


def test_handle_message_menu_selection_1(mock_store, mock_line):
    """輸入 1 應進入股票監控"""
    mock_store.check_cooldown.return_value = False
    mock_store.get_current_service.return_value = None
    mock_store.get_plan.return_value = "free"
    with patch("bot.router.StockMonitorService"):
        handle_message("U999", "1", mock_store, mock_line, "token")
    # 應呼叫 set_service_state
    assert mock_store.set_service_state.called or mock_line.reply.called


def test_service_permissions_structure():
    """權限表應包含三個服務"""
    assert "stock_monitor" in SERVICE_PERMISSIONS
    assert "pre_market" in SERVICE_PERMISSIONS
    assert "post_market" in SERVICE_PERMISSIONS
    assert "free" in SERVICE_PERMISSIONS["stock_monitor"]
    assert "free" not in SERVICE_PERMISSIONS["pre_market"]
