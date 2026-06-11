"""
telegram/webhook.py — Telegram Webhook 路由
處理 Telegram Update 事件：/start 邀請碼驗證、訊息、CallbackQuery
"""
import logging
from fastapi import Request

from bot.router import handle_message
from bot.telegram.invite import verify_invite, bind_invite

logger = logging.getLogger(__name__)

# 等待邀請碼輸入的 chat_id 集合
_pending_invite = set()  # type: set


def register(app, store, tg_client):
    """將 Telegram webhook 路由掛載到 FastAPI app"""

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request):
        try:
            update = await request.json()
        except Exception:
            return {"ok": False}

        # --- Message（文字訊息）---
        message = update.get("message")
        if message:
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "")
            message_id = str(message.get("message_id", ""))
            if not chat_id or not text:
                return {"ok": True}

            reply_token = "msg:{}:{}".format(chat_id, message_id)
            logger.info("[telegram] chat_id={} text={!r}".format(chat_id, text))

            # /start 指令
            if text.startswith("/start"):
                plan = store.get_plan(chat_id)
                if plan and plan != "free":
                    tg_client.send_menu(chat_id)
                else:
                    _pending_invite.add(chat_id)
                    tg_client.push(chat_id, "👋 歡迎使用 Smart 股市助理！\n\n請輸入邀請碼以啟用服務：")
                return {"ok": True}

            # 等待邀請碼輸入
            if chat_id in _pending_invite:
                code = text.strip().upper()
                plan = verify_invite(code)
                if plan:
                    bind_invite(code, chat_id)
                    store.set_plan(chat_id, plan)
                    _pending_invite.discard(chat_id)
                    tg_client.push(chat_id,
                        "✅ 邀請碼驗證成功！歡迎加入 Smart 股市助理。"
                    )
                    tg_client.send_menu(chat_id)
                else:
                    tg_client.push(chat_id, "❌ 邀請碼錯誤或已使用，請重新輸入：")
                return {"ok": True}

            # 一般訊息 → 路由
            handle_message(chat_id, text, store, tg_client, reply_token)
            return {"ok": True}

        # --- CallbackQuery（按鈕點擊）---
        callback_query = update.get("callback_query")
        if callback_query:
            query_id = callback_query.get("id", "")
            chat_id = str(callback_query.get("from", {}).get("id", ""))
            data = callback_query.get("data", "")
            if not chat_id or not data:
                return {"ok": True}

            reply_token = "cbq:{}:{}".format(query_id, chat_id)
            logger.info("[telegram] callback chat_id={} data={!r}".format(chat_id, data))
            handle_message(chat_id, data, store, tg_client, reply_token)
            return {"ok": True}

        return {"ok": True}
