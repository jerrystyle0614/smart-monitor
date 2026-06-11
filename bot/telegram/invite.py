"""
telegram/invite.py — 邀請碼管理
格式：SM + 4 位大寫英數字（例如 SM8K3F）
"""
import json
import random
import string
from pathlib import Path
from typing import Optional

INVITES_PATH = Path("data/invites.json")


def _load():
    # type: () -> dict
    if not INVITES_PATH.exists():
        return {}
    try:
        return json.loads(INVITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data):
    # type: (dict) -> None
    INVITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    INVITES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate_code():
    # type: () -> str
    """產生一個唯一的邀請碼（SM + 4 位大寫英數字）"""
    data = _load()
    while True:
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        code = "SM{}".format(suffix)
        if code not in data:
            return code


def verify_invite(code):
    # type: (str) -> Optional[str]
    """驗證邀請碼是否有效。有效回傳方案名稱，無效回傳 None。"""
    data = _load()
    entry = data.get(code)
    if not entry:
        return None
    if entry.get("used"):
        return None
    return entry.get("plan")


def bind_invite(code, chat_id):
    # type: (str, str) -> None
    """將邀請碼標為已使用並記錄 chat_id。"""
    data = _load()
    if code in data:
        data[code]["used"] = True
        data[code]["chat_id"] = chat_id
        _save(data)
