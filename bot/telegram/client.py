"""
telegram/client.py — Telegram Bot API 推播/回覆封裝
介面與 bot/line/client.py 的 LineClient 保持一致（push / reply）
使用 requests 直接呼叫 Bot API（同步），避免引入 async 複雜度
"""
import os
import requests
from typing import Optional
from bot.telegram.keyboard import (
    main_menu_keyboard, cancel_keyboard,
    skip_cancel_keyboard, confirm_cancel_keyboard,
    to_inline_markup,
)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _auto_keyboard(text):
    # type: (str) -> dict
    """根據訊息內容自動選擇對應的 inline keyboard，沒有則回傳空 dict"""
    if "📊 Smart 助理" in text:
        return to_inline_markup(main_menu_keyboard())
    if "輸入「確認」" in text or "輸入「確認」" in text:
        return to_inline_markup(confirm_cancel_keyboard())
    if "輸入『跳過』略過" in text:
        return to_inline_markup(skip_cancel_keyboard())
    if "輸入『取消』回主選單" in text:
        return to_inline_markup(cancel_keyboard())
    return {}


class TelegramClient:
    def __init__(self, token=None):
        # type: (Optional[str]) -> None
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def _url(self, method):
        # type: (str) -> str
        return _BASE.format(token=self._token, method=method)

    def _post(self, method, payload):
        # type: (str, dict) -> None
        try:
            resp = requests.post(self._url(method), json=payload, timeout=10)
            if resp.status_code not in (200, 201):
                print("[警告] Telegram {} 失敗：{} {}".format(
                    method, resp.status_code, resp.text[:100]
                ))
        except Exception as e:
            print("[警告] Telegram {} 失敗：{}".format(method, e))

    def push(self, chat_id, text):
        # type: (str, str) -> None
        """主動推播訊息給使用者"""
        payload = {"chat_id": chat_id, "text": text}
        kb = _auto_keyboard(text)
        if kb:
            payload["reply_markup"] = kb
        self._post("sendMessage", payload)

    def reply(self, token, text):
        # type: (str, str) -> None
        """回覆訊息。token 格式：
        - callback_query → 'cbq:{callback_query_id}:{chat_id}'
        - message → 'msg:{chat_id}:{message_id}'
        """
        parts = token.split(":", 2)
        kind = parts[0] if parts else "msg"

        if kind == "cbq" and len(parts) == 3:
            self._post("answerCallbackQuery", {"callback_query_id": parts[1]})
            chat_id = parts[2]
        else:
            chat_id = parts[1] if len(parts) >= 2 else token

        payload = {"chat_id": chat_id, "text": text}
        kb = _auto_keyboard(text)
        if kb:
            payload["reply_markup"] = kb
        self._post("sendMessage", payload)

    def send_menu(self, chat_id):
        # type: (str) -> None
        """發送附 Inline Keyboard 的主選單"""
        self._post("sendMessage", {
            "chat_id": chat_id,
            "text": "📊 Smart Monitor 服務選單\n\n請選擇服務：",
            "reply_markup": to_inline_markup(main_menu_keyboard()),
        })

    def send_with_cancel(self, chat_id, text):
        # type: (str, str) -> None
        """發送附取消按鈕的訊息（問答中使用）"""
        self._post("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": to_inline_markup(cancel_keyboard()),
        })
