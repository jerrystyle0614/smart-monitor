"""
user_store.py — 使用者資料讀寫模組
每位使用者的狀態與 config 存在 users/{line_user_id}/ 目錄下
"""

import json
import datetime
from pathlib import Path
from typing import Optional


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

    def get_current_question(self, uid: str) -> Optional[str]:
        """取得目前追問的欄位名稱"""
        return self._read_state(uid).get("current_question")

    def set_current_question(self, uid: str, field: Optional[str]) -> None:
        """設定目前追問的欄位名稱"""
        state = self._read_state(uid)
        state["current_question"] = field
        self._write_state(uid, state)
