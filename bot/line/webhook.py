"""
line/webhook.py — LINE Webhook 路由
處理 LINE 平台傳入事件：簽章驗證、訊息去重、分發至 router
"""

import base64
import collections
import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from bot.router import handle_follow, handle_message

logger = logging.getLogger(__name__)

router = APIRouter()

# LINE webhook retry 去重：記錄最近 200 個已處理的 message id
_seen_message_ids = collections.deque(maxlen=200)


def _verify_signature(body: bytes, signature: str) -> bool:
    """驗證 LINE webhook 簽章，防止偽造請求"""
    secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    return hmac.compare_digest(
        base64.b64encode(expected).decode(),
        signature,
    )


def register(app, store, line_client):
    """將 LINE webhook 路由掛載到 FastAPI app"""

    @app.post("/webhook")
    async def webhook(request: Request):
        """接收 LINE 平台 webhook 事件，驗證簽章後分發給各 handler"""
        signature = request.headers.get("X-Line-Signature", "")
        body = await request.body()

        if not _verify_signature(body, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        payload = json.loads(body)
        for event in payload.get("events", []):
            event_type = event.get("type")
            source = event.get("source", {})
            user_id = source.get("userId")
            if not user_id:
                continue

            if event_type == "follow":
                handle_follow(user_id, store, line_client)

            elif event_type == "message":
                msg = event.get("message", {})

                message_id = msg.get("id", "")
                if message_id and message_id in _seen_message_ids:
                    logger.warning("[line] 略過重複 message_id={}".format(message_id))
                    continue
                if message_id:
                    _seen_message_ids.append(message_id)

                line_client.mark_as_read(msg.get("markAsReadToken", ""))

                if msg.get("type") != "text":
                    continue

                text = msg.get("text", "")
                reply_token = event.get("replyToken", "")
                logger.info("[line] uid={} text={!r}".format(user_id, text))
                handle_message(user_id, text, store, line_client, reply_token)

        return {"status": "ok"}
