"""test_scheduler.py — 排程管理器測試"""
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test_token")

from bot.scheduler.manager import SchedulerManager
from bot.scheduler.config import ScheduledJob, SCHEDULED_JOBS


class TestScheduledJob:
    """ScheduledJob 定義測試"""

    def test_scheduled_job_creation(self):
        """驗證排程任務可以創建"""
        job = ScheduledJob(
            name="test_job",
            hour=8,
            minute=30,
            func=lambda: print("test"),
            description="Test job"
        )
        assert job.name == "test_job"
        assert job.hour == 8
        assert job.minute == 30

    def test_scheduled_job_with_defaults(self):
        """驗證排程任務可以使用預設值"""
        job = ScheduledJob(
            name="test_job",
            hour=8,
            minute=30
        )
        assert job.args == ()
        assert job.kwargs == {}
        assert job.func is None

    def test_scheduled_job_with_args_kwargs(self):
        """驗證排程任務支援參數"""
        def test_func(a, b, c=None):
            return a + b

        job = ScheduledJob(
            name="test_job",
            hour=8,
            minute=30,
            func=test_func,
            args=(1, 2),
            kwargs={"c": 3}
        )
        assert job.args == (1, 2)
        assert job.kwargs == {"c": 3}
        assert job.func is not None


class TestSchedulerManager:
    """SchedulerManager 初始化測試"""

    def test_scheduler_initialization(self):
        """驗證排程管理器可以初始化"""
        manager = SchedulerManager()
        assert manager is not None
        assert manager.is_running is False
        assert manager.scheduled_jobs is None


# 更多測試將在後續步驟中添加
