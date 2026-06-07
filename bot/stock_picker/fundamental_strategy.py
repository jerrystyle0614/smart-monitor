"""
fundamental_strategy.py — 籌碼面篩選策略
篩選條件：三大法人買賣超（TEJ）+ 融資餘額變化（FinMind）
"""

from typing import List

from bot.stock_picker.base import Stock, Strategy


class FundamentalStrategy(Strategy):
    """籌碼面策略：三大法人 + 融資餘額篩選"""

    def __init__(
        self,
        exchange_client,
        stock_list_provider,
        use_three_major: bool = True,
        consecutive_buy_days: int = 1,
        margin_increase_threshold: float = 5.0,
    ):
        """
        Args:
            exchange_client: ExchangeClient instance
            stock_list_provider: callable that returns stock list
            use_three_major: 是否優先使用三大法人篩選（如果 TEJ 可用）
            consecutive_buy_days: 三大法人連續買超天數（預設 1 天）
            margin_increase_threshold: 融資增幅閾值（%）
        """
        self.name = "fundamental"
        self.exchange_client = exchange_client
        self.stock_list_provider = stock_list_provider
        self.use_three_major = use_three_major
        self.consecutive_buy_days = consecutive_buy_days
        self.margin_increase_threshold = margin_increase_threshold

    def scan(self) -> List[Stock]:
        """
        掃描符合籌碼面條件的股票。

        優先邏輯：
        1. 如果 TEJ 可用：篩選三大法人連續買超 + 融資增幅穩定
        2. 如果 TEJ 不可用：單純篩選融資增幅穩定
        """
        try:
            all_stocks = self.stock_list_provider()
            if not all_stocks:
                print("[fundamental] 股票清單為空")
                return []
        except Exception as e:
            print(f"[fundamental] 無法取得股票清單：{e}")
            return []

        qualified = []

        for stock_data in all_stocks:
            stock_id = stock_data.get("stock_id", "")
            stock_name = stock_data.get("stock_name", "")

            if not stock_id:
                continue

            # 條件 1: 三大法人買賣超（可選，取決於 TEJ 可用性）
            if self.use_three_major:
                buyers = self.exchange_client.get_three_major_buyers(stock_id)
                if not buyers or buyers.get("consecutive_buy_days", 0) < self.consecutive_buy_days:
                    continue

            # 條件 2: 融資餘額增幅穩定
            margin = self.exchange_client.get_margin_status(stock_id)
            if not margin:
                continue

            margin_increase_pct = margin.get("margin_increase_pct", 0)
            if margin_increase_pct >= self.margin_increase_threshold:
                continue

            # 通過所有條件
            qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))

        return qualified
