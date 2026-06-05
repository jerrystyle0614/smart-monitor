"""
test_state_machine.py — 對話狀態機單元測試
純邏輯測試，不需任何外部服務
"""

import pytest
from bot.state_machine import StateMachine, MISSING_FIELDS, MONITOR_KEYWORDS


def _make_sm(state="IDLE", config=None):
    sm = StateMachine()
    sm.state = state
    sm.pending_config = config or {}
    return sm


def test_trigger_keywords_change_state_to_parsing():
    """包含監控關鍵字的訊息應將狀態切換到 PARSING"""
    sm = _make_sm("IDLE")
    assert sm.should_parse("我想監控弘憶") is True
    assert sm.should_parse("幫我追蹤台積電") is True
    assert sm.should_parse("今天天氣真好") is False


def test_get_missing_fields_all_null():
    """所有欄位為 null 時，應回傳 stock_id 以外的必填欄位"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": None, "cost_price": None,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    missing = sm.get_missing_fields()
    assert "total_shares" in missing
    assert "cost_price" in missing


def test_get_missing_fields_partial():
    """部分欄位已填時，只回傳未填的必填欄位"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": 64.86,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    missing = sm.get_missing_fields()
    # stop_loss 和 target_stage_1 都是選填，所以缺少時不算 missing
    # 只有 total_shares 和 cost_price 是必填
    assert "total_shares" not in missing
    assert "cost_price" not in missing


def test_get_missing_fields_none_when_required_filled():
    """必填欄位全部填完時，回傳空 list"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": 64.86,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    assert sm.get_missing_fields() == []


def test_next_question_for_missing_total_shares():
    """缺 total_shares 時應問持股張數"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": None, "cost_price": 64.86,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    q = sm.next_question()
    assert "幾張" in q or "張數" in q


def test_next_question_for_missing_cost_price():
    """缺 cost_price 時應問均價"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": None,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    q = sm.next_question()
    assert "均價" in q or "成本" in q


def test_apply_answer_shares():
    """使用者回答張數時應正確更新 pending_config"""
    sm = _make_sm(state="COLLECTING", config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": None, "cost_price": None,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    sm.current_question = "total_shares"
    sm.apply_answer("5")
    assert sm.pending_config["total_shares"] == 5000  # 5 張 = 5000 股


def test_apply_answer_price():
    """使用者回答均價時應正確更新 pending_config"""
    sm = _make_sm(state="COLLECTING", config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": None,
        "stop_loss_moving": None, "target_stage_1": None,
        "target_stage_2": None,
    })
    sm.current_question = "cost_price"
    sm.apply_answer("64.86")
    assert sm.pending_config["cost_price"] == pytest.approx(64.86)


def test_build_confirm_card():
    """確認卡片應包含所有已填欄位"""
    sm = _make_sm(config={
        "stock_id": "3312", "stock_name": "弘憶",
        "total_shares": 5000, "cost_price": 64.86,
        "stop_loss_moving": 63.0, "target_stage_1": 75.0,
        "target_stage_2": None,
    })
    card = sm.build_confirm_card()
    assert "3312" in card
    assert "64.86" in card
    assert "63" in card
    assert "75" in card
