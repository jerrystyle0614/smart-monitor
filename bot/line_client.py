"""
line_client.py — LINE Messaging API 推播/回覆封裝
封裝 push 和 reply 兩種傳訊方式，供 handlers.py 呼叫
"""

import os
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    PushMessageRequest, ReplyMessageRequest,
    MarkMessagesAsReadByTokenRequest,
    TextMessage,
)


class LineClient:
    def __init__(self):
        # 從環境變數讀取 LINE Channel Access Token
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        config = Configuration(access_token=token)
        self._api = MessagingApi(ApiClient(config))

    def push(self, user_id: str, text: str) -> None:
        """主動推播訊息給使用者（不需 reply_token）"""
        try:
            self._api.push_message(PushMessageRequest(
                to=user_id,
                messages=[TextMessage(type="text", text=text)],
            ))
        except Exception as e:
            print(f"[警告] LINE push 失敗：{e}")

    def reply(self, reply_token: str, text: str) -> None:
        """回覆使用者訊息（需 reply_token，僅在 30 秒內有效）"""
        try:
            self._api.reply_message(ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(type="text", text=text)],
            ))
        except Exception as e:
            print(f"[警告] LINE reply 失敗：{e}")

    def mark_as_read(self, mark_as_read_token: str) -> None:
        """
        將使用者訊息標為已讀（需官方帳號開啟「聊天」功能）。
        token 來自 webhook message event 的 markAsReadToken 欄位，
        會將該訊息以前的所有訊息一併標為已讀。
        失敗只印警告，不影響主流程。
        """
        if not mark_as_read_token:
            return
        try:
            self._api.mark_messages_as_read_by_token(
                MarkMessagesAsReadByTokenRequest(
                    mark_as_read_token=mark_as_read_token
                )
            )
        except Exception as e:
            print(f"[警告] LINE mark_as_read 失敗：{e}")
