"""
state_machine.py — 對話狀態機
管理每位使用者的對話流程：IDLE → PARSING → COLLECTING → CONFIRMING → MONITORING
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

    def apply_answer(self, text: str) -> None:
        """將使用者對追問的回答套用到 pending_config"""
        field = self.current_question
        if field is None:
            return

        text = text.strip()

        if field == "total_shares":
            # 使用者輸入張數，轉換為股數（1 張 = 1000 股）
            lots = float(text.replace("張", "").strip())
            self.pending_config["total_shares"] = int(lots * 1000)
        elif field in ("cost_price", "stop_loss_moving",
                       "target_stage_1", "target_stage_2"):
            self.pending_config[field] = float(text.replace("元", "").strip())

        self.current_question = None

    def build_confirm_card(self) -> str:
        """建立確認卡片文字"""
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

        lines = [
            "📋 請確認監控條件\n",
            f"股票：{stock_id} {stock_name}",
            f"持股：{lots} 張（{shares:,} 股）",
            f"均價：{cost} 元",
            f"停損：{stop if stop else '未設定'} 元{_pct(stop)}",
            f"目標一：{t1 if t1 else '未設定'} 元{_pct(t1)}",
            f"目標二：{t2 if t2 else '未設定'} 元{_pct(t2)}",
            "\n輸入「確認」開始監控，或「重新輸入」重來。",
        ]
        return "\n".join(lines)
