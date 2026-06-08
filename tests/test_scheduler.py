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

    def test_manager_start_stop(self):
        """驗證管理器可以啟動和停止"""
        mock_jobs = MagicMock(spec=ScheduledJobs)
        mock_jobs.stock_picker_daily = MagicMock()

        manager = SchedulerManager()

        # 啟動
        manager.start(mock_jobs)
        assert manager.is_running is True

        # 停止
        manager.stop()
        assert manager.is_running is False

    def test_manager_registers_jobs(self):
        """驗證管理器註冊所有任務"""
        mock_jobs = MagicMock(spec=ScheduledJobs)
        mock_jobs.stock_picker_daily = MagicMock()

        manager = SchedulerManager()
        manager.start(mock_jobs)

        jobs = manager.get_jobs()
        # 應該有至少 1 個任務被註冊
        assert len(jobs) >= 1

        manager.stop()

    def test_manager_disabled_with_flag(self):
        """ENABLE_SCHEDULER=False 時不啟動"""
        with patch("bot.scheduler.manager.ENABLE_SCHEDULER", False):
            mock_jobs = MagicMock(spec=ScheduledJobs)
            manager = SchedulerManager()
            manager.start(mock_jobs)

            # 應該不啟動
            assert manager.is_running is False

    def test_get_jobs_empty(self):
        """未啟動排程時 get_jobs 返回空列表"""
        manager = SchedulerManager()
        jobs = manager.get_jobs()
        assert isinstance(jobs, list)
        assert len(jobs) == 0

    def test_manager_stop_without_start(self):
        """在未啟動的情況下呼叫 stop 應安全完成"""
        manager = SchedulerManager()
        manager.stop()  # 應不拋出異常
        assert manager.is_running is False

    def test_manager_start_twice_ignored(self):
        """重複啟動應被忽略並記錄警告"""
        mock_jobs = MagicMock(spec=ScheduledJobs)
        mock_jobs.stock_picker_daily = MagicMock()

        manager = SchedulerManager()
        manager.start(mock_jobs)

        # 再次啟動應被忽略
        manager.start(mock_jobs)
        assert manager.is_running is True

        manager.stop()


from bot.scheduler.jobs import ScheduledJobs


class TestScheduledJobs:
    """排程任務測試（選股；盤前/盤後已移至 MonitorEngine）"""

    def test_stock_picker_daily_no_stocks(self):
        """無推薦股票時，任務應安全完成"""
        mock_engine = MagicMock()
        mock_engine.scan.return_value = []

        jobs = ScheduledJobs(stock_picker_engine=mock_engine)
        result = jobs.stock_picker_daily()

        assert result["stocks_found"] == 0
        assert result["users_notified"] == 0

    def test_stock_picker_daily_with_stocks(self):
        """有推薦股票時，應推播給所有用戶"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001", "U002"]

        # 模擬推薦股票物件
        mock_stock1 = MagicMock()
        mock_stock1.stock_id = "2330"
        mock_stock1.stock_name = "台積電"

        mock_stock2 = MagicMock()
        mock_stock2.stock_id = "2454"
        mock_stock2.stock_name = "聯發科"

        mock_engine = MagicMock()
        mock_engine.scan.return_value = [mock_stock1, mock_stock2]

        mock_line = MagicMock()

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            stock_picker_engine=mock_engine
        )
        result = jobs.stock_picker_daily()

        assert result["stocks_found"] == 2
        assert result["users_notified"] == 2

    def test_stock_picker_engine_not_initialized(self):
        """未初始化 StockPickerEngine 時應安全返回"""
        jobs = ScheduledJobs(stock_picker_engine=None)
        result = jobs.stock_picker_daily()

        assert result["stocks_found"] == 0
        assert result["users_notified"] == 0

    def test_stock_picker_daily_error_handling(self):
        """單一用戶推播失敗不應影響其他用戶"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001", "U002"]

        mock_stock1 = MagicMock()
        mock_stock1.stock_id = "2330"
        mock_stock1.stock_name = "台積電"

        mock_engine = MagicMock()
        mock_engine.scan.return_value = [mock_stock1]

        mock_line = MagicMock()
        # U001 推播失敗，U002 成功
        mock_line.push.side_effect = [
            Exception("Push to U001 failed"),
            None
        ]

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            stock_picker_engine=mock_engine
        )
        result = jobs.stock_picker_daily()

        # 應記錄 U001 的錯誤，但 U002 成功推播
        assert result["stocks_found"] == 1
        assert result["users_notified"] == 1
        assert len(result["errors"]) == 1

    def test_format_stock_picker_message(self):
        """測試選股推薦訊息格式化"""
        jobs = ScheduledJobs()

        mock_stock1 = MagicMock()
        mock_stock1.stock_id = "2330"
        mock_stock1.stock_name = "台積電"

        message = jobs._format_stock_picker_message([mock_stock1])

        assert message is not None
        assert "🎯 今日選股推薦" in message
        assert "台積電(2330)" in message
        assert "💡 輸入『1』" in message


class TestSchedulerIntegration:
    """完整集成測試 - 驗證排程和任務協作"""

    def test_full_workflow_with_scheduler_manager(self):
        """
        集成測試：排程管理器完整工作流
        1. 建立 SchedulerManager 和 ScheduledJobs
        2. 啟動排程
        3. 驗證任務已被註冊（get_jobs() 回傳至少 1 個）
        4. 停止排程
        5. 驗證 is_running=False
        """
        # 建立 Mock 的 ScheduledJobs
        mock_jobs = MagicMock(spec=ScheduledJobs)
        mock_jobs.stock_picker_daily = MagicMock(return_value={"stocks_found": 5})

        # 建立管理器
        manager = SchedulerManager()
        assert manager.is_running is False

        # 啟動排程
        manager.start(mock_jobs)
        assert manager.is_running is True

        # 驗證任務已被註冊
        jobs = manager.get_jobs()
        assert len(jobs) >= 1  # 至少有 1 個任務被註冊

        # 驗證任務名稱
        job_ids = [job.id for job in jobs]
        # 根據 ENABLE_SCHEDULER 和各個 feature flag 的狀態，應該有任務被註冊

        # 停止排程
        manager.stop()
        assert manager.is_running is False

        # 驗證停止後無法再取得任務（或取得空列表）
        jobs_after_stop = manager.get_jobs()
        # APScheduler 在 shutdown 後可能返回空列表
        assert isinstance(jobs_after_stop, list)
