"""
fundamental_strategy.py — 籌碼面篩選策略
篩選條件：融資餘額變化（替代三大法人，TWSE 官方 API 無個股端點）
"""

from typing import List

from bot.stock_picker.base import Stock, Strategy


class FundamentalStrategy(Strategy):
    """籌碼面策略：融資餘額篩選（籌碼面近似指標）"""

    def __init__(
        self,
        exchange_client,
        stock_list_provider,
        margin_increase_threshold: float = 5.0,
    ):
        """
        Args:
            exchange_client: ExchangeClient instance
            stock_list_provider: callable that returns stock list
            margin_increase_threshold: 融資增幅閾值（%）
                                        增幅 < threshold 表示融資相對穩定
        """
        self.name = "fundamental"
        self.exchange_client = exchange_client
        self.stock_list_provider = stock_list_provider
        self.margin_increase_threshold = margin_increase_threshold

    def scan(self) -> List[Stock]:
        """
        掃描符合籌碼面條件的股票。
        條件：融資餘額增幅 < threshold（表示籌碼相對穩定）
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

            # 檢查融資餘額
            margin = self.exchange_client.get_margin_status(stock_id)
            if not margin:
                continue

            margin_increase_pct = margin.get("margin_increase_pct", 0)
            # 融資增幅過高表示散戶跟風，篩選掉
            if margin_increase_pct >= self.margin_increase_threshold:
                continue

            # 通過條件
            qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))

        return qualified
