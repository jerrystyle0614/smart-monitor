"""
server.py — FastAPI app 主體
負責 lifespan 管理、全域例外處理、health endpoint
LINE webhook 路由由 bot/line/webhook.py 掛載
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from bot.line.client import LineClient
from bot.line import webhook as line_webhook
from bot.user_store import UserStore
from bot.data.fugle_client import FugleClient
from bot.monitor_engine import MonitorEngine
from bot.scheduler.manager import SchedulerManager
from bot.scheduler.jobs import ScheduledJobs
from notifier import DiscordNotifier

logger = logging.getLogger(__name__)

_line_store = UserStore(platform="line")
_line = LineClient()
_store = _line_store  # backward compat alias
_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine

    try:
        client = FugleClient()
        client.load_stock_map()
        logger.info("[startup] Stock map loaded")
    except Exception as e:
        logger.error("[startup] Stock map load failed: {}".format(e))

    discord = DiscordNotifier()
    _engine = MonitorEngine(
        stores={"line": _line_store},
        clients={"line": _line},
        discord=discord,
    )
    _engine.start()

    try:
        scheduled_jobs = ScheduledJobs(
            user_store=_store,
            line_client=_line,
            stock_picker_engine=None,
        )
        scheduler_manager = SchedulerManager()
        scheduler_manager.start(scheduled_jobs)
        app.state.scheduler_manager = scheduler_manager
        logger.info("[startup] Scheduler manager initialized and started")
    except Exception as e:
        logger.error("[startup] Scheduler initialization failed: {}".format(e))

    yield

    if hasattr(app.state, 'scheduler_manager'):
        scheduler_manager = app.state.scheduler_manager
        if scheduler_manager.is_running:
            scheduler_manager.stop()
            logger.info("[shutdown] Scheduler manager stopped")

    if _engine:
        _engine.stop()


app = FastAPI(lifespan=lifespan)

# 掛載 LINE webhook 路由
line_webhook.register(app, _store, _line)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """捕捉所有未處理例外，記錄 log、推播 Discord，並回傳 500"""
    import asyncio
    import traceback
    from fastapi.responses import JSONResponse

    tb = traceback.format_exc()
    logger.error("[server] Unhandled exception on {}: {}".format(request.url.path, exc), exc_info=True)

    max_len = 3800
    tb_display = tb if len(tb) <= max_len else tb[:max_len] + "\n…（已截斷）"

    msg = (
        "**路徑：** `{}`\n"
        "**錯誤：** `{}`\n\n"
        "```\n{}\n```"
    ).format(request.url.path, exc, tb_display)

    error_webhook = os.environ.get("DISCORD_ERROR_WEBHOOK_URL")
    if error_webhook:
        notifier = DiscordNotifier(webhook_url=error_webhook)
        await asyncio.to_thread(notifier.send, "🚨 Server Error 500", msg, 0xE74C3C)

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "ok"}
