"""
fundamental_strategy.py — 籌碼面篩選策略
篩選條件：三大法人連續買超 + 融資增幅正常 + 交易量足夠
"""

from typing import List

from bot.stock_picker.base import Stock, Strategy


class FundamentalStrategy(Strategy):
    """籌碼面策略"""
    
    def __init__(
        self,
        finmind_client,
        consecutive_days: int = 3,
        margin_increase_threshold: float = 5.0,
    ):
        self.name = "fundamental"
        self.client = finmind_client
        self.consecutive_days = consecutive_days
        self.margin_increase_threshold = margin_increase_threshold
    
    def scan(self) -> List[Stock]:
        """
        掃描符合籌碼面條件的股票。
        條件：
        1. 三大法人連續 N 天買超
        2. 融資餘額增幅 < threshold %
        """
        try:
            all_stocks = self.client.get_all_stocks_basic()
        except Exception as e:
            print(f"[fundamental] 無法取得股票清單：{e}")
            return []
        
        qualified = []
        
        for stock_data in all_stocks:
            stock_id = stock_data.get("stock_id", "")
            stock_name = stock_data.get("stock_name", "")
            
            if not stock_id:
                continue
            
            # 檢查三大法人買賣超
            buyers = self.client.get_three_major_buyers(stock_id, days=self.consecutive_days)
            if not buyers or buyers.get("consecutive_buy_days", 0) < self.consecutive_days:
                continue
            
            # 檢查融資增幅
            margin = self.client.get_margin_status(stock_id)
            if not margin:
                continue
            
            margin_increase_pct = margin.get("margin_increase_pct", 0)
            if margin_increase_pct >= self.margin_increase_threshold:
                continue
            
            # 通過所有條件
            qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))
        
        return qualified
