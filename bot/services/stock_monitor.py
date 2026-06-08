"""
stock_monitor.py — 股票監控服務
四步問答流程：股票代號→股數→均價→停損價（選填）
"""

from typing import Optional, Tuple, Any

from bot.services.base import Step, ScriptedService
from bot.data.fugle_client import FugleClient


class StockMonitorService(ScriptedService):
    """股票監控服務"""

    def __init__(self):
        self.name = "stock_monitor"
        self.steps = [
            Step(
                field="stock_id",
                question="請問要監控哪支股票？（輸入名稱或代號）",
                validate=self._validate_stock,
                optional=False,
            ),
            Step(
                field="total_shares",
                question="持有幾股？（例如：100）",
                validate=self._validate_shares,
                optional=False,
            ),
            Step(
                field="cost_price",
                question="買入均價是多少元？",
                validate=self._validate_price,
                optional=False,
            ),
            Step(
                field="stop_loss_moving",
                question="停損價是多少元？（輸入『跳過』略過）",
                validate=self._validate_price,
                optional=True,
            ),
        ]

    def _validate_stock(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        """驗證股票代號或名稱"""
        client = FugleClient()
        result = client.verify_stock(text)
        if not result:
            return False, None, "找不到此股票，請重新輸入名稱或代號"
        return True, result, ""

    def _validate_shares(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        """驗證股數（正整數）"""
        try:
            shares = int(text)
            if shares < 1:
                return False, None, "請輸入正整數，例如：100"
            return True, shares, ""
        except ValueError:
            return False, None, "請輸入正整數，例如：100"

    def _validate_price(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        """驗證價格"""
        try:
            price = float(text)
            if price <= 0:
                return False, None, "請輸入正數，例如：900"
            return True, price, ""
        except ValueError:
            return False, None, "請輸入數字，例如：900"

    def on_complete(self, uid, draft, store, line, reply_token=""):
        # type: (str, dict, Any, Any, str) -> None
        """完成後顯示確認卡片"""
        stock_info = draft.get("stock_id", {})
        stock_id = stock_info.get("stock_id") if isinstance(stock_info, dict) else stock_info
        stock_name = stock_info.get("stock_name", "") if isinstance(stock_info, dict) else ""

        total_shares = draft.get("total_shares")
        cost_price = draft.get("cost_price")
        stop_loss = draft.get("stop_loss_moving")

        # 取得最新報價
        client = FugleClient()
        quote = client.get_quote(stock_id)
        if not quote:
            line.reply(reply_token, "⚠️ 無法取得即時報價，請稍後重試")
            return

        close_price = quote["close_price"]
        change_pct = quote["change_pct"]

        # 計算停損百分比
        stop_pct = ""
        if stop_loss and cost_price:
            stop_pct = "（{:+.2f}%）".format((stop_loss - cost_price) / cost_price * 100)

        msg = (
            "📋 確認監控條件\n\n"
            "股票：{}（{}）\n"
            "收盤：{} 元（{:+.2f}%）\n"
            "持股：{} 股\n"
            "均價：{} 元\n"
            "停損：{} {}\n\n"
            "輸入「確認」開始監控\n"
            "輸入「取消」重新設定"
        ).format(
            stock_name, stock_id,
            close_price, change_pct,
            total_shares,
            cost_price,
            stop_loss or "未設定", stop_pct,
        )

        # 切換狀態為等待確認
        store.set_service_state(uid, "stock_monitor_confirm", None, draft, None)
        line.reply(reply_token, msg)
