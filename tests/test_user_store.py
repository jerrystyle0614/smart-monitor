"""
test_user_store.py — user_store 模組單元測試
使用 pytest tmp_path fixture，不寫入真實 users/ 目錄
"""

import json
import pytest
from bot.user_store import UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(base_dir=str(tmp_path))


def test_get_state_default_is_idle(store):
    """未設定狀態時，預設應回傳 IDLE"""
    assert store.get_state("user_001") == "IDLE"


def test_set_and_get_state(store):
    """設定狀態後應能正確讀取"""
    store.set_state("user_001", "COLLECTING")
    assert store.get_state("user_001") == "COLLECTING"


def test_get_config_default_is_empty(store):
    """未設定 config 時應回傳空 dict"""
    assert store.get_config("user_001") == {}


def test_set_and_get_config(store):
    """設定 config 後應能正確讀取"""
    cfg = {"stock_id": "3312", "cost_price": 64.86}
    store.set_config("user_001", cfg)
    assert store.get_config("user_001") == cfg


def test_get_daily_call_count_default_zero(store):
    """未呼叫過 Claude 時，當日計數應為 0"""
    assert store.get_daily_call_count("user_001") == 0


def test_increment_and_get_daily_call_count(store):
    """累加後應正確回傳計數"""
    store.increment_daily_call_count("user_001")
    store.increment_daily_call_count("user_001")
    assert store.get_daily_call_count("user_001") == 2


def test_daily_call_count_resets_on_new_day(store):
    """日期變更後計數應重置為 0"""
    import datetime
    store.increment_daily_call_count("user_001")

    # 手動寫入昨天的日期
    state = store._read_state("user_001")
    state["call_date"] = "2020-01-01"
    store._write_state("user_001", state)

    assert store.get_daily_call_count("user_001") == 0


def test_multiple_users_isolated(store):
    """不同使用者的資料應互相隔離"""
    store.set_state("user_A", "CONFIRMING")
    store.set_state("user_B", "IDLE")
    assert store.get_state("user_A") == "CONFIRMING"
    assert store.get_state("user_B") == "IDLE"


def test_get_current_question_default_none(store):
    """未設定 current_question 時應回傳 None"""
    assert store.get_current_question("user_001") is None


def test_set_and_get_current_question(store):
    """設定 current_question 後應能正確讀取"""
    store.set_current_question("user_001", "total_shares")
    assert store.get_current_question("user_001") == "total_shares"


def test_set_current_question_none_clears(store):
    """設定為 None 應清除 current_question"""
    store.set_current_question("user_001", "total_shares")
    store.set_current_question("user_001", None)
    assert store.get_current_question("user_001") is None


def test_get_all_monitoring_users(tmp_path):
    store = UserStore(str(tmp_path))
    store.set_state("u1", "MONITORING")
    store.set_state("u2", "IDLE")
    store.set_state("u3", "MONITORING")
    result = store.get_all_monitoring_users()
    assert set(result) == {"u1", "u3"}


def test_alert_fired_default_false(tmp_path):
    store = UserStore(str(tmp_path))
    assert store.get_alert_fired("u1", "stop") is False
    assert store.get_alert_fired("u1", "target1") is False


def test_set_alert_fired(tmp_path):
    store = UserStore(str(tmp_path))
    store.set_alert_fired("u1", "stop", True)
    assert store.get_alert_fired("u1", "stop") is True
    assert store.get_alert_fired("u1", "target1") is False


def test_reset_alerts_on_config_change(tmp_path):
    store = UserStore(str(tmp_path))
    store.set_alert_fired("u1", "stop", True)
    store.set_alert_fired("u1", "target1", True)
    store.reset_alerts("u1")
    assert store.get_alert_fired("u1", "stop") is False
    assert store.get_alert_fired("u1", "target1") is False
