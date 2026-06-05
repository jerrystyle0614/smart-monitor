"""
test_monitor_engine.py — MonitorEngine 單元測試
mock Fugle API 和推播，驗證條件觸發邏輯
"""
import pytest
from unittest.mock import MagicMock, patch
from bot.monitor_engine import MonitorEngine


def _make_store(uid="u1", config=None, stop_fired=False, target_fired=False):
    store = MagicMock()
    store.get_all_monitoring_users.return_value = [uid]
    store.get_config.return_value = config or {
        "stock_id": "3312",
        "stock_name": "弘憶",
        "total_shares": 3000,
        "cost_price": 64.0,
        "stop_loss_moving": 63.0,
        "target_stage_1": 75.0,
    }
    store.get_alert_fired.side_effect = lambda u, k: (
        stop_fired if k == "stop" else (target_fired if k == "target1" else False)
    )
    return store


def test_stop_loss_triggers_alert():
    """股價跌破停損價時應觸發警報"""
    store = _make_store()
    engine = MonitorEngine(store, MagicMock(), MagicMock())
    with patch("bot.monitor_engine.fetch_price", return_value=62.0):
        alerts = engine._check_user("u1")
    assert any("停損" in a["title"] for a in alerts)


def test_stop_loss_not_triggered_when_price_above():
    """股價高於停損價時不應觸發"""
    store = _make_store()
    engine = MonitorEngine(store, MagicMock(), MagicMock())
    with patch("bot.monitor_engine.fetch_price", return_value=65.0):
        alerts = engine._check_user("u1")
    assert not any("停損" in a["title"] for a in alerts)


def test_target1_triggers_alert():
    """股價達到目標一時應觸發警報"""
    store = _make_store()
    engine = MonitorEngine(store, MagicMock(), MagicMock())
    with patch("bot.monitor_engine.fetch_price", return_value=76.0):
        alerts = engine._check_user("u1")
    assert any("目標" in a["title"] for a in alerts)


def test_no_duplicate_alert():
    """已觸發的警報不應重複發送"""
    store = _make_store(stop_fired=True)
    engine = MonitorEngine(store, MagicMock(), MagicMock())
    with patch("bot.monitor_engine.fetch_price", return_value=62.0):
        alerts = engine._check_user("u1")
    assert not any("停損" in a["title"] for a in alerts)


def test_no_alert_when_stop_loss_not_set():
    """未設定停損時，股價再低也不觸發停損警報"""
    store = _make_store(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 3000, "cost_price": 64.0,
        "stop_loss_moving": None, "target_stage_1": 75.0,
    })
    engine = MonitorEngine(store, MagicMock(), MagicMock())
    with patch("bot.monitor_engine.fetch_price", return_value=50.0):
        alerts = engine._check_user("u1")
    assert not any("停損" in a["title"] for a in alerts)


def test_dispatch_sends_line_and_discord():
    """_dispatch 應同時呼叫 LINE push 和 Discord send"""
    store = _make_store()
    line = MagicMock()
    discord = MagicMock()
    engine = MonitorEngine(store, line, discord)
    engine._dispatch("u1", [{"title": "停損觸發", "message": "跌破 63", "color": 0xE74C3C}])
    line.push.assert_called_once_with("u1", "停損觸發\n\n跌破 63")
    discord.send.assert_called_once()
