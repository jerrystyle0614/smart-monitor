"""test_etf_picker.py — ETF 推薦服務測試"""
import json
import os
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")


def _make_etf_data(close=100.0, bias=2.0, ret_30=3.0, div_yield=5.0, avg_vol=5000):
    return {
        "close": close,
        "ma20": round(close / (1 + bias / 100), 2),
        "avg_vol_20": avg_vol,
        "ret_30": ret_30,
        "bias": bias,
        "div_yield": div_yield,
        "can_buy_lot": True,
        "one_lot_cost": int(close * 1000),
    }


class TestETFPickerService:

    def test_service_name(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        assert svc.name == "etf_picker"

    def test_has_two_steps(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        assert len(svc.steps) == 2

    def test_validate_capital_valid(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        ok, val, _ = svc._validate_capital("50000")
        assert ok and val == 50000.0

    def test_validate_capital_invalid(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        ok, _, msg = svc._validate_capital("abc")
        assert not ok
        assert msg

    def test_validate_goal_valid(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        for inp, expected in [("1", "index"), ("2", "dividend"), ("3", "theme")]:
            ok, val, _ = svc._validate_goal(inp)
            assert ok and val == expected

    def test_validate_goal_invalid(self):
        from bot.services.etf_picker import ETFPickerService
        svc = ETFPickerService()
        ok, _, msg = svc._validate_goal("4")
        assert not ok


class TestScanETFs:

    def test_filters_low_volume(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(avg_vol=50)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("dividend", 100000)
        assert result == []

    def test_filters_high_bias(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(bias=10.0)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("index", 100000)
        assert result == []

    def test_filters_bad_return(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(ret_30=-15.0)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("index", 100000)
        assert result == []

    def test_filters_low_div_yield_for_dividend_goal(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(div_yield=1.0)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("dividend", 100000)
        assert result == []

    def test_passes_valid_etf(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(close=30.0, bias=2.0, ret_30=5.0, div_yield=6.0, avg_vol=5000)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("dividend", 100000)
        assert len(result) > 0

    def test_marks_lot_affordability(self):
        from bot.services.etf_picker import _scan_etfs
        data = _make_etf_data(close=200.0, avg_vol=5000)
        with patch("bot.services.etf_picker._fetch_etf_data", return_value=data):
            result = _scan_etfs("index", 100000)
        if result:
            # 200 * 1000 = 200000 > 100000 → 不夠買整張
            assert result[0]["can_buy_lot"] is False


class TestETFPickerRouter:

    def test_etf_picker_in_service_map(self):
        from bot.router import _SERVICE_MAP
        assert "etf_picker" in _SERVICE_MAP

    def test_etf_picker_requires_pro(self):
        from bot.router import SERVICE_PERMISSIONS
        assert "pro" in SERVICE_PERMISSIONS["etf_picker"]
        assert "free" not in SERVICE_PERMISSIONS["etf_picker"]

    def test_menu_choice_5_starts_etf_picker(self):
        from bot.router import handle_message
        mock_store = MagicMock()
        mock_store.check_cooldown.return_value = False
        mock_store.get_plan.return_value = "pro"
        mock_store.get_current_service.return_value = None
        mock_line = MagicMock()

        with patch("bot.services.etf_picker.ETFPickerService.start") as mock_start:
            handle_message("uid_test", "5", mock_store, mock_line, "reply_token")
            mock_start.assert_called_once()
