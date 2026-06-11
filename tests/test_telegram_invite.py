"""test_telegram_invite.py — 邀請碼系統單元測試"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_generate_invite_code_format():
    """產生的邀請碼格式應為 SM + 4 位大寫英數字"""
    from bot.telegram.invite import generate_code
    code = generate_code()
    assert code.startswith("SM")
    assert len(code) == 6
    assert code[2:].isalnum()


def test_verify_invite_valid(tmp_path):
    """有效且未使用的邀請碼應通過驗證，回傳方案名稱"""
    from bot.telegram.invite import verify_invite
    invites = {"SM8K3F": {"plan": "pro", "used": False, "chat_id": None}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SM8K3F")
    assert result == "pro"


def test_verify_invite_already_used(tmp_path):
    """已使用的邀請碼應回傳 None"""
    from bot.telegram.invite import verify_invite
    invites = {"SMABC1": {"plan": "basic", "used": True, "chat_id": "999"}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SMABC1")
    assert result is None


def test_verify_invite_invalid_code(tmp_path):
    """不存在的邀請碼應回傳 None"""
    from bot.telegram.invite import verify_invite
    inv_path = tmp_path / "invites.json"
    inv_path.write_text("{}")
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SMXXXX")
    assert result is None


def test_bind_invite_marks_used(tmp_path):
    """bind_invite 應將邀請碼標為 used 並記錄 chat_id"""
    from bot.telegram.invite import bind_invite
    invites = {"SM8K3F": {"plan": "pro", "used": False, "chat_id": None}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        bind_invite("SM8K3F", "123456789")
        data = json.loads(inv_path.read_text())
    assert data["SM8K3F"]["used"] is True
    assert data["SM8K3F"]["chat_id"] == "123456789"
