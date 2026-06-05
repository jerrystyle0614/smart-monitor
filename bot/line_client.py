"""
line_client.py — LINE Messaging API 推播/回覆封裝
封裝 push 和 reply 兩種傳訊方式，供 handlers.py 呼叫
"""

import os
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    PushMessageRequest, ReplyMessageRequest,
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
