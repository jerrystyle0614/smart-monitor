"""test_telegram_webhook.py — Telegram Webhook Handler 單元測試"""
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_app(store, tg_client):
    app = FastAPI()
    from bot.telegram.webhook import register
    register(app, store, tg_client)
    return app


def test_webhook_text_message_routes_to_handle_message():
    """文字訊息應呼叫 router 的 handle_message"""
    store = MagicMock()
    store.get_plan.return_value = "pro"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 123456789, "is_bot": False, "first_name": "Jerry"},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1700000000,
            "text": "1",
        }
    }
    with patch("bot.telegram.webhook.handle_message") as mock_handle:
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    mock_handle.assert_called_once()
    call_args = mock_handle.call_args[0]
    assert call_args[0] == "123456789"
    assert call_args[1] == "1"


def test_webhook_start_command_unregistered_asks_invite():
    """/start 對未啟用使用者應回覆邀請碼提示"""
    store = MagicMock()
    store.get_plan.return_value = "free"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 2,
        "message": {
            "message_id": 101,
            "from": {"id": 999, "is_bot": False, "first_name": "New"},
            "chat": {"id": 999, "type": "private"},
            "date": 1700000000,
            "text": "/start",
        }
    }
    with patch("bot.telegram.webhook.verify_invite", return_value=None):
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    tg_client.push.assert_called_once()
    assert "邀請碼" in tg_client.push.call_args[0][1]


def test_webhook_callback_query_routes_to_handle_message():
    """Callback query 應呼叫 router 的 handle_message"""
    store = MagicMock()
    store.get_plan.return_value = "pro"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 3,
        "callback_query": {
            "id": "abc123",
            "from": {"id": 123456789, "is_bot": False, "first_name": "Jerry"},
            "message": {
                "message_id": 200,
                "chat": {"id": 123456789, "type": "private"},
                "date": 1700000000,
                "text": "選單",
            },
            "data": "2",
        }
    }
    with patch("bot.telegram.webhook.handle_message") as mock_handle:
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    mock_handle.assert_called_once()
    call_args = mock_handle.call_args[0]
    assert call_args[0] == "123456789"
    assert call_args[1] == "2"
