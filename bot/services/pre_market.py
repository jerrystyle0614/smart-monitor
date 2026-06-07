"""
pre_market.py — 盤前分析服務
單步問答：選股票 → 立即執行分析並推播
"""

from typing import Tuple, Any

from bot.services.base import Step, ScriptedService
from bot.data.fugle_client import FugleClient
from bot.analysis_runner import run_analysis_for_user, AnalysisMode


def push_to_line(uid, message, line):
    # type: (str, str, Any) -> None
    """LINE push 封裝（可被測試 patch 覆蓋）"""
    line.push(uid, message)


class PreMarketService(ScriptedService):
    """盤前分析服務"""

    def __init__(self):
        self.name = "pre_market"
        self.steps = [
            Step(
                field="stock_id",
                question="請問要分析哪支股票？（輸入名稱或代號）",
                validate=self._validate_stock,
                optional=False,
            ),
        ]

    def _validate_stock(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        """驗證股票"""
        client = FugleClient()
        result = client.verify_stock(text)
        if not result:
            return False, None, "找不到此股票，請重新輸入"
        return True, result, ""

    def on_complete(self, uid, draft, store, line):
        # type: (str, dict, Any, Any) -> None
        """執行分析並推播"""
        stock_info = draft.get("stock_id", {})
        stock_id = stock_info.get("stock_id") if isinstance(stock_info, dict) else stock_info
        stock_name = stock_info.get("stock_name", "") if isinstance(stock_info, dict) else ""

        # 執行分析
        result = run_analysis_for_user(
            {"stock_id": stock_id, "stock_name": stock_name, "cost_price": None},
            {},
            AnalysisMode.PREMARKET,
        )

        if result:
            push_to_line(uid, result["title"], line)
            push_to_line(uid, result["message"], line)

        store.clear_service_state(uid)
