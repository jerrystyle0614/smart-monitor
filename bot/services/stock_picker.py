"""
stock_picker.py — 選股推薦服務（ScriptedService 子類）
用戶查看推薦、管理訂閱
"""

import json
from pathlib import Path
from typing import Optional, Dict, List

from bot.services.base import ScriptedService, Step


def load_picker_cache() -> Optional[Dict]:
    """載入今日選股推薦快取"""
    cache_path = Path("data") / "stock_picker_cache.json"
    if not cache_path.exists():
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[stock_picker] 無法載入快取：{e}")
        return None


class StockPickerService(ScriptedService):
    """選股推薦服務"""
    
    def __init__(self):
        self.name = "stock_picker"
        self.steps = [
            Step(
                field="action",
                question="選擇操作：",
                validate=self._validate_action,
                optional=False,
            ),
        ]
    
    def _validate_action(self, text: str):
        """驗證用戶操作"""
        valid_actions = ["詳細", "訂閱", "取消訂閱"]
        if text in valid_actions:
            return True, text, ""
        return False, None, "請輸入『詳細』、『訂閱』或『取消訂閱』"
    
    def start(self, uid: str, store, line, reply_token: str = "") -> None:
        """進入選股推薦，顯示推薦清單"""
        cache = load_picker_cache()

        if not cache or not cache.get("stocks"):
            line.reply(reply_token, "📈 今日選股推薦\n\n掃描尚未開始或無符合條件的股票。")
            store.clear_service_state(uid)
            return

        stocks = cache.get("stocks", [])
        msg = f"📈 Smart Monitor 每日選股推薦（{cache.get('date', '未知')}）\n\n"
        msg += f"掃描發現 {len(stocks)} 支值得關注的股票：\n\n"

        for i, stock in enumerate(stocks[:10], 1):  # 最多顯示 10 支
            stock_id = stock.get("stock_id", "")
            stock_name = stock.get("stock_name", "")
            reasons = stock.get("reasons", {})
            msg += f"{i}️⃣ {stock_name}（{stock_id}）\n"
            if reasons.get("fundamental") or reasons.get("technical"):
                msg += "   理由："
                if reasons.get("fundamental"):
                    msg += f"{reasons['fundamental']}, "
                if reasons.get("technical"):
                    msg += reasons["technical"]
                msg = msg.rstrip(", ") + "\n"
            msg += "\n"

        msg += "輸入『詳細 [數字]』查看詳細說明\n"
        msg += "輸入『訂閱』開始每日推播\n"
        msg += "輸入『取消訂閱』停止推播\n"
        msg += "輸入『取消』回到主選單"

        line.reply(reply_token, msg)
        store.set_service_state(uid, self.name, 0, {}, None)

    def on_complete(self, uid: str, draft: Dict, store, line, reply_token: str = "") -> None:
        """處理訂閱/查看詳細等操作"""
        action = draft.get("action")

        if action == "訂閱":
            store.set_subscription(uid, "stock_picker", True)
            line.reply(reply_token, "✅ 已訂閱每日選股推薦（08:00 推播）")
        elif action == "取消訂閱":
            store.set_subscription(uid, "stock_picker", False)
            line.reply(reply_token, "❌ 已取消每日選股推薦")
        elif action == "詳細":
            line.reply(reply_token, "詳細功能開發中...")

        store.clear_service_state(uid)
