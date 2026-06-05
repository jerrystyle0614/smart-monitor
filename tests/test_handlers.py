"""
test_handlers.py — handlers 模組整合測試
mock LineClient 和 UserStore，驗證事件處理邏輯
"""

import pytest
from unittest.mock import MagicMock, patch
from bot.handlers import handle_follow, handle_message


def _make_deps(state="IDLE", config=None, call_count=0):
    """建構 mock 依賴"""
    store = MagicMock()
    store.get_state.return_value = state
    store.get_config.return_value = config or {}
    store.get_daily_call_count.return_value = call_count
    line = MagicMock()
    return store, line


def test_handle_follow_sends_two_messages():
    """加好友事件應推播兩則歡迎訊息"""
    store, line = _make_deps()
    handle_follow("user_001", store, line)
    assert line.push.call_count == 2


def test_handle_message_idle_no_keyword_replies_help():
    """IDLE 狀態收到非關鍵字訊息，應回覆使用說明"""
    store, line = _make_deps(state="IDLE")
    handle_message("user_001", "今天天氣真好", store, line)
    line.reply.assert_called_once()
    args = line.reply.call_args[0]
    assert "說明" in args[1] or "監控" in args[1]


def test_handle_message_idle_keyword_triggers_claude():
    """IDLE 狀態收到監控關鍵字，應呼叫 Claude 解析"""
    store, line = _make_deps(state="IDLE")
    parsed = {
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": 64.86,
        "stop_loss_moving": 63.0, "target_stage_1": 75.0,
        "target_stage_2": None,
    }
    with patch("bot.handlers.parse_monitor_intent", return_value=parsed):
        handle_message("user_001", "監控弘憶 5 張均價 64.86", store, line)

    store.set_state.assert_called()
    line.reply.assert_called_once()


def test_handle_message_daily_limit_exceeded():
    """超過每日 Claude 呼叫上限時，應回覆限制說明，不呼叫 Claude"""
    store, line = _make_deps(state="IDLE", call_count=10)
    with patch("bot.handlers.parse_monitor_intent") as mock_parse:
        handle_message("user_001", "監控弘憶", store, line)
        mock_parse.assert_not_called()
    line.reply.assert_called_once()


def test_handle_message_confirming_yes_sets_monitoring():
    """CONFIRMING 狀態回覆「確認」應切換到 MONITORING"""
    config = {
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": 64.86,
        "stop_loss_moving": 63.0, "target_stage_1": 75.0,
        "target_stage_2": None,
    }
    store, line = _make_deps(state="CONFIRMING", config=config)
    handle_message("user_001", "確認", store, line)
    store.set_state.assert_called_with("user_001", "MONITORING")
    line.reply.assert_called_once()


def test_handle_message_monitoring_stop_sets_idle():
    """MONITORING 狀態收到「停止」應切換到 IDLE"""
    store, line = _make_deps(state="MONITORING")
    handle_message("user_001", "停止", store, line)
    store.set_state.assert_called_with("user_001", "IDLE")
    line.reply.assert_called_once()
