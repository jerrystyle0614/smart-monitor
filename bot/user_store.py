"""
user_store.py — 使用者資料讀寫模組
每位使用者的狀態與 config 存在 users/{line_user_id}/ 目錄下
"""

import json
import datetime
import time
from pathlib import Path
from typing import Optional

# 冷卻機制參數
COOLDOWN_WINDOW_SEC = 30   # 觀察視窗（秒）
COOLDOWN_MSG_LIMIT  = 5    # 視窗內超過此則數觸發冷卻
COOLDOWN_BLOCK_SEC  = 60   # 冷卻封鎖時間（秒）

# 意圖失敗閾值
INTENT_FAIL_GUIDE   = 5    # 失敗幾次後給範例引導
INTENT_FAIL_WARN    = 10   # 失敗幾次後警告有上限
INTENT_FAIL_BLOCK   = 20   # 失敗幾次後視為惡意，封鎖當日


class UserStore:
    def __init__(self, base_dir: str = "users"):
        self._base = Path(base_dir)

    def _user_dir(self, uid: str) -> Path:
        """取得或建立使用者目錄"""
        d = self._base / uid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_path(self, uid: str) -> Path:
        """取得使用者 state.json 的路徑"""
        return self._user_dir(uid) / "state.json"

    def _config_path(self, uid: str) -> Path:
        """取得使用者 config.json 的路徑"""
        return self._user_dir(uid) / "config.json"

    def _read_state(self, uid: str) -> dict:
        """讀取 state.json，不存在則回傳空 dict"""
        path = self._state_path(uid)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] 讀取 {path} 失敗，重置為空：{e}")
            return {}

    def _write_state(self, uid: str, data: dict) -> None:
        """寫入 state.json"""
        with open(self._state_path(uid), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_state(self, uid: str) -> str:
        """取得使用者狀態，預設為 IDLE"""
        return self._read_state(uid).get("state", "IDLE")

    def set_state(self, uid: str, state: str) -> None:
        """設定使用者狀態"""
        data = self._read_state(uid)
        data["state"] = state
        self._write_state(uid, data)

    def get_config(self, uid: str) -> dict:
        """取得使用者 config，不存在則回傳空 dict"""
        path = self._config_path(uid)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] 讀取 {path} 失敗，回傳空 config：{e}")
            return {}

    def set_config(self, uid: str, config: dict) -> None:
        """設定使用者 config"""
        with open(self._config_path(uid), "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def get_daily_call_count(self, uid: str) -> int:
        """取得今日 Claude API 呼叫次數，日期變更時自動重置"""
        today = datetime.date.today().isoformat()
        state = self._read_state(uid)
        if state.get("call_date") != today:
            return 0
        return state.get("call_count", 0)

    def increment_daily_call_count(self, uid: str) -> int:
        """累加今日呼叫次數並回傳新值"""
        today = datetime.date.today().isoformat()
        state = self._read_state(uid)
        if state.get("call_date") != today:
            state["call_date"] = today
            state["call_count"] = 0
        state["call_count"] = state.get("call_count", 0) + 1
        self._write_state(uid, state)
        return state["call_count"]

    def get_daily_intent_fail_count(self, uid: str) -> int:
        """取得今日意圖判斷失敗次數"""
        today = datetime.date.today().isoformat()
        state = self._read_state(uid)
        if state.get("intent_fail_date") != today:
            return 0
        return state.get("intent_fail_count", 0)

    def increment_intent_fail_count(self, uid: str) -> int:
        """累加今日意圖判斷失敗次數並回傳新值"""
        today = datetime.date.today().isoformat()
        state = self._read_state(uid)
        if state.get("intent_fail_date") != today:
            state["intent_fail_date"] = today
            state["intent_fail_count"] = 0
        state["intent_fail_count"] = state.get("intent_fail_count", 0) + 1
        self._write_state(uid, state)
        return state["intent_fail_count"]

    def check_cooldown(self, uid: str) -> bool:
        """
        冷卻機制：30 秒內超過 5 則訊息則封鎖 60 秒。
        回傳 True 表示目前在冷卻中（應拒絕處理）。
        """
        now = time.time()
        state = self._read_state(uid)

        # 檢查是否在封鎖期
        blocked_until = state.get("cooldown_blocked_until", 0)
        if now < blocked_until:
            return True

        # 記錄本次訊息時間戳，清除視窗外的舊記錄
        timestamps = state.get("msg_timestamps", [])
        timestamps.append(now)
        timestamps = [t for t in timestamps if now - t <= COOLDOWN_WINDOW_SEC]
        state["msg_timestamps"] = timestamps

        # 超過視窗內訊息數量限制，設定封鎖期
        if len(timestamps) > COOLDOWN_MSG_LIMIT:
            state["cooldown_blocked_until"] = now + COOLDOWN_BLOCK_SEC
            self._write_state(uid, state)
            return True

        self._write_state(uid, state)
        return False

    def get_current_question(self, uid: str) -> Optional[str]:
        """取得目前追問的欄位名稱"""
        return self._read_state(uid).get("current_question")

    def set_current_question(self, uid: str, field: Optional[str]) -> None:
        """設定目前追問的欄位名稱"""
        state = self._read_state(uid)
        state["current_question"] = field
        self._write_state(uid, state)

    def get_all_monitoring_users(self) -> list:
        """回傳所有目前處於 MONITORING 狀態的使用者 ID 列表"""
        result = []
        if not self._base.exists():
            return result
        for user_dir in self._base.iterdir():
            if user_dir.is_dir():
                uid = user_dir.name
                if self.get_state(uid) == "MONITORING":
                    result.append(uid)
        return result

    def get_alert_fired(self, uid: str, alert_key: str) -> bool:
        """取得指定警報是否已觸發，預設 False"""
        state = self._read_state(uid)
        return state.get("alerts_fired", {}).get(alert_key, False)

    def set_alert_fired(self, uid: str, alert_key: str, value: bool) -> None:
        """設定指定警報觸發旗標"""
        state = self._read_state(uid)
        if "alerts_fired" not in state:
            state["alerts_fired"] = {}
        state["alerts_fired"][alert_key] = value
        self._write_state(uid, state)

    def reset_alerts(self, uid: str) -> None:
        """清除所有警報旗標（修改監控條件時呼叫）"""
        state = self._read_state(uid)
        state["alerts_fired"] = {}
        self._write_state(uid, state)
