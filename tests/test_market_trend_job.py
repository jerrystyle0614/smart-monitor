"""tests/test_market_trend_job.py"""
from unittest.mock import patch, MagicMock
import pytest


class TestMarketTrendDaily:
    def _make_jobs(self):
        from bot.scheduler.jobs import ScheduledJobs
        line_client = MagicMock()
        tg_client = MagicMock()
        return ScheduledJobs(line_client=line_client, tg_client=tg_client), line_client, tg_client

    def test_pushes_to_all_active_users(self):
        """有 active 用戶時應推播給每個人"""
        jobs, line_client, tg_client = self._make_jobs()

        sample_data = {"sp500": {"price": 5500.0, "change_pct": 0.5}}
        sample_msg = "📈 今日大盤走勢預測（2026-06-29 08:50）\n\n偏多\n\n⚠️ 本分析僅供參考，投資決策應自負其責"

        with patch("bot.scheduler.jobs.fetch_market_data", return_value=sample_data), \
             patch("bot.scheduler.jobs.analyze_market_trend", return_value="偏多"), \
             patch("bot.scheduler.jobs.build_market_trend_message", return_value=sample_msg), \
             patch("bot.user_store.UserStore.get_all_active_users", return_value=["uid_line_1"]):
            jobs.market_trend_daily()

        line_client.push.assert_called_once_with("uid_line_1", sample_msg)

    def test_skips_when_no_market_data(self):
        """fetch_market_data 回傳 None 時不推播"""
        jobs, line_client, tg_client = self._make_jobs()

        with patch("bot.scheduler.jobs.fetch_market_data", return_value=None):
            jobs.market_trend_daily()

        line_client.push.assert_not_called()
        tg_client.push.assert_not_called()

    def test_no_crash_when_push_fails(self):
        """單一用戶推播失敗時不中斷其他用戶"""
        jobs, line_client, tg_client = self._make_jobs()
        line_client.push.side_effect = Exception("network error")

        sample_data = {"sp500": {"price": 5500.0, "change_pct": 0.5}}

        with patch("bot.scheduler.jobs.fetch_market_data", return_value=sample_data), \
             patch("bot.scheduler.jobs.analyze_market_trend", return_value="偏多"), \
             patch("bot.scheduler.jobs.build_market_trend_message", return_value="msg"), \
             patch("bot.user_store.UserStore.get_all_active_users", return_value=["u1", "u2"]):
            jobs.market_trend_daily()  # 不應拋例外

    def test_pushes_to_telegram_users(self):
        """有 tg_client 時應推播給 Telegram 使用者"""
        jobs, line_client, tg_client = self._make_jobs()

        sample_data = {"sp500": {"price": 5500.0, "change_pct": 0.5}}
        sample_msg = "msg"

        # get_all_active_users 每次呼叫都回傳 ["tg_user_1"]（LINE + TG 各呼叫一次）
        with patch("bot.scheduler.jobs.fetch_market_data", return_value=sample_data), \
             patch("bot.scheduler.jobs.analyze_market_trend", return_value="偏多"), \
             patch("bot.scheduler.jobs.build_market_trend_message", return_value=sample_msg), \
             patch("bot.user_store.UserStore.get_all_active_users", return_value=["tg_user_1"]):
            jobs.market_trend_daily()

        # TG 應有推播
        assert tg_client.push.called
        tg_client.push.assert_called_with("tg_user_1", sample_msg)

    def test_no_crash_when_tg_push_fails(self):
        """TG 推播失敗時不中斷其他使用者"""
        jobs, line_client, tg_client = self._make_jobs()
        tg_client.push.side_effect = Exception("tg network error")

        sample_data = {"sp500": {"price": 5500.0, "change_pct": 0.5}}

        with patch("bot.scheduler.jobs.fetch_market_data", return_value=sample_data), \
             patch("bot.scheduler.jobs.analyze_market_trend", return_value="偏多"), \
             patch("bot.scheduler.jobs.build_market_trend_message", return_value="msg"), \
             patch("bot.user_store.UserStore.get_all_active_users", return_value=["u1"]):
            jobs.market_trend_daily()  # 不應拋例外
