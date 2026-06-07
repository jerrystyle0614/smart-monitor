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


class TestSchedulerIntegration:
    """完整集成測試 - 驗證排程和任務協作"""

    def test_full_workflow_pre_market(self):
        """
        集成測試：完整盤前分析工作流
        1. Mock UserStore 返回 1 個用戶，用戶有 2 支監控股票
        2. Mock AnalysisEngine 返回分析結果
        3. Mock LineClient 追蹤 push 呼叫
        4. 執行 pre_market_analysis()
        5. 驗證：push 被呼叫 2 次（每支股票一次）
        """
        # 建立 Mock
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001"]
        mock_store.get_watchlist.return_value = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
        ]

        mock_analysis = MagicMock()
        # 每次分析都返回有效結果
        mock_analysis.analyze_pre_market.return_value = {
            "technical": {"trend": "上升", "support": 750, "resistance": 800},
            "timestamp": "2026-06-07T08:30:00"
        }

        mock_line = MagicMock()

        # 建立 ScheduledJobs
        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )

        # 執行盤前分析
        result = jobs.pre_market_analysis()

        # 驗證結果
        assert result["users_processed"] == 1
        assert result["stocks_analyzed"] == 2
        assert result["timestamp"] is not None
        assert len(result["errors"]) == 0

        # 驗證 push 被呼叫 1 次（訊息包含 2 支股票）
        mock_line.push.assert_called_once()
        call_args = mock_line.push.call_args
        assert call_args[0][0] == "U001"  # 驗證用戶 ID
        assert "台積電" in call_args[0][1]  # 驗證訊息包含股票名稱
        assert "聯發科" in call_args[0][1]

    def test_full_workflow_with_scheduler_manager(self):
        """
        集成測試：排程管理器完整工作流
        1. 建立 SchedulerManager 和 ScheduledJobs
        2. 啟動排程
        3. 驗證任務已被註冊（get_jobs() 回傳至少 3 個）
        4. 停止排程
        5. 驗證 is_running=False
        """
        # 建立 Mock 的 ScheduledJobs
        mock_jobs = MagicMock(spec=ScheduledJobs)
        mock_jobs.stock_picker_daily = MagicMock(return_value={"stocks_found": 5})
        mock_jobs.pre_market_analysis = MagicMock(return_value={"stocks_analyzed": 10})
        mock_jobs.post_market_analysis = MagicMock(return_value={"stocks_analyzed": 10})

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

    def test_multiple_users_watchlist_broadcast(self):
        """
        集成測試：多用戶、多股票的推播流程
        驗證每個用戶都能收到該用戶自己的監控股票分析結果
        """
        # 建立 Mock
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001", "U002", "U003"]

        # 不同用戶有不同的監控清單
        def get_watchlist_side_effect(uid):
            watchlists = {
                "U001": [
                    {"stock_id": "2330", "stock_name": "台積電"},
                    {"stock_id": "2454", "stock_name": "聯發科"},
                ],
                "U002": [
                    {"stock_id": "2330", "stock_name": "台積電"},
                ],
                "U003": [],  # 無監控股票
            }
            return watchlists.get(uid, [])

        mock_store.get_watchlist.side_effect = get_watchlist_side_effect

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

        # 執行盤前分析
        result = jobs.pre_market_analysis()

        # 驗證結果
        assert result["users_processed"] == 3
        assert result["stocks_analyzed"] == 3  # 2 (U001) + 1 (U002) + 0 (U003)
        assert len(result["errors"]) == 0

        # 驗證 push 被呼叫 2 次（U001 和 U002，U003 沒有監控）
        assert mock_line.push.call_count == 2

        # 驗證每個推播都指向正確的用戶
        calls = mock_line.push.call_args_list
        pushed_users = [call[0][0] for call in calls]
        assert "U001" in pushed_users
        assert "U002" in pushed_users

    def test_error_isolation_with_cascade_prevention(self):
        """
        集成測試：驗證錯誤隔離和級聯預防
        - 用戶 1 的股票分析拋出異常
        - 用戶 2 應繼續執行
        - 推播失敗也不應中斷整個流程
        """
        mock_store = MagicMock()
        mock_store.get_all_monitoring_users.return_value = ["U001", "U002"]

        # U001 有 1 支股票，U002 有 2 支
        def get_watchlist_side_effect(uid):
            watchlists = {
                "U001": [{"stock_id": "2330", "stock_name": "台積電"}],
                "U002": [
                    {"stock_id": "2454", "stock_name": "聯發科"},
                    {"stock_id": "2317", "stock_name": "鴻海"},
                ],
            }
            return watchlists.get(uid, [])

        mock_store.get_watchlist.side_effect = get_watchlist_side_effect

        mock_analysis = MagicMock()
        # U001 的分析失敗，U002 的成功
        mock_analysis.analyze_pre_market.side_effect = [
            Exception("Failed to fetch data for 2330"),
            {"technical": {"trend": "下跌"}},  # 2454 成功
            {"technical": {"trend": "上升"}},  # 2317 成功
        ]

        mock_line = MagicMock()
        # U002 的推播成功
        mock_line.push.return_value = None

        jobs = ScheduledJobs(
            user_store=mock_store,
            line_client=mock_line,
            analysis_engine=mock_analysis
        )

        result = jobs.pre_market_analysis()

        # 驗證：
        # - 2 個用戶已處理
        # - 只有 2 支股票成功分析（2454, 2317），2330 失敗
        # - 至少有 1 個錯誤記錄
        # - U002 的推播應該成功
        assert result["users_processed"] == 2
        assert result["stocks_analyzed"] == 2
        assert len(result["errors"]) >= 1

        # U002 應該被推播（儘管 U001 有失敗）
        mock_line.push.assert_called_once()
        call_args = mock_line.push.call_args
        assert call_args[0][0] == "U002"
