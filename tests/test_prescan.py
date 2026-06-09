"""test_prescan.py — prescan 模組測試"""
import json
import os
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import tempfile

os.environ.setdefault("FINMIND_API_KEY", "test_key")
os.environ.setdefault("FUGLE_API_KEY", "test_key")


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_df(close=100.0, volume=1000, rows=25):
    """產生假 K 線 DataFrame"""
    data = {
        "date": [str(date.today() - timedelta(days=i)) for i in range(rows)],
        "open": [close] * rows,
        "high": [close * 1.01] * rows,
        "low": [close * 0.99] * rows,
        "close": [close] * rows,
        "volume": [volume] * rows,
    }
    return pd.DataFrame(data)


def _make_institutional(trust_net=100.0, trust_consecutive=3):
    return {
        "consecutive_net_buy_days": trust_consecutive,
        "foreign_net": 500.0,
        "trust_net": trust_net,
        "dealer_net": 50.0,
        "total_net": 650.0,
        "trust_consecutive_days": trust_consecutive,
        "dates": [],
    }


# ── prescan 模組測試 ──────────────────────────────────────────────────────────

class TestRunPrescan:
    """run_prescan 的 patch 路徑需指向 lazy import 的來源模組"""

    def test_run_prescan_writes_json(self, tmp_path):
        """run_prescan 應寫入 JSON 檔案並回傳候選股數量"""
        all_stocks = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
            {"stock_id": "2317", "stock_name": "鴻海"},
        ]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional()

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", return_value=_make_df(close=100.0, volume=1000)):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 3
        today = date.today().isoformat()
        out_file = tmp_path / f"{today}.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["count"] == 3
        assert len(data["stocks"]) == 3

    def test_run_prescan_filters_low_price(self, tmp_path):
        """收盤價 <= 5 的股票應被過濾"""
        all_stocks = [
            {"stock_id": "1234", "stock_name": "低價股"},
            {"stock_id": "2330", "stock_name": "台積電"},
        ]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional()

        def candle_side(stock_id, days=60):
            price = 3.0 if stock_id == "1234" else 500.0
            return _make_df(close=price, volume=2000)

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", side_effect=candle_side):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 1

    def test_run_prescan_filters_low_volume(self, tmp_path):
        """近 20 日均量 <= 500 張的股票應被過濾"""
        all_stocks = [{"stock_id": "2330", "stock_name": "台積電"}]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional()

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", return_value=_make_df(close=100.0, volume=100)):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 0

    def test_run_prescan_filters_trust_net_negative(self, tmp_path):
        """投信淨賣超 < 0 的股票應被過濾"""
        all_stocks = [{"stock_id": "2330", "stock_name": "台積電"}]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional(trust_net=-200.0)

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", return_value=_make_df(close=100.0, volume=2000)):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 0

    def test_run_prescan_excludes_etf_and_ky(self, tmp_path):
        """ETF（代號 > 4 碼）與 KY 股應被排除在掃描之前"""
        all_stocks = [
            {"stock_id": "00878", "stock_name": "國泰永續高息"},  # ETF，5碼
            {"stock_id": "2330", "stock_name": "台積電 KY"},      # KY 股
            {"stock_id": "2454", "stock_name": "聯發科"},         # 正常
        ]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional()

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", return_value=_make_df(close=100.0, volume=2000)):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 1

    def test_run_prescan_handles_api_failure(self, tmp_path):
        """FinMind 回傳空清單時應回傳 0 且不 raise"""
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = []

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 0

    def test_run_prescan_skips_failed_stock(self, tmp_path):
        """單支股票 fetch_candles 失敗應略過，不中斷整批"""
        all_stocks = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
        ]
        mock_fm = MagicMock()
        mock_fm.get_all_stocks_basic.return_value = all_stocks
        mock_fm.get_three_major_buyers.return_value = _make_institutional()

        def candle_side(stock_id, days=60):
            if stock_id == "2330":
                raise Exception("API timeout")
            return _make_df(close=100.0, volume=2000)

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path), \
             patch("bot.stock_picker.finmind_client.FinMindClient", return_value=mock_fm), \
             patch("daily_data.fetch_candles", side_effect=candle_side):

            from bot.services.prescan import run_prescan
            count = run_prescan()

        assert count == 1  # 2454 通過，2330 略過


