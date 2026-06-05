"""
test_claude_parser.py — claude_parser 模組單元測試
mock Anthropic SDK，不發出真實 API 請求
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from bot.claude_parser import parse_monitor_intent


def _mock_response(content: str):
    """建構 mock Anthropic API 回應"""
    mock = MagicMock()
    mock.content = [MagicMock(text=content)]
    return mock


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_parse_full_intent():
    """完整輸入應解析出所有欄位"""
    text = "我買了弘憶 5 張，均價 64.86，停損 63，目標 75"
    expected = {
        "stock_id": "3312",
        "stock_name": "弘憶",
        "total_shares": 5000,
        "cost_price": 64.86,
        "stop_loss_moving": 63.0,
        "target_stage_1": 75.0,
        "target_stage_2": None,
    }
    mock_json = json.dumps(expected)

    with patch("bot.claude_parser.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = _mock_response(mock_json)

        result = parse_monitor_intent(text)

    assert result["stock_id"] == "3312"
    assert result["total_shares"] == 5000
    assert result["cost_price"] == pytest.approx(64.86)
    assert result["stop_loss_moving"] == pytest.approx(63.0)
    assert result["target_stage_2"] is None


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_parse_partial_intent_returns_nulls():
    """不完整輸入，缺少欄位應回傳 null"""
    text = "監控弘憶"
    partial = {
        "stock_id": "3312",
        "stock_name": "弘憶",
        "total_shares": None,
        "cost_price": None,
        "stop_loss_moving": None,
        "target_stage_1": None,
        "target_stage_2": None,
    }

    with patch("bot.claude_parser.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = _mock_response(json.dumps(partial))

        result = parse_monitor_intent(text)

    assert result["total_shares"] is None
    assert result["cost_price"] is None


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_parse_returns_nulls_on_api_error():
    """API 錯誤時應回傳全 null 結果，不 raise"""
    with patch("bot.claude_parser.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = Exception("network error")

        result = parse_monitor_intent("監控弘憶")

    assert result["stock_id"] is None
    assert result["total_shares"] is None


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_parse_handles_invalid_json():
    """API 回傳非 JSON 時應回傳全 null 結果，不 raise"""
    with patch("bot.claude_parser.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = _mock_response("我無法解析這句話")

        result = parse_monitor_intent("亂說一通")

    assert result["stock_id"] is None
