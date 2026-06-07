"""
server.py — FastAPI webhook server
接收 LINE 平台傳入的事件並路由到對應 handler
"""

import base64
import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

from bot.router import handle_follow, handle_message
from bot.line_client import LineClient
from bot.user_store import UserStore
from bot.data.fugle_client import FugleClient
from bot.monitor_engine import MonitorEngine
from notifier import DiscordNotifier


def _clear_user_data():
    """清空所有使用者資料。僅在 CLEAR_ON_START=1 時執行，用於測試環境。"""
    if os.environ.get("CLEAR_ON_START") != "1":
        return
    users_dir = Path("users")
    if users_dir.exists():
        shutil.rmtree(users_dir)
    users_dir.mkdir()
    print("[server] 使用者資料已清空（測試模式）")


# 在 lifespan 之前初始化，確保 lifespan 函式可直接引用
_store = UserStore()
_line = LineClient()
_engine = None  # 由 lifespan 啟動後賦值


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    _clear_user_data()
    # 從 Fugle 載入完整股票對照表
    try:
        client = FugleClient()
        client.load_stock_map()
        print("[startup] Stock map loaded")
    except Exception as e:
        print("[startup] Stock map load failed: {}".format(e))
    discord = DiscordNotifier()
    _engine = MonitorEngine(_store, _line, discord)
    _engine.start()
    yield
    if _engine:
        _engine.stop()


app = FastAPI(lifespan=lifespan)


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


@app.post("/webhook")
async def webhook(request: Request):
    """接收 LINE 平台 webhook 事件，驗證簽章後分發給各 handler"""
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    # 簽章驗證失敗時回傳 400，防止非法請求進入業務邏輯
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(body)
    for event in payload.get("events", []):
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        # 沒有 userId 的事件（例如群組未加好友）直接略過
        if not user_id:
            continue

        if event_type == "follow":
            # 使用者加好友事件
            handle_follow(user_id, _store, _line)

        elif event_type == "message":
            msg = event.get("message", {})
            # 只處理文字訊息，圖片/貼圖等一律略過
            if msg.get("type") != "text":
                continue
            text = msg.get("text", "")
            reply_token = event.get("replyToken", "")
            handle_message(user_id, text, _store, _line, reply_token)

    return {"status": "ok"}


@app.get("/health")
async def health():
    """健康檢查端點，供負載平衡或監控服務確認服務存活"""
    return {"status": "ok"}
