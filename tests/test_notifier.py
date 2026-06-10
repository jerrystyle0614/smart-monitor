"""test_notifier.py — DiscordNotifier 測試（聚焦 webhook 優先序）"""
import os
from unittest.mock import patch

from notifier import DiscordNotifier


def test_explicit_webhook_takes_precedence_over_env():
    """明確傳入的 webhook_url（如 error 頻道）應優先於環境變數，不被覆蓋"""
    with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://general/hook"}):
        n = DiscordNotifier(webhook_url="https://error/hook")
    assert n.webhook_url == "https://error/hook"
    assert n.enabled is True


def test_falls_back_to_env_when_no_arg():
    """未指定 webhook_url 時退回環境變數（一般頻道）"""
    with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://general/hook"}):
        n = DiscordNotifier()
    assert n.webhook_url == "https://general/hook"


def test_disabled_when_no_webhook_anywhere():
    """既無傳入也無環境變數時，enabled 為 False（改印終端機）"""
    with patch.dict(os.environ, {}, clear=True):
        n = DiscordNotifier()
    assert n.webhook_url is None
    assert n.enabled is False
