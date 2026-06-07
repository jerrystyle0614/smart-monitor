"""test_stock_picker_base.py — Strategy 基類和 Stock 資料類別測試"""
import os
import pytest
from typing import List

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.stock_picker.base import Stock, Strategy


class MockStrategy(Strategy):
    """測試用策略"""
    def __init__(self):
        self.name = "mock"

    def scan(self) -> List[Stock]:
        return [
            Stock(stock_id="2330", stock_name="台積電"),
            Stock(stock_id="2454", stock_name="聯發科"),
        ]


def test_stock_dataclass():
    """Stock 應為資料類別"""
    stock = Stock(stock_id="2330", stock_name="台積電")
    assert stock.stock_id == "2330"
    assert stock.stock_name == "台積電"


def test_strategy_abstract_scan():
    """Strategy 的 scan() 應為抽象方法"""
    with pytest.raises(NotImplementedError):
        strategy = Strategy()
        strategy.scan()


def test_mock_strategy_scan():
    """MockStrategy 應實作 scan()"""
    strategy = MockStrategy()
    result = strategy.scan()
    assert len(result) == 2
    assert result[0].stock_id == "2330"
    assert isinstance(result[0], Stock)


def test_stock_equality():
    """相同 stock_id 的 Stock 應相等"""
    s1 = Stock(stock_id="2330", stock_name="台積電")
    s2 = Stock(stock_id="2330", stock_name="台積電")
    assert s1 == s2


def test_stock_hashable():
    """Stock 應可用於 set"""
    s1 = Stock(stock_id="2330", stock_name="台積電")
    s2 = Stock(stock_id="2454", stock_name="聯發科")
    stock_set = {s1, s2}
    assert len(stock_set) == 2
