"""
server.py — FastAPI webhook server
接收 LINE 平台傳入的事件並路由到對應 handler
"""

import base64
import collections
import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

from bot.router import handle_follow, handle_message
from bot.line_client import LineClient
from bot.user_store import UserStore
from bot.data.fugle_client import FugleClient
from bot.monitor_engine import MonitorEngine
from bot.scheduler.manager import SchedulerManager
from bot.scheduler.jobs import ScheduledJobs
from notifier import DiscordNotifier
import logging

logger = logging.getLogger(__name__)

# LINE webhook retry 去重：記錄最近 200 個已處理的 message id
_seen_message_ids = collections.deque(maxlen=200)


# 在 lifespan 之前初始化，確保 lifespan 函式可直接引用
_store = UserStore()
_line = LineClient()
_engine = None  # 由 lifespan 啟動後賦值


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    # 從 Fugle 載入完整股票對照表
    try:
        client = FugleClient()
        client.load_stock_map()
        logger.info("[startup] Stock map loaded")
    except Exception as e:
        logger.error("[startup] Stock map load failed: {}".format(e))

    # 啟動監控引擎
    discord = DiscordNotifier()
    _engine = MonitorEngine(_store, _line, discord)
    _engine.start()

    # 初始化並啟動排程
    try:
        scheduled_jobs = ScheduledJobs(
            user_store=_store,
            line_client=_line,
            stock_picker_engine=None,  # 稍後由 Phase B 初始化
        )
        scheduler_manager = SchedulerManager()
        scheduler_manager.start(scheduled_jobs)
        app.state.scheduler_manager = scheduler_manager
        logger.info("[startup] Scheduler manager initialized and started")
    except Exception as e:
        logger.error("[startup] Scheduler initialization failed: {}".format(e))

    yield

    # 關閉排程
    if hasattr(app.state, 'scheduler_manager'):
        scheduler_manager = app.state.scheduler_manager
        if scheduler_manager.is_running:
            scheduler_manager.stop()
            logger.info("[shutdown] Scheduler manager stopped")

    # 關閉監控引擎
    if _engine:
        _engine.stop()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """捕捉所有未處理例外，記錄 log、推播 Discord，並回傳 500，避免 process crash。"""
    import asyncio
    import traceback
    from fastapi.responses import JSONResponse

    tb = traceback.format_exc()
    logger.error("[server] Unhandled exception on {}: {}".format(request.url.path, exc), exc_info=True)

    # 截斷 traceback 避免超過 Discord embed 4096 字元上限
    max_len = 3800
    tb_display = tb if len(tb) <= max_len else tb[:max_len] + "\n…（已截斷）"

    msg = (
        "**路徑：** `{}`\n"
        "**錯誤：** `{}`\n\n"
        "```\n{}\n```"
    ).format(request.url.path, exc, tb_display)

    notifier = DiscordNotifier()
    await asyncio.to_thread(notifier.send, "🚨 Server Error 500", msg, 0xE74C3C)

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
        if not user_id:
            continue

        if event_type == "follow":
            handle_follow(user_id, _store, _line)

        elif event_type == "message":
            msg = event.get("message", {})

            # 去重：同一個 message id 只處理一次，防止 LINE retry 重複觸發
            message_id = msg.get("id", "")
            if message_id and message_id in _seen_message_ids:
                logger.warning("[webhook] 略過重複 message_id={}".format(message_id))
                continue
            if message_id:
                _seen_message_ids.append(message_id)

            # 收到訊息立即標為已讀（涵蓋所有訊息類型，含貼圖/圖片），
            # 讓使用者送出後馬上看到「已讀」，不必等 AI 分析完成
            _line.mark_as_read(msg.get("markAsReadToken", ""))

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
