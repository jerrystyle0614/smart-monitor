"""
user_store.py — 使用者資料持久化模組
管理三個 JSON 檔案：profile.json（身份）、state.json（對話狀態）、watchlist.json（加密監控）
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from bot.crypto import encrypt_fields, decrypt_fields


MAX_STOCKS = 3
SENSITIVE_FIELDS = ["total_shares", "cost_price", "stop_loss_moving", "target_stage_1"]
COOLDOWN_DURATION = 60   # 冷卻時長（秒）
COOLDOWN_WINDOW = 30     # 計算視窗（秒）
COOLDOWN_THRESHOLD = 5   # 超過幾訊息觸發

# --- 向後相容常數（handlers.py Phase A 改寫前使用）---
COOLDOWN_BLOCK_SEC = COOLDOWN_DURATION
INTENT_FAIL_GUIDE = 5
INTENT_FAIL_WARN = 10
INTENT_FAIL_BLOCK = 20


_DEFAULT_STATE = {
    "service": None,
    "step": None,
    "draft": {},
    "edit_index": None,
    "msg_timestamps": [],
    "cooldown_blocked_until": 0,
}

_DEFAULT_PROFILE = {
    "plan": "free",
    "plan_expires": None,
    "created_at": None,
}


class UserStoreError(Exception):
    """UserStore 操作失敗"""


class UserStore:
    """使用者資料儲存（三檔案架構：profile / state / watchlist）"""

    # class-level default — can be patched via patch.object(UserStore, "data_dir", ...)
    data_dir = os.environ.get("USER_DATA_DIR", "users")

    def __init__(self):
        # Honour env var at construction time, but do NOT overwrite if already
        # patched at the class level (the fixture patches before instantiation).
        env_val = os.environ.get("USER_DATA_DIR")
        if env_val and env_val != UserStore.data_dir:
            self.data_dir = env_val  # type: ignore[assignment]
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _user_dir(self, uid):
        # type: (str) -> Path
        """取得（並建立）使用者資料目錄"""
        path = Path(self.data_dir) / uid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_json(self, path, default):
        # type: (Path, Dict) -> Dict
        """讀取 JSON；不存在或解析失敗則回傳 default 的副本"""
        try:
            if path.exists():
                with open(str(path), "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print("[user_store] 讀取 {} 失敗：{}".format(path, e))
        return dict(default)

    def _save_json(self, path, data):
        # type: (Path, Dict) -> None
        """儲存 JSON"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(path), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[user_store] 儲存 {} 失敗：{}".format(path, e))

    # ------------------------------------------------------------------
    # Profile — plan management
    # ------------------------------------------------------------------

    def get_plan(self, uid):
        # type: (str) -> str
        """取得使用者計畫（free/basic/pro），預設 'free'"""
        profile_path = self._user_dir(uid) / "profile.json"
        profile = self._load_json(profile_path, _DEFAULT_PROFILE)
        return profile.get("plan", "free")

    def set_plan(self, uid, plan):
        # type: (str, str) -> None
        """設定使用者計畫"""
        profile_path = self._user_dir(uid) / "profile.json"
        profile = self._load_json(profile_path, dict(_DEFAULT_PROFILE))
        profile["uid"] = uid
        profile["plan"] = plan
        self._save_json(profile_path, profile)

    # ------------------------------------------------------------------
    # State — dialog state machine
    # ------------------------------------------------------------------

    def _load_state(self, uid):
        # type: (str) -> Dict
        state_path = self._user_dir(uid) / "state.json"
        return self._load_json(state_path, dict(_DEFAULT_STATE))

    def _save_state(self, uid, state):
        # type: (str, Dict) -> None
        state_path = self._user_dir(uid) / "state.json"
        self._save_json(state_path, state)

    def get_current_service(self, uid):
        # type: (str) -> Optional[str]
        """取得目前進行中的服務名稱，無則為 None"""
        return self._load_state(uid).get("service")

    def get_current_step(self, uid):
        # type: (str) -> Optional[int]
        """取得目前問答步驟"""
        return self._load_state(uid).get("step")

    def get_draft(self, uid):
        # type: (str) -> Dict
        """取得草稿欄位"""
        return self._load_state(uid).get("draft", {})

    def set_service_state(self, uid, service, step, draft, edit_index):
        # type: (str, Optional[str], Optional[int], Dict, Optional[int]) -> None
        """設定完整服務狀態"""
        state = self._load_state(uid)
        state["service"] = service
        state["step"] = step
        state["draft"] = draft
        state["edit_index"] = edit_index
        self._save_state(uid, state)

    def clear_service_state(self, uid):
        # type: (str) -> None
        """清除服務狀態，回到待機"""
        self.set_service_state(uid, None, None, {}, None)

    # ------------------------------------------------------------------
    # Watchlist — encrypted stock list
    # ------------------------------------------------------------------

    def _load_watchlist_raw(self, uid):
        # type: (str) -> Dict
        watchlist_path = self._user_dir(uid) / "watchlist.json"
        return self._load_json(watchlist_path, {"stocks": []})

    def _save_watchlist_raw(self, uid, wl_data):
        # type: (str, Dict) -> None
        watchlist_path = self._user_dir(uid) / "watchlist.json"
        self._save_json(watchlist_path, wl_data)

    def get_watchlist(self, uid):
        # type: (str) -> List[Dict]
        """
        取得監控清單，敏感欄位自動解密。
        回傳的敏感欄位值為字串（原始輸入格式）。
        """
        wl_data = self._load_watchlist_raw(uid)
        stocks = []
        for stock in wl_data.get("stocks", []):
            decrypted = decrypt_fields(stock, SENSITIVE_FIELDS)
            stocks.append(decrypted)
        return stocks

    def add_stock(self, uid, stock):
        # type: (str, Dict) -> None
        """新增股票至監控清單（自動加密敏感欄位），超過上限拋出 UserStoreError"""
        wl_data = self._load_watchlist_raw(uid)
        if len(wl_data["stocks"]) >= MAX_STOCKS:
            raise UserStoreError(
                "監控上限 {} 支，無法新增".format(MAX_STOCKS)
            )
        encrypted = encrypt_fields(stock, SENSITIVE_FIELDS)
        wl_data["stocks"].append(encrypted)
        self._save_watchlist_raw(uid, wl_data)

    def update_stock(self, uid, index, stock):
        # type: (str, int, Dict) -> None
        """更新指定索引的股票（自動加密）"""
        wl_data = self._load_watchlist_raw(uid)
        if index < 0 or index >= len(wl_data["stocks"]):
            raise UserStoreError("索引 {} 超出範圍".format(index))
        encrypted = encrypt_fields(stock, SENSITIVE_FIELDS)
        wl_data["stocks"][index] = encrypted
        self._save_watchlist_raw(uid, wl_data)

    def remove_stock(self, uid, index):
        # type: (str, int) -> None
        """刪除指定索引的股票"""
        wl_data = self._load_watchlist_raw(uid)
        if index < 0 or index >= len(wl_data["stocks"]):
            raise UserStoreError("索引 {} 超出範圍".format(index))
        wl_data["stocks"].pop(index)
        self._save_watchlist_raw(uid, wl_data)

    # ------------------------------------------------------------------
    # Cooldown — spam protection
    # ------------------------------------------------------------------

    def check_cooldown(self, uid):
        # type: (str) -> bool
        """
        冷卻機制：COOLDOWN_THRESHOLD 訊息在 COOLDOWN_WINDOW 秒內 →
        觸發 COOLDOWN_DURATION 秒封鎖。
        回傳 True 表示被封鎖，False 表示允許。
        """
        state = self._load_state(uid)
        now = time.time()

        # 檢查是否在封鎖期
        if state.get("cooldown_blocked_until", 0) > now:
            return True

        # 清理視窗外的舊時戳
        timestamps = [
            t for t in state.get("msg_timestamps", [])
            if now - t < COOLDOWN_WINDOW
        ]

        # 已達閾值 → 觸發冷卻
        if len(timestamps) >= COOLDOWN_THRESHOLD:
            state["cooldown_blocked_until"] = now + COOLDOWN_DURATION
            state["msg_timestamps"] = []
            self._save_state(uid, state)
            return True

        # 正常 → 記錄本次時戳
        timestamps.append(now)
        state["msg_timestamps"] = timestamps
        self._save_state(uid, state)
        return False

    # ------------------------------------------------------------------
    # Monitoring — cross-user queries
    # ------------------------------------------------------------------

    def get_all_monitoring_users(self):
        # type: () -> List[str]
        """回傳所有有監控股票（watchlist 非空）的使用者 ID 列表"""
        users = []
        users_path = Path(self.data_dir)
        if not users_path.exists():
            return users
        for user_dir in users_path.iterdir():
            if not user_dir.is_dir():
                continue
            wl_data = self._load_json(
                user_dir / "watchlist.json", {"stocks": []}
            )
            if wl_data.get("stocks"):
                users.append(user_dir.name)
        return users

    # ------------------------------------------------------------------
    # Per-stock alert flags (stored in watchlist.json)
    # ------------------------------------------------------------------

    def get_alert_fired(self, uid, stock_index, alert_key):
        # type: (str, int, str) -> bool
        """取得指定股票的警報是否已觸發（預設 False）"""
        wl_data = self._load_watchlist_raw(uid)
        stocks = wl_data.get("stocks", [])
        if stock_index < 0 or stock_index >= len(stocks):
            return False
        return stocks[stock_index].get("alerts_fired", {}).get(alert_key, False)

    def set_alert_fired(self, uid, stock_index, alert_key, value):
        # type: (str, int, str, bool) -> None
        """設定指定股票的警報狀態"""
        wl_data = self._load_watchlist_raw(uid)
        stocks = wl_data.get("stocks", [])
        if stock_index < 0 or stock_index >= len(stocks):
            return
        if "alerts_fired" not in stocks[stock_index]:
            stocks[stock_index]["alerts_fired"] = {"stop": False, "target1": False}
        stocks[stock_index]["alerts_fired"][alert_key] = value
        self._save_watchlist_raw(uid, wl_data)
