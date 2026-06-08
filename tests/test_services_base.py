"""test_services_base.py — ScriptedService 基底測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.services.base import Step, ScriptedService


def validate_digit(text):
    """驗證數字"""
    if not text.isdigit():
        return (False, None, "請輸入數字")
    return (True, int(text), "")


class MockService(ScriptedService):
    """測試用服務"""
    def __init__(self):
        self.name = "mock"
        self.steps = [
            Step(
                field="field1",
                question="問題 1？",
                validate=validate_digit,
                optional=False
            ),
            Step(
                field="field2",
                question="問題 2？",
                validate=validate_digit,
                optional=True
            ),
            Step(
                field="field3",
                question="問題 3？",
                validate=validate_digit,
                optional=False
            ),
        ]
        self.on_complete_called = False
        self.on_complete_draft = None

    def on_complete(self, uid, draft, store, line, reply_token=""):
        """覆蓋完成邏輯"""
        self.on_complete_called = True
        self.on_complete_draft = draft


@pytest.fixture
def service():
    return MockService()


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def mock_line():
    return MagicMock()


def test_start_shows_first_question(service, mock_store, mock_line):
    """start() 應顯示第一題"""
    service.start("U123", mock_store, mock_line)
    mock_store.set_service_state.assert_called()
    mock_line.reply.assert_called()
    # _show_step 以 reply(reply_token, prompt) 呼叫，問題文字在第二個位置參數
    call_args = mock_line.reply.call_args[0][1]
    assert "問題 1" in call_args


def test_handle_input_cancel(service, mock_store, mock_line):
    """「取消」應回傳 CANCEL"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 0
    mock_store.get_draft.return_value = {}
    result = service.handle_input("U123", "取消", mock_store, mock_line)
    assert result == "CANCEL"


def test_handle_input_validation_fail_reasks(service, mock_store, mock_line):
    """驗證失敗應重問"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 0
    mock_store.get_draft.return_value = {}
    result = service.handle_input("U123", "not_a_number", mock_store, mock_line)
    assert result == "CONTINUE"
    # 應顯示錯誤訊息
    calls = mock_line.reply.call_args_list
    assert any("請輸入數字" in str(call) for call in calls)


def test_handle_input_validation_pass_advances(service, mock_store, mock_line):
    """驗證通過應前進"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 0
    mock_store.get_draft.return_value = {}
    result = service.handle_input("U123", "123", mock_store, mock_line)
    assert result == "CONTINUE"
    # draft 應被更新
    calls = mock_store.set_service_state.call_args_list
    assert any("field1" in str(call) for call in calls)


def test_handle_input_skip_optional(service, mock_store, mock_line):
    """「跳過」選填欄位應前進，記 None"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 1  # 第二題（選填）
    mock_store.get_draft.return_value = {"field1": 123}
    result = service.handle_input("U123", "跳過", mock_store, mock_line)
    # 應前進，但由於有 3 題，所以是 CONTINUE
    assert result == "CONTINUE"
    # draft 應包含 field2: None
    calls = mock_store.set_service_state.call_args_list
    assert any("field2" in str(call) for call in calls)


def test_handle_input_skip_required_reasks(service, mock_store, mock_line):
    """「跳過」必填欄位應重問"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 0  # 第一題（必填）
    mock_store.get_draft.return_value = {}
    result = service.handle_input("U123", "跳過", mock_store, mock_line)
    assert result == "CONTINUE"
    # 應顯示錯誤
    calls = mock_line.reply.call_args_list
    assert any("無法" in str(call) or "必填" in str(call) for call in calls)


def test_handle_input_last_step_calls_on_complete(service, mock_store, mock_line):
    """最後一題完成後應呼叫 on_complete()"""
    mock_store.get_current_service.return_value = "mock"
    mock_store.get_current_step.return_value = 2  # 最後一題（第三題）
    mock_store.get_draft.return_value = {"field1": 123, "field2": None}
    result = service.handle_input("U123", "456", mock_store, mock_line)
    assert result == "DONE"
    assert service.on_complete_called == True
    assert service.on_complete_draft is not None
