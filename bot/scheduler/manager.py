"""
manager.py — 排程管理器
控制 APScheduler 的啟動、停止、任務註冊
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    BackgroundScheduler = None
    CronTrigger = None

from bot.scheduler.config import SCHEDULED_JOBS, ENABLE_SCHEDULER

logger = logging.getLogger(__name__)


class SchedulerManager:
    """排程管理器"""

    def __init__(self):
        self.scheduler = None
        if BackgroundScheduler:
            self.scheduler = BackgroundScheduler(timezone="Asia/Taipei")
        self.scheduled_jobs = None
        self.is_running = False

    def start(self, scheduled_jobs) -> None:
        """啟動排程"""
        if not ENABLE_SCHEDULER:
            logger.info("[scheduler] 排程已禁用 (ENABLE_SCHEDULER=False)")
            return

        if self.is_running:
            logger.warning("[scheduler] 排程已在運行")
            return

        if not self.scheduler:
            logger.error("[scheduler] APScheduler 未安裝")
            return

        self.scheduled_jobs = scheduled_jobs

        # 註冊所有任務
        self._register_jobs()

        # 啟動排程
        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("[scheduler] 排程已啟動")
        except Exception as e:
            logger.error(f"[scheduler] 啟動失敗: {e}")
            raise

    def stop(self) -> None:
        """停止排程"""
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("[scheduler] 排程已停止")
        except Exception as e:
            logger.error(f"[scheduler] 停止失敗: {e}")

    def _register_jobs(self) -> None:
        """註冊排程任務"""
        if not self.scheduler or not self.scheduled_jobs:
            return

        for job_config in SCHEDULED_JOBS:
            try:
                # 根據任務名稱取得對應的函數
                func = self._get_job_function(job_config.name)
                if not func:
                    logger.warning(f"[scheduler] 任務 {job_config.name} 的函數未找到")
                    continue

                # 建立 cron trigger
                trigger = CronTrigger(
                    hour=job_config.hour,
                    minute=job_config.minute,
                    timezone="Asia/Taipei"
                )

                # 新增任務到排程
                self.scheduler.add_job(
                    func=func,
                    trigger=trigger,
                    id=job_config.name,
                    name=job_config.description,
                )
                logger.info(f"[scheduler] 已註冊任務: {job_config.name} (每日 {job_config.hour:02d}:{job_config.minute:02d})")

            except Exception as e:
                logger.error(f"[scheduler] 註冊任務 {job_config.name} 失敗: {e}")

    def _get_job_function(self, job_name: str):
        """根據任務名稱取得對應函數"""
        if not self.scheduled_jobs:
            return None

        mapping = {
            "stock_picker_daily": getattr(self.scheduled_jobs, "stock_picker_daily", None),
            "pre_market_analysis": getattr(self.scheduled_jobs, "pre_market_analysis", None),
            "post_market_analysis": getattr(self.scheduled_jobs, "post_market_analysis", None),
        }
        return mapping.get(job_name)

    def get_jobs(self) -> list:
        """取得當前註冊的任務列表"""
        if not self.scheduler:
            return []
        return self.scheduler.get_jobs()
