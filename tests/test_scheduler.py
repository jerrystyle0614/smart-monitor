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
        mock_jobs.pre_market_analysis = MagicMock()
        mock_jobs.post_market_analysis = MagicMock()

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
        mock_jobs.pre_market_analysis = MagicMock()
        mock_jobs.post_market_analysis = MagicMock()

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
        mock_jobs.pre_market_analysis = MagicMock()
        mock_jobs.post_market_analysis = MagicMock()

        manager = SchedulerManager()
        manager.start(mock_jobs)

        # 再次啟動應被忽略
        manager.start(mock_jobs)
        assert manager.is_running is True

        manager.stop()


from bot.scheduler.jobs import ScheduledJobs


class TestScheduledJobs:
    """排程任務測試"""

    def test_pre_market_analysis_with_empty_users(self):
        """無監控用戶時，任務應安全完成"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = []

        jobs = ScheduledJobs(user_store=mock_store)
        result = jobs.pre_market_analysis()

        assert result["users_processed"] == 0
        assert result["stocks_analyzed"] == 0
        assert result["timestamp"] is not None

    def test_pre_market_analysis_with_empty_watchlist(self):
        """用戶有監控但清單空時，任務應安全完成"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001"]
        mock_store.get_watchlist.return_value = []

        jobs = ScheduledJobs(user_store=mock_store)
        result = jobs.pre_market_analysis()

        assert result["users_processed"] == 1
        assert result["stocks_analyzed"] == 0

    def test_pre_market_analysis_with_mock(self):
        """盤前分析應對所有監控用戶執行"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001"]
        mock_store.get_watchlist.return_value = [
            {"stock_id": "2330", "stock_name": "台積電"}
        ]

        mock_analysis = MagicMock()
        mock_analysis.analyze_pre_market.return_value = {
            "technical": {"trend": "上升"},
            "timestamp": "2026-06-07T08:30:00"
        }

        mock_line = MagicMock()

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )
        result = jobs.pre_market_analysis()

        assert result["users_processed"] == 1
        assert result["stocks_analyzed"] == 1
        assert len(result["errors"]) == 0
        mock_line.push.assert_called()

    def test_post_market_analysis_with_empty_users(self):
        """無監控用戶時，盤後任務應安全完成"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = []

        jobs = ScheduledJobs(user_store=mock_store)
        result = jobs.post_market_analysis()

        assert result["users_processed"] == 0
        assert result["stocks_analyzed"] == 0

    def test_post_market_analysis_with_mock(self):
        """盤後分析應對所有監控用戶執行"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001"]
        mock_store.get_watchlist.return_value = [
            {"stock_id": "2330", "stock_name": "台積電"}
        ]

        mock_analysis = MagicMock()
        mock_analysis.analyze_post_market.return_value = {
            "technical": {"trend": "下降"},
            "timestamp": "2026-06-07T13:35:00"
        }

        mock_line = MagicMock()

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )
        result = jobs.post_market_analysis()

        assert result["users_processed"] == 1
        assert result["stocks_analyzed"] == 1
        mock_line.push.assert_called()

    def test_pre_market_error_handling_per_user(self):
        """用戶處理失敗不應影響其他用戶"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001", "U002"]

        # U001 拋出異常
        mock_store.get_watchlist.side_effect = [
            Exception("U001 loading failed"),
            [{"stock_id": "2330", "stock_name": "台積電"}]
        ]

        mock_analysis = MagicMock()
        mock_analysis.analyze_pre_market.return_value = {
            "technical": {"trend": "上升"},
        }

        mock_line = MagicMock()

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )
        result = jobs.pre_market_analysis()

        # 應該在 errors 中記錄 U001 的錯誤，但仍繼續處理 U002
        assert len(result["errors"]) > 0
        assert result["stocks_analyzed"] == 1

    def test_pre_market_error_handling_per_stock(self):
        """股票分析失敗不應影響其他股票"""
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001"]
        mock_store.get_watchlist.return_value = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
        ]

        mock_analysis = MagicMock()
        # 第一支股票失敗，第二支成功
        mock_analysis.analyze_pre_market.side_effect = [
            Exception("Stock analysis failed"),
            {"technical": {"trend": "上升"}}
        ]

        mock_line = MagicMock()

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )
        result = jobs.pre_market_analysis()

        # 應記錄 2330 的錯誤，但仍分析 2454
        assert result["stocks_analyzed"] == 1
        assert len(result["errors"]) >= 1

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

    def test_format_pre_market_message(self):
        """測試盤前訊息格式化"""
        jobs = ScheduledJobs()

        analyses = [
            {
                "stock_id": "2330",
                "stock_name": "台積電",
                "analysis": {"technical": {"trend": "上升"}}
            },
            {
                "stock_id": "2454",
                "stock_name": "聯發科",
                "analysis": {"technical": {"trend": "下降"}}
            }
        ]

        message = jobs._format_pre_market_message(analyses)

        assert message is not None
        assert "📊 盤前分析" in message
        assert "台積電(2330)" in message
        assert "聯發科(2454)" in message

    def test_format_post_market_message(self):
        """測試盤後訊息格式化"""
        jobs = ScheduledJobs()

        analyses = [
            {
                "stock_id": "2330",
                "stock_name": "台積電",
                "analysis": {"technical": {"trend": "上升"}}
            }
        ]

        message = jobs._format_post_market_message(analyses)

        assert message is not None
        assert "📊 盤後分析" in message
        assert "台積電(2330)" in message

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
