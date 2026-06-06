"""
state_machine.py — 對話狀態機
管理每位使用者的對話流程：IDLE → COLLECTING → CONFIRMING → MONITORING
"""

from typing import Optional

MONITOR_KEYWORDS = ["監控", "持股", "買進", "買了", "追蹤", "觀察"]

# 必填欄位（缺少時必須追問）
REQUIRED_FIELDS = ["total_shares", "cost_price"]

# 選填欄位（缺少時不追問，保留 None）
OPTIONAL_FIELDS = ["stop_loss_moving", "target_stage_1", "target_stage_2"]

MISSING_FIELDS = REQUIRED_FIELDS  # 向外暴露供測試用

# 各欄位的追問問題與解析方式
FIELD_QUESTIONS = {
    "total_shares": "請問你買了幾張？（例如：5）",
    "cost_price":   "請問均價是多少元？（例如：64.86）",
}


class StateMachine:
    """單一使用者的對話狀態機實例"""

    def __init__(self):
        self.state = "IDLE"
        self.pending_config: dict = {}
        self.current_question: Optional[str] = None  # 目前正在追問的欄位名稱

    def should_parse(self, text: str) -> bool:
        """判斷訊息是否應觸發 Claude 解析（包含監控關鍵字）"""
        return any(kw in text for kw in MONITOR_KEYWORDS)

    def get_missing_fields(self) -> list[str]:
        """回傳目前 pending_config 中仍缺少的必填欄位名稱列表"""
        return [
            f for f in REQUIRED_FIELDS
            if self.pending_config.get(f) is None
        ]

    def next_question(self) -> str:
        """取得下一個要追問的問題文字，並記錄 current_question"""
        missing = self.get_missing_fields()
        if not missing:
            return ""
        self.current_question = missing[0]
        return FIELD_QUESTIONS[self.current_question]

    def apply_answer(self, text: str) -> bool:
        """將使用者對追問的回答套用到 pending_config，回傳 True 表示成功，False 表示格式錯誤"""
        field = self.current_question
        if field is None:
            return True

        try:
            text = text.strip()
            if field == "total_shares":
                # 使用者輸入張數，轉換為股數（1 張 = 1000 股）
                lots = float(text.replace("張", "").strip())
                self.pending_config["total_shares"] = int(lots * 1000)
            elif field in ("cost_price", "stop_loss_moving",
                           "target_stage_1", "target_stage_2"):
                self.pending_config[field] = float(text.replace("元", "").strip())
            self.current_question = None
            return True
        except ValueError:
            # current_question 保持不變，handlers.py 可以重問同一個問題
            return False

    def build_confirm_card(self, close_price: float = None, change_pct: float = None) -> str:
        """建立確認卡片文字，可選傳入即時收盤價與漲跌幅"""
        cfg = self.pending_config
        stock_id   = cfg.get("stock_id", "")
        stock_name = cfg.get("stock_name", "")
        shares     = cfg.get("total_shares", 0)
        cost       = cfg.get("cost_price")
        stop       = cfg.get("stop_loss_moving")
        t1         = cfg.get("target_stage_1")
        t2         = cfg.get("target_stage_2")

        lots = shares // 1000 if shares else 0

        def _pct(price):
            if price is None or cost is None or cost == 0:
                return ""
            return f"（{(price - cost) / cost * 100:+.2f}%）"

        stock_display = f"{stock_id} {stock_name}" if stock_id else f"⚠️ 代號未知（{stock_name}）"

        if close_price is not None:
            sign = "+" if (change_pct or 0) >= 0 else ""
            pct_str = f"{sign}{change_pct:.2f}%" if change_pct is not None else ""
            close_line = f"收盤價：{close_price} 元 {pct_str}".strip()
        else:
            close_line = "收盤價：查詢中"

        lines = [
            "📋 請確認監控條件\n",
            f"股票：{stock_display}",
            close_line,
            f"持股：{'未設定' if not shares else f'{lots} 張（{shares:,} 股）'}",
            f"均價：{'未設定' if cost is None else f'{cost} 元'}",
            f"停損：{'未設定' if stop is None else f'{stop} 元{_pct(stop)}'}",
            f"目標一：{'未設定' if t1 is None else f'{t1} 元{_pct(t1)}'}",
            f"目標二：{'未設定' if t2 is None else f'{t2} 元{_pct(t2)}'}",
            "\n輸入「確認」開始監控，或「重新輸入」重來。",
            "\n📝 可直接修改欄位：",
            "修改股票 台積電 ／ 修改持股 5",
            "修改均價 62 ／ 修改停損 60",
            "修改目標 80 ／ 修改目標二 90",
        ]
        return "\n".join(lines)
