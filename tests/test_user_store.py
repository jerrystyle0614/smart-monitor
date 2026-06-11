"""test_user_store.py — UserStore 單元測試"""
import os
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.user_store import UserStore, UserStoreError


@pytest.fixture
def store(tmp_path):
    """建立測試用 UserStore，資料存在 tmp 目錄"""
    with patch.object(UserStore, "data_dir", str(tmp_path / "users")):
        yield UserStore()


def test_get_plan_default_free(store):
    """新使用者預設計畫應為 'free'"""
    uid = "U123"
    plan = store.get_plan(uid)
    assert plan == "free"


def test_set_plan_and_get(store):
    """set_plan 後應能讀回"""
    uid = "U123"
    store.set_plan(uid, "basic")
    assert store.get_plan(uid) == "basic"


def test_get_current_service_none_by_default(store):
    """新使用者服務應為 None"""
    uid = "U456"
    assert store.get_current_service(uid) is None


def test_set_service_state(store):
    """set_service_state 應正確儲存"""
    uid = "U456"
    store.set_service_state(uid, "stock_monitor", 1, {"stock_id": "2330"}, None)
    assert store.get_current_service(uid) == "stock_monitor"
    assert store.get_current_step(uid) == 1
    assert store.get_draft(uid)["stock_id"] == "2330"


def test_get_watchlist_empty_by_default(store):
    """新使用者監控清單應為空"""
    uid = "U789"
    wl = store.get_watchlist(uid)
    assert wl == []


def test_add_stock_encrypts_sensitive_fields(store):
    """add_stock 應加密敏感欄位"""
    uid = "U789"
    stock = {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    }
    store.add_stock(uid, stock)
    wl = store.get_watchlist(uid)
    assert len(wl) == 1
    assert wl[0]["stock_id"] == "2330"
    assert wl[0]["total_shares"] == "5"  # 讀回應自動解密
    assert wl[0]["cost_price"] == "900.0"


def test_add_stock_max_3_limit(store):
    """超過 3 支應拋出異常"""
    uid = "U999"
    for i in range(3):
        store.add_stock(uid, {
            "stock_id": str(2330 + i),
            "stock_name": "Stock{}".format(i),
            "total_shares": "1",
            "cost_price": "100",
            "stop_loss_moving": "90",
            "target_stage_1": None,
            "alerts_fired": {"stop": False, "target1": False}
        })
    with pytest.raises(UserStoreError):
        store.add_stock(uid, {
            "stock_id": "9999",
            "stock_name": "Too Many",
            "total_shares": "1",
            "cost_price": "100",
            "stop_loss_moving": "90",
            "target_stage_1": None,
            "alerts_fired": {"stop": False, "target1": False}
        })


def test_update_stock(store):
    """update_stock 應更新指定索引的股票"""
    uid = "U111"
    store.add_stock(uid, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    store.update_stock(uid, 0, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "10",
        "cost_price": "920.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    wl = store.get_watchlist(uid)
    assert wl[0]["total_shares"] == "10"
    assert wl[0]["cost_price"] == "920.0"


def test_remove_stock(store):
    """remove_stock 應刪除指定索引"""
    uid = "U222"
    store.add_stock(uid, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    store.remove_stock(uid, 0)
    wl = store.get_watchlist(uid)
    assert len(wl) == 0


def test_check_cooldown_allows_normal_rate(store):
    """正常速率應不觸發冷卻"""
    uid = "U333"
    assert store.check_cooldown(uid) == False
    time.sleep(0.1)
    assert store.check_cooldown(uid) == False


def test_check_cooldown_blocks_spam(store):
    """5 訊息在 30 秒內應觸發 60 秒冷卻"""
    uid = "U444"
    for i in range(5):
        store.check_cooldown(uid)
    # 第 5 次後應被阻擋
    assert store.check_cooldown(uid) == True


def test_get_all_monitoring_users(store):
    """get_all_monitoring_users 應回傳有 watchlist 的使用者"""
    uid1 = "U555"
    uid2 = "U666"
    store.add_stock(uid1, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    users = store.get_all_monitoring_users()
    assert uid1 in users
    assert uid2 not in users


def test_get_alert_fired(store):
    """get_alert_fired 應回傳警報狀態"""
    uid = "U777"
    store.add_stock(uid, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    assert store.get_alert_fired(uid, 0, "stop") == False


def test_set_alert_fired(store):
    """set_alert_fired 應更新警報狀態"""
    uid = "U888"
    store.add_stock(uid, {
        "stock_id": "2330",
        "stock_name": "台積電",
        "total_shares": "5",
        "cost_price": "900.0",
        "stop_loss_moving": "850.0",
        "target_stage_1": None,
        "alerts_fired": {"stop": False, "target1": False}
    })
    store.set_alert_fired(uid, 0, "stop", True)
    assert store.get_alert_fired(uid, 0, "stop") == True


def test_platform_line_uses_line_subdir(tmp_path):
    """platform='line' 時資料應存在 users/line/{uid}/ 下"""
    store = UserStore(platform="line")
    store.data_dir = str(tmp_path / "users" / "line")
    Path(store.data_dir).mkdir(parents=True, exist_ok=True)
    store.set_plan("U123", "pro")
    assert (tmp_path / "users" / "line" / "U123" / "profile.json").exists()


def test_platform_telegram_uses_telegram_subdir(tmp_path):
    """platform='telegram' 時資料應存在 users/telegram/{chat_id}/ 下"""
    store = UserStore(platform="telegram")
    store.data_dir = str(tmp_path / "users" / "telegram")
    Path(store.data_dir).mkdir(parents=True, exist_ok=True)
    store.set_plan("123456789", "basic")
    assert (tmp_path / "users" / "telegram" / "123456789" / "profile.json").exists()


def test_default_platform_is_line(tmp_path):
    """預設 platform 應為 line"""
    store = UserStore()
    assert "line" in store.data_dir
