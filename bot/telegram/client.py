"""
telegram/client.py — Telegram Bot API 推播/回覆封裝
介面與 bot/line/client.py 的 LineClient 保持一致（push / reply）
使用 requests 直接呼叫 Bot API（同步），避免引入 async 複雜度
"""
import os
import requests
from typing import Optional
from bot.telegram.keyboard import main_menu_keyboard, to_inline_markup, cancel_keyboard

_BASE = "https://api.telegram.org/bot{token}/{method}"


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
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

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
            payload = {"chat_id": parts[2], "text": text}
            if text.startswith("📊"):
                payload["reply_markup"] = to_inline_markup(main_menu_keyboard())
            self._post("sendMessage", payload)
        else:
            chat_id = parts[1] if len(parts) >= 2 else token
            self._post("sendMessage", {"chat_id": chat_id, "text": text})

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
