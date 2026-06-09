"""test_line_client.py — LineClient 測試（聚焦 mark_as_read）"""
import os
from unittest.mock import MagicMock

os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test_token")

from bot.line_client import LineClient
from linebot.v3.messaging import MarkMessagesAsReadByTokenRequest


def _client_with_mock_api():
    """建立 LineClient 並以 MagicMock 取代底層 SDK，避免真打網路"""
    client = LineClient()
    client._api = MagicMock()
    return client


def test_mark_as_read_calls_api_with_token():
    """有 token 時應呼叫 SDK，並帶入正確的 markAsReadToken"""
    client = _client_with_mock_api()

    client.mark_as_read("TOKEN_ABC")

    client._api.mark_messages_as_read_by_token.assert_called_once()
    req = client._api.mark_messages_as_read_by_token.call_args[0][0]
    assert isinstance(req, MarkMessagesAsReadByTokenRequest)
    # 序列化後欄位名為 markAsReadToken
    assert req.to_dict()["markAsReadToken"] == "TOKEN_ABC"


def test_mark_as_read_skips_empty_token():
    """空 token 應直接略過，不呼叫 SDK"""
    client = _client_with_mock_api()

    client.mark_as_read("")

    client._api.mark_messages_as_read_by_token.assert_not_called()


def test_mark_as_read_swallows_errors():
    """SDK 拋出例外時不應往外拋（已讀失敗不影響主流程）"""
    client = _client_with_mock_api()
    client._api.mark_messages_as_read_by_token.side_effect = Exception("API down")

    # 不應拋出例外
    client.mark_as_read("TOKEN_ABC")
