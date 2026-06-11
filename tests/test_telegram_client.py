"""test_telegram_client.py — TelegramClient 單元測試"""
import pytest
from unittest.mock import MagicMock, patch


def test_telegram_client_push_calls_send_message():
    """push() 應呼叫 Telegram sendMessage API"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.push("123456789", "hello")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "sendMessage" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "123456789"
        assert call_args[1]["json"]["text"] == "hello"


def test_telegram_client_push_silent_on_error():
    """push() 失敗時只印警告，不 raise"""
    with patch("bot.telegram.client.requests.post", side_effect=Exception("net error")):
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.push("123456789", "hello")  # 不應 raise


def test_telegram_client_reply_with_message_id():
    """reply(msg:chat_id:message_id, text) 應呼叫 sendMessage"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.reply("msg:123456789:999", "pong")
        mock_post.assert_called_once()
        assert "sendMessage" in mock_post.call_args[0][0]


def test_telegram_client_send_menu_includes_keyboard():
    """send_menu() 應發送含 inline_keyboard 的訊息"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.send_menu("123456789")
        call_json = mock_post.call_args[1]["json"]
        assert "reply_markup" in call_json
        assert "inline_keyboard" in call_json["reply_markup"]
