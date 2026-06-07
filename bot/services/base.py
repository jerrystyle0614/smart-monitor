"""
base.py — ScriptedService 問答腳本基底類別
所有服務（股票監控、盤前分析、盤後分析）都繼承此類，實作問答流程
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Callable, Tuple, Any


@dataclass
class Step:
    """問答步驟定義"""
    field: str                                                      # 儲存欄位名
    question: str                                                   # 問題文字
    validate: Callable[[str], Tuple[bool, Any, str]]                # 驗證函式：(text) -> (ok, value, error_msg)
    optional: bool = False                                          # 是否可輸入「跳過」略過


class ScriptedService:
    """問答腳本服務基底類別"""

    name: str                # 服務名稱
    steps: List[Step]        # 問答步驟列表

    def start(self, uid: str, store, line) -> None:
        """進入服務，初始化狀態並顯示第一題"""
        store.set_service_state(uid, self.name, 0, {}, None)
        self._show_step(uid, 0, store, line)

    def handle_input(self, uid: str, text: str, store, line) -> str:
        """
        處理使用者輸入。
        回傳 "CONTINUE"（繼續）、"DONE"（完成）、"CANCEL"（取消）
        """
        current_step = store.get_current_step(uid)
        if current_step is None:
            return "CANCEL"

        step = self.steps[current_step]
        draft = store.get_draft(uid)

        # 檢查「取消」
        if text == "取消":
            store.clear_service_state(uid)
            return "CANCEL"

        # 檢查「跳過」（選填欄位）
        if text == "跳過":
            if not step.optional:
                line.reply(f"❌ 此欄位必填，無法跳過。{step.question}")
                return "CONTINUE"
            draft[step.field] = None
            next_step = current_step + 1
            if next_step >= len(self.steps):
                store.set_service_state(uid, self.name, None, draft, None)
                self.on_complete(uid, draft, store, line)
                return "DONE"
            store.set_service_state(uid, self.name, next_step, draft, None)
            self._show_step(uid, next_step, store, line)
            return "CONTINUE"

        # 驗證輸入
        ok, value, error_msg = step.validate(text)
        if not ok:
            line.reply(f"❌ {error_msg}\n\n{step.question}")
            return "CONTINUE"

        # 驗證通過，儲存值
        draft[step.field] = value
        next_step = current_step + 1

        # 檢查是否最後一題
        if next_step >= len(self.steps):
            store.set_service_state(uid, self.name, None, draft, None)
            self.on_complete(uid, draft, store, line)
            return "DONE"

        # 繼續下一題
        store.set_service_state(uid, self.name, next_step, draft, None)
        self._show_step(uid, next_step, store, line)
        return "CONTINUE"

    def on_complete(self, uid: str, draft: Dict, store, line) -> None:
        """問答完成後執行（子類覆蓋此方法）"""
        raise NotImplementedError("Subclass must implement on_complete()")

    def _show_step(self, uid: str, step_index: int, store, line) -> None:
        """顯示指定步驟的問題"""
        if step_index < 0 or step_index >= len(self.steps):
            return
        step = self.steps[step_index]
        prompt = step.question
        if step.optional:
            prompt += "\n（輸入『跳過』略過）"
        line.reply(prompt)