class TestLoadPrescanCandidates:

    def test_loads_today_file(self, tmp_path):
        """有當日檔案時應回傳當日資料"""
        today = date.today().isoformat()
        data = {
            "date": today,
            "count": 2,
            "stocks": [
                {"stock_id": "2330", "stock_name": "台積電"},
                {"stock_id": "2454", "stock_name": "聯發科"},
            ],
        }
        (tmp_path / f"{today}.json").write_text(json.dumps(data), encoding="utf-8")

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path):
            from bot.services.prescan import load_prescan_candidates
            result = load_prescan_candidates()

        assert len(result) == 2
        assert ("2330", "台積電") in result

    def test_fallback_to_yesterday(self, tmp_path):
        """無當日檔案時應 fallback 到前一日"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        data = {
            "date": yesterday,
            "count": 1,
            "stocks": [{"stock_id": "2317", "stock_name": "鴻海"}],
        }
        (tmp_path / f"{yesterday}.json").write_text(json.dumps(data), encoding="utf-8")

        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path):
            from bot.services.prescan import load_prescan_candidates
            result = load_prescan_candidates()

        assert ("2317", "鴻海") in result

    def test_fallback_to_universe_when_no_files(self, tmp_path):
        """無任何快取時應 fallback 到 _FALLBACK_UNIVERSE"""
        with patch("bot.services.prescan.PRESCAN_DIR", tmp_path):
            from bot.services.prescan import load_prescan_candidates, _FALLBACK_UNIVERSE
            result = load_prescan_candidates()

        assert result == list(_FALLBACK_UNIVERSE)
        assert len(result) == len(_FALLBACK_UNIVERSE)


# ── trust_consecutive_days 測試 ──────────────────────────────────────────────

class TestTrustConsecutiveDays:

    def test_finmind_client_returns_trust_consecutive(self):
        """get_three_major_buyers 應回傳 trust_consecutive_days"""
        mock_response = {
            "data": [
                {"date": "2026-06-09", "stock_id": "2330", "buy": 500, "sell": 100, "name": "Investment_Trust"},
                {"date": "2026-06-08", "stock_id": "2330", "buy": 300, "sell": 50,  "name": "Investment_Trust"},
                {"date": "2026-06-07", "stock_id": "2330", "buy": 200, "sell": 300, "name": "Investment_Trust"},
            ]
        }
        with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            from bot.stock_picker.finmind_client import FinMindClient
            client = FinMindClient()
            result = client.get_three_major_buyers("2330", days=5)

        assert result is not None
        assert "trust_consecutive_days" in result
        # 前兩日投信買超（400>50, 250>0），第三日賣超（200>300 → net<0），連續天數=2
        assert result["trust_consecutive_days"] == 2

    def test_institutional_client_returns_trust_consecutive(self):
        """get_institutional_data 應回傳 trust_consecutive_days"""
        mock_response = {
            "data": [
                {"date": "2026-06-09", "stock_id": "2330", "buy": 500, "sell": 100, "name": "Investment_Trust"},
                {"date": "2026-06-08", "stock_id": "2330", "buy": 300, "sell": 50,  "name": "Investment_Trust"},
            ]
        }
        with patch("bot.data.institutional_client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            from bot.data.institutional_client import get_institutional_data
            result = get_institutional_data("2330", days=5)

        assert result is not None
        assert "trust_consecutive_days" in result
        assert result["trust_consecutive_days"] == 2


# ── 排程 prescan_daily 測試 ───────────────────────────────────────────────────

class TestPrescanScheduler:

    def test_prescan_daily_job_registered_in_config(self):
        """SCHEDULED_JOBS 應包含 prescan_daily"""
        from bot.scheduler.config import SCHEDULED_JOBS
        names = [j.name for j in SCHEDULED_JOBS]
        assert "prescan_daily" in names

    def test_prescan_daily_job_time(self):
        """prescan_daily 應設定在 13:40"""
        from bot.scheduler.config import SCHEDULED_JOBS
        job = next(j for j in SCHEDULED_JOBS if j.name == "prescan_daily")
        assert job.hour == 13
        assert job.minute == 40

    def test_prescan_daily_method_exists(self):
        """ScheduledJobs 應有 prescan_daily 方法"""
        from bot.scheduler.jobs import ScheduledJobs
        jobs = ScheduledJobs()
        assert hasattr(jobs, "prescan_daily")
        assert callable(jobs.prescan_daily)

    def test_prescan_daily_calls_run_prescan(self):
        """prescan_daily() 應呼叫 run_prescan()"""
        from bot.scheduler.jobs import ScheduledJobs
        jobs = ScheduledJobs()
        with patch("bot.services.prescan.run_prescan", return_value=150) as mock_run:
            jobs.prescan_daily()
        mock_run.assert_called_once()

    def test_manager_maps_prescan_daily(self):
        """SchedulerManager._get_job_function 應能解析 prescan_daily"""
        from bot.scheduler.manager import SchedulerManager
        from bot.scheduler.jobs import ScheduledJobs
        manager = SchedulerManager()
        manager.scheduled_jobs = ScheduledJobs()
        func = manager._get_job_function("prescan_daily")
        assert func is not None
