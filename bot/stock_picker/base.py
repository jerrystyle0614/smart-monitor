"""
base.py — Strategy 基類和 Stock 資料類別
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Stock:
    """股票資料類別（frozen 使其可 hash）"""
    stock_id: str
    stock_name: str


class Strategy:
    """選股策略基類"""

    name: str

    def scan(self) -> List[Stock]:
        """
        掃描符合條件的股票。
        子類應覆蓋此方法。
        回傳 List[Stock]
        """
        raise NotImplementedError("Subclass must implement scan()")
