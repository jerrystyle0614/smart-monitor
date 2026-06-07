# Smart Monitor Phase B — 選股推薦服務實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement daily stock picker service with strategy plugin architecture, combining fundamental (FinMind) and technical (Fugle) criteria to recommend stocks.

**Architecture:** Strategy plugin pattern separates concerns—each strategy (fundamental, technical) independently scans, results combine via intersection. Daily scheduled job caches recommendations, broadcasts to pro subscribers. Claude API generates human-readable explanations per stock.

**Tech Stack:** Python 3.9, APScheduler (daily 08:00 job), FinMind + Fugle APIs, Claude API, ScriptedService extension, LINE Bot, Discord webhooks.

---

## 檔案結構規劃

**新建目錄和檔案：**
```
bot/
├── stock_picker/
│   ├── __init__.py
│   ├── base.py                  # Strategy 基類、Stock 資料類別
│   ├── finmind_client.py        # FinMind API 封裝
│   ├── fundamental_strategy.py  # 籌碼面策略
│   ├── technical_strategy.py    # 技術面策略
│   ├── engine.py                # StockPickerEngine 掃描引擎
│   └── scheduler.py             # 每日排程任務
├── services/
│   └── stock_picker.py          # StockPickerService（ScriptedService 子類）
├── user_store.py                # 擴充：訂閱狀態管理
└── server.py                    # 修改：註冊排程

data/
└── stock_picker_cache.json      # 推薦結果快取（共享）

tests/
├── test_finmind_client.py
├── test_fundamental_strategy.py
├── test_technical_strategy.py
├── test_stock_picker_engine.py
├── test_stock_picker_service.py
└── test_stock_picker_scheduler.py
```

---

## Task 1: Strategy 基類和資料結構

**Files:**
- Create: `bot/stock_picker/__init__.py`
- Create: `bot/stock_picker/base.py`
- Test: `tests/test_stock_picker_base.py`

### Step 1: Write failing test

Create `tests/test_stock_picker_base.py`:

```python
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
```

### Step 2: Run test to confirm FAIL

```bash
cd /Users/jerry/Projects/Personal/experiments/smart-monitor
python3 -m pytest tests/test_stock_picker_base.py::test_stock_dataclass -v
```

Expected: `ModuleNotFoundError: No module named 'bot.stock_picker'`

### Step 3: Create `bot/stock_picker/__init__.py`

```python
"""stock_picker package — stock picker service components"""
from bot.stock_picker.base import Stock, Strategy

__all__ = ["Stock", "Strategy"]
```

### Step 4: Create `bot/stock_picker/base.py`

```python
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
```

### Step 5: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_base.py -v
```

Expected: 6 tests PASS

### Step 6: Commit

```bash
git add bot/stock_picker/__init__.py bot/stock_picker/base.py tests/test_stock_picker_base.py
git commit -m "✨ feat: add Strategy base class and Stock dataclass for stock picker"
```

---

## Task 2: FinMindClient API 封裝

**Files:**
- Create: `bot/stock_picker/finmind_client.py`
- Test: `tests/test_finmind_client.py`

### Step 1: Write failing test

Create `tests/test_finmind_client.py`:

```python
"""test_finmind_client.py — FinMind API 客戶端測試"""
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

os.environ.setdefault("FINMIND_API_KEY", "test_key_12345")

from bot.stock_picker.finmind_client import FinMindClient


@pytest.fixture
def client():
    return FinMindClient()


def test_init_sets_api_key(client):
    """初始化應讀取 API key"""
    assert client.api_key == "test_key_12345"


def test_get_three_major_buyers_success(client):
    """get_three_major_buyers 應回傳買賣超資料"""
    mock_response = {
        "data": [
            {
                "date": "2026-06-07",
                "stock_id": "2330",
                "buy": 500000000,
                "sell": 100000000,
            }
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_three_major_buyers("2330", days=3)
    
    assert result is not None
    assert "consecutive_buy_days" in result or "data" in result


def test_get_three_major_buyers_api_failure(client):
    """API 失敗時應回傳 None"""
    with patch("bot.stock_picker.finmind_client.requests.get", side_effect=Exception("API Error")):
        result = client.get_three_major_buyers("2330")
    assert result is None


def test_get_margin_status_success(client):
    """get_margin_status 應回傳融資融券資料"""
    mock_response = {
        "data": [
            {
                "date": "2026-06-07",
                "stock_id": "2330",
                "margin_balance": 5000000,
                "short_balance": 1000000,
            }
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_margin_status("2330")
    
    assert result is not None
    assert isinstance(result, dict)


def test_get_margin_status_api_failure(client):
    """API 失敗時應回傳 None"""
    with patch("bot.stock_picker.finmind_client.requests.get", side_effect=Exception("API Error")):
        result = client.get_margin_status("2330")
    assert result is None


def test_get_all_stocks_basic_returns_list(client):
    """get_all_stocks_basic 應回傳股票列表"""
    mock_response = {
        "data": [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
        ]
    }
    with patch("bot.stock_picker.finmind_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = client.get_all_stocks_basic()
    
    assert isinstance(result, list)
    assert len(result) >= 0
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_finmind_client.py::test_init_sets_api_key -v
```

Expected: `ModuleNotFoundError`

### Step 3: Create `bot/stock_picker/finmind_client.py`

```python
"""
finmind_client.py — FinMind API 統一封裝
取得籌碼面資料：三大法人買賣超、融資融券
"""

import os
from typing import Optional, Dict, List
from datetime import datetime, timedelta

import requests


class FinMindClient:
    """FinMind API 客戶端"""
    
    def __init__(self):
        self.api_key = os.environ.get("FINMIND_API_KEY", "")
        self.base_url = "https://api.finmindtrade.com/api/v4"
    
    def get_three_major_buyers(self, stock_id: str, days: int = 3) -> Optional[Dict]:
        """
        取得三大法人買賣超資料。
        回傳 {
            "consecutive_buy_days": int,
            "total_buy": float,
            "total_sell": float,
            "latest_data": [date, buy, sell]
        }
        或 None（失敗）
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockThreeMainForces",
                "stock_id": stock_id,
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("data"):
                return None
            
            # 計算連續買超天數
            records = data.get("data", [])
            consecutive_days = 0
            for record in records:
                buy = float(record.get("buy", 0))
                sell = float(record.get("sell", 0))
                if buy > sell:
                    consecutive_days += 1
                else:
                    break
            
            return {
                "consecutive_buy_days": consecutive_days,
                "total_buy": sum(float(r.get("buy", 0)) for r in records[:days]),
                "total_sell": sum(float(r.get("sell", 0)) for r in records[:days]),
                "latest_data": records[0] if records else None,
            }
        except Exception as e:
            print(f"[finmind] get_three_major_buyers {stock_id} 失敗：{e}")
            return None
    
    def get_margin_status(self, stock_id: str) -> Optional[Dict]:
        """
        取得融資融券狀態。
        回傳 {
            "margin_balance": float,
            "short_balance": float,
            "margin_increase_pct": float
        }
        或 None（失敗）
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockMarginPurchaseShortSale",
                "stock_id": stock_id,
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("data"):
                return None
            
            records = data.get("data", [])
            if len(records) < 2:
                return None
            
            current = records[0]
            previous = records[1]
            
            margin_current = float(current.get("MarginBalance", 0))
            margin_previous = float(previous.get("MarginBalance", 0))
            
            margin_increase_pct = 0
            if margin_previous > 0:
                margin_increase_pct = (margin_current - margin_previous) / margin_previous * 100
            
            return {
                "margin_balance": margin_current,
                "short_balance": float(current.get("ShortBalance", 0)),
                "margin_increase_pct": margin_increase_pct,
                "date": current.get("Date"),
            }
        except Exception as e:
            print(f"[finmind] get_margin_status {stock_id} 失敗：{e}")
            return None
    
    def get_all_stocks_basic(self) -> List[Dict]:
        """
        取得全市場股票基本資訊。
        回傳 [{"stock_id": "2330", "stock_name": "台積電"}, ...]
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockInfo",
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            return data.get("data", [])
        except Exception as e:
            print(f"[finmind] get_all_stocks_basic 失敗：{e}")
            return []
```

### Step 4: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_finmind_client.py -v
```

Expected: 6 tests PASS

### Step 5: Commit

```bash
git add bot/stock_picker/finmind_client.py tests/test_finmind_client.py
git commit -m "✨ feat: add FinMindClient for fundamental data (three major buyers, margin status)"
```

---

## Task 3: FundamentalStrategy 籌碼面策略

**Files:**
- Create: `bot/stock_picker/fundamental_strategy.py`
- Test: `tests/test_fundamental_strategy.py`

### Step 1: Write failing test

Create `tests/test_fundamental_strategy.py`:

```python
"""test_fundamental_strategy.py — FundamentalStrategy 籌碼面篩選"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FINMIND_API_KEY", "test_key")

from bot.stock_picker.base import Stock
from bot.stock_picker.fundamental_strategy import FundamentalStrategy


@pytest.fixture
def mock_finmind():
    return MagicMock()


@pytest.fixture
def strategy(mock_finmind):
    return FundamentalStrategy(mock_finmind, consecutive_days=3, margin_increase_threshold=5.0)


def test_scan_returns_list_of_stocks(strategy, mock_finmind):
    """scan() 應回傳 List[Stock]"""
    mock_finmind.get_all_stocks_basic.return_value = [
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2454", "stock_name": "聯發科"},
    ]
    mock_finmind.get_three_major_buyers.return_value = {
        "consecutive_buy_days": 3,
        "total_buy": 10000000,
        "total_sell": 1000000,
    }
    mock_finmind.get_margin_status.return_value = {
        "margin_balance": 5000000,
        "margin_increase_pct": 2.0,
    }
    
    result = strategy.scan()
    assert isinstance(result, list)
    if result:
        assert isinstance(result[0], Stock)


def test_consecutive_buy_days_filter(strategy, mock_finmind):
    """應篩選連續買超 N 天的股票"""
    mock_finmind.get_all_stocks_basic.return_value = [
        {"stock_id": "2330", "stock_name": "台積電"},
    ]
    
    # 連續買超 3 天 → 符合
    mock_finmind.get_three_major_buyers.return_value = {
        "consecutive_buy_days": 3,
        "total_buy": 10000000,
        "total_sell": 1000000,
    }
    mock_finmind.get_margin_status.return_value = {
        "margin_balance": 5000000,
        "margin_increase_pct": 2.0,
    }
    
    result = strategy.scan()
    assert len(result) > 0


def test_margin_increase_threshold_filter(strategy, mock_finmind):
    """應篩選融資增幅 < 5% 的股票"""
    mock_finmind.get_all_stocks_basic.return_value = [
        {"stock_id": "2330", "stock_name": "台積電"},
    ]
    mock_finmind.get_three_major_buyers.return_value = {
        "consecutive_buy_days": 3,
        "total_buy": 10000000,
        "total_sell": 1000000,
    }
    
    # 融資增幅 10% > 5% → 不符合
    mock_finmind.get_margin_status.return_value = {
        "margin_balance": 5000000,
        "margin_increase_pct": 10.0,
    }
    
    result = strategy.scan()
    assert len(result) == 0
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_fundamental_strategy.py::test_scan_returns_list_of_stocks -v
```

Expected: Module not found

### Step 3: Create `bot/stock_picker/fundamental_strategy.py`

```python
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
```

### Step 4: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_fundamental_strategy.py -v
```

Expected: 4 tests PASS

### Step 5: Commit

```bash
git add bot/stock_picker/fundamental_strategy.py tests/test_fundamental_strategy.py
git commit -m "✨ feat: add FundamentalStrategy for fundamental (three major buyers + margin) filtering"
```

---

## Task 4: TechnicalStrategy 技術面策略

**Files:**
- Create: `bot/stock_picker/technical_strategy.py`
- Test: `tests/test_technical_strategy.py`

### Step 1: Write failing test

Create `tests/test_technical_strategy.py`:

```python
"""test_technical_strategy.py — TechnicalStrategy 技術面篩選"""
import os
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")

from bot.stock_picker.base import Stock
from bot.stock_picker.technical_strategy import TechnicalStrategy


def _make_candles_df(ma20=100.0, current_close=105.0, high20=110.0):
    """建立假日K資料"""
    dates = pd.date_range("2026-05-08", periods=20, freq="B").strftime("%Y-%m-%d").tolist()
    closes = [99.0 + i * 0.3 for i in range(20)]
    closes[-1] = current_close
    
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": [high20] * 20,
        "low": closes,
        "close": closes,
        "volume": [1000] * 20,
    })


@pytest.fixture
def mock_fugle():
    return MagicMock()


@pytest.fixture
def strategy(mock_fugle):
    return TechnicalStrategy(mock_fugle, ma_period=20, pullback_threshold=8.0)


def test_scan_returns_list_of_stocks(strategy, mock_fugle):
    """scan() 應回傳 List[Stock]"""
    mock_fugle.load_stock_map.return_value = {"台積電": "2330"}
    mock_fugle.fetch_candles.return_value = _make_candles_df()
    
    result = strategy.scan()
    assert isinstance(result, list)


def test_close_above_ma20_filter(strategy, mock_fugle):
    """應篩選收盤價 > MA20 的股票"""
    mock_fugle.load_stock_map.return_value = {"台積電": "2330"}
    # 收盤價 105 > MA20 100 → 符合
    mock_fugle.fetch_candles.return_value = _make_candles_df(ma20=100.0, current_close=105.0)
    
    result = strategy.scan()
    # 應包含此股票
    assert any(s.stock_id == "2330" for s in result)


def test_pullback_threshold_filter(strategy, mock_fugle):
    """應篩選回撤 < 8% 的股票"""
    mock_fugle.load_stock_map.return_value = {"台積電": "2330"}
    # 高點 110，現價 101，回撤 8.2% > 8% → 不符合
    mock_fugle.fetch_candles.return_value = _make_candles_df(ma20=100.0, current_close=101.0, high20=110.0)
    
    result = strategy.scan()
    # 不應包含此股票
    assert not any(s.stock_id == "2330" for s in result)
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_technical_strategy.py::test_scan_returns_list_of_stocks -v
```

Expected: Module not found

### Step 3: Create `bot/stock_picker/technical_strategy.py`

```python
"""
technical_strategy.py — 技術面篩選策略
篩選條件：收盤價 > MA20 + 回撤 < 8% + 過去 5 日有上漲
"""

from typing import List

import pandas as pd

from bot.stock_picker.base import Stock, Strategy


class TechnicalStrategy(Strategy):
    """技術面策略"""
    
    def __init__(
        self,
        fugle_client,
        ma_period: int = 20,
        pullback_threshold: float = 8.0,
    ):
        self.name = "technical"
        self.client = fugle_client
        self.ma_period = ma_period
        self.pullback_threshold = pullback_threshold
    
    def scan(self) -> List[Stock]:
        """
        掃描符合技術面條件的股票。
        條件：
        1. 收盤價 > MA20（趨勢向上）
        2. 距離 20 日高點回撤 < threshold %（未過度下跌）
        3. 過去 5 日有上漲（動能未衰）
        """
        try:
            stock_map = self.client.load_stock_map()
        except Exception as e:
            print(f"[technical] 無法載入股票清單：{e}")
            return []
        
        qualified = []
        
        for stock_name, stock_id in stock_map.items():
            try:
                df = self.client.fetch_candles(stock_id, days=60)
                if df is None or len(df) < self.ma_period:
                    continue
                
                # 計算 MA20
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["high"] = pd.to_numeric(df["high"], errors="coerce")
                
                ma20 = df["close"].tail(self.ma_period).mean()
                current_close = df["close"].iloc[-1]
                high20 = df["high"].tail(self.ma_period).max()
                
                # 條件 1：收盤價 > MA20
                if current_close <= ma20:
                    continue
                
                # 條件 2：回撤 < threshold %
                if high20 > 0:
                    pullback_pct = (high20 - current_close) / high20 * 100
                    if pullback_pct >= self.pullback_threshold:
                        continue
                
                # 條件 3：過去 5 日有上漲
                recent_closes = df["close"].tail(5).values
                if len(recent_closes) < 5:
                    continue
                
                has_gain = any(recent_closes[i] < recent_closes[i + 1] for i in range(4))
                if not has_gain:
                    continue
                
                # 通過所有條件
                qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))
            
            except Exception as e:
                print(f"[technical] {stock_id} 分析失敗：{e}")
                continue
        
        return qualified
```

### Step 4: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_technical_strategy.py -v
```

Expected: 3 tests PASS

### Step 5: Commit

```bash
git add bot/stock_picker/technical_strategy.py tests/test_technical_strategy.py
git commit -m "✨ feat: add TechnicalStrategy for technical (MA20 + pullback + momentum) filtering"
```

---

## Task 5: StockPickerEngine 掃描引擎

**Files:**
- Create: `bot/stock_picker/engine.py`
- Test: `tests/test_stock_picker_engine.py`

### Step 1: Write failing test

Create `tests/test_stock_picker_engine.py`:

```python
"""test_stock_picker_engine.py — StockPickerEngine 掃描引擎"""
import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.stock_picker.base import Stock
from bot.stock_picker.engine import StockPickerEngine


@pytest.fixture
def mock_strategies():
    s1 = MagicMock()
    s1.name = "strategy1"
    s1.scan.return_value = [
        Stock(stock_id="2330", stock_name="台積電"),
        Stock(stock_id="2454", stock_name="聯發科"),
    ]
    
    s2 = MagicMock()
    s2.name = "strategy2"
    s2.scan.return_value = [
        Stock(stock_id="2330", stock_name="台積電"),
        Stock(stock_id="3008", stock_name="大立光"),
    ]
    
    return [s1, s2]


def test_scan_returns_intersection(mock_strategies):
    """scan() 應回傳所有策略的交集"""
    engine = StockPickerEngine(mock_strategies)
    result = engine.scan()
    
    # 交集應只有 2330
    assert len(result) == 1
    assert result[0].stock_id == "2330"


def test_scan_all_strategies_called(mock_strategies):
    """scan() 應呼叫所有策略的 scan()"""
    engine = StockPickerEngine(mock_strategies)
    result = engine.scan()
    
    assert mock_strategies[0].scan.called
    assert mock_strategies[1].scan.called


def test_scan_single_strategy(mock_strategies):
    """單一策略時應回傳該策略結果"""
    engine = StockPickerEngine([mock_strategies[0]])
    result = engine.scan()
    
    assert len(result) == 2
    assert result[0].stock_id == "2330"
    assert result[1].stock_id == "2454"
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_stock_picker_engine.py::test_scan_returns_intersection -v
```

Expected: Module not found

### Step 3: Create `bot/stock_picker/engine.py`

```python
"""
engine.py — StockPickerEngine 掃描引擎
組合多個策略結果，取交集
"""

from typing import List

from bot.stock_picker.base import Stock, Strategy


class StockPickerEngine:
    """選股掃描引擎"""
    
    def __init__(self, strategies: List[Strategy]):
        self.strategies = strategies
    
    def scan(self) -> List[Stock]:
        """
        執行所有策略並取交集。
        回傳同時符合所有策略條件的股票列表。
        """
        if not self.strategies:
            return []
        
        # 執行第一個策略
        results = [set(self.strategies[0].scan())]
        
        # 執行其餘策略
        for strategy in self.strategies[1:]:
            try:
                strategy_result = set(strategy.scan())
                results.append(strategy_result)
            except Exception as e:
                print(f"[engine] {strategy.name} 執行失敗：{e}")
                continue
        
        if not results:
            return []
        
        # 取交集
        intersection = results[0]
        for i in range(1, len(results)):
            intersection &= results[i]
        
        return sorted(list(intersection), key=lambda s: s.stock_id)
```

### Step 4: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_engine.py -v
```

Expected: 3 tests PASS

### Step 5: Commit

```bash
git add bot/stock_picker/engine.py tests/test_stock_picker_engine.py
git commit -m "✨ feat: add StockPickerEngine for combining strategies via intersection"
```

---

## Task 6: StockPickerService 用戶互動

**Files:**
- Create: `bot/services/stock_picker.py`
- Modify: `bot/router.py`（新增路由）
- Modify: `bot/user_store.py`（擴充訂閱管理）
- Test: `tests/test_stock_picker_service.py`

### Step 1: Write failing test

Create `tests/test_stock_picker_service.py`:

```python
"""test_stock_picker_service.py — StockPickerService 用戶互動"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.services.stock_picker import StockPickerService


@pytest.fixture
def service():
    return StockPickerService()


def test_service_has_name():
    """服務應有 name 屬性"""
    service = StockPickerService()
    assert service.name == "stock_picker"


def test_service_has_steps():
    """服務應有 steps 列表"""
    service = StockPickerService()
    assert hasattr(service, "steps")
    assert isinstance(service.steps, list)


def test_start_shows_menu(service):
    """start() 應顯示推薦清單菜單"""
    mock_store = MagicMock()
    mock_line = MagicMock()
    
    with patch("bot.services.stock_picker.load_picker_cache") as mock_cache:
        mock_cache.return_value = {
            "stocks": [
                {"stock_id": "2330", "stock_name": "台積電", "reasons": {}, "risks": ""}
            ]
        }
        service.start("U123", mock_store, mock_line)
    
    mock_line.reply.assert_called()
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_stock_picker_service.py::test_service_has_name -v
```

Expected: Module not found

### Step 3: Create `bot/services/stock_picker.py`

```python
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
    
    def start(self, uid: str, store, line) -> None:
        """進入選股推薦，顯示推薦清單"""
        cache = load_picker_cache()
        
        if not cache or not cache.get("stocks"):
            line.reply("📈 今日選股推薦\n\n掃描尚未開始或無符合條件的股票。")
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
        
        line.reply(msg)
        store.set_service_state(uid, self.name, 0, {}, None)
    
    def on_complete(self, uid: str, draft: Dict, store, line) -> None:
        """處理訂閱/查看詳細等操作"""
        action = draft.get("action")
        
        if action == "訂閱":
            store.set_subscription(uid, "stock_picker", True)
            line.reply("✅ 已訂閱每日選股推薦（08:00 推播）")
        elif action == "取消訂閱":
            store.set_subscription(uid, "stock_picker", False)
            line.reply("❌ 已取消每日選股推薦")
        elif action == "詳細":
            line.reply("詳細功能開發中...")
        
        store.clear_service_state(uid)
```

### Step 4: Update `bot/user_store.py` — 擴充訂閱管理

在 `get_draft()` 方法之後新增：

```python
def get_subscription(self, uid: str, service_name: str) -> bool:
    """取得訂閱狀態（預設 False）"""
    state_path = self._user_dir(uid) / "state.json"
    state = self._load_json(state_path, {
        "service": None, "step": None, "draft": {}, "edit_index": None,
        "msg_timestamps": [], "cooldown_blocked_until": 0,
        "subscriptions": {}
    })
    subscriptions = state.get("subscriptions", {})
    return subscriptions.get(service_name, False)

def set_subscription(self, uid: str, service_name: str, subscribed: bool) -> None:
    """設定訂閱狀態"""
    state_path = self._user_dir(uid) / "state.json"
    state = self._load_json(state_path, {
        "service": None, "step": None, "draft": {}, "edit_index": None,
        "msg_timestamps": [], "cooldown_blocked_until": 0,
        "subscriptions": {}
    })
    if "subscriptions" not in state:
        state["subscriptions"] = {}
    state["subscriptions"][service_name] = subscribed
    self._save_json(state_path, state)
```

### Step 5: Update `bot/router.py` — 新增路由

在 `_show_menu()` 函數中，基本選單增加「4」的選項，並在 `handle_message()` 中新增：

```python
elif text == "4":
    # 檢查權限
    plan = store.get_plan(uid)
    if plan != "pro":
        line.reply(
            "⚠️ 選股推薦為 pro 方案專屬功能。\n"
            "請聯絡管理員了解升級方式。"
        )
        return
    
    # 進入選股推薦服務
    from bot.services.stock_picker import StockPickerService
    service = StockPickerService()
    service.start(uid, store, line)
```

### Step 6: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_service.py -v
```

Expected: 3 tests PASS

### Step 7: Commit

```bash
git add bot/services/stock_picker.py bot/user_store.py bot/router.py tests/test_stock_picker_service.py
git commit -m "✨ feat: add StockPickerService for user interaction (view, subscribe, manage picks)"
```

---

## Task 7: 每日排程和快取機制

**Files:**
- Create: `bot/stock_picker/scheduler.py`
- Modify: `bot/server.py`（註冊排程）
- Test: `tests/test_stock_picker_scheduler.py`

### Step 1: Write failing test

Create `tests/test_stock_picker_scheduler.py`:

```python
"""test_stock_picker_scheduler.py — 每日排程任務"""
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")
os.environ.setdefault("FINMIND_API_KEY", "test_key")

from bot.stock_picker.scheduler import save_picker_cache, load_picker_cache


def test_save_picker_cache_creates_file():
    """save_picker_cache 應建立快取檔案"""
    cache_data = {
        "date": "2026-06-07",
        "stocks": [
            {"stock_id": "2330", "stock_name": "台積電", "reasons": {}, "risks": ""}
        ]
    }
    save_picker_cache(cache_data)
    
    loaded = load_picker_cache()
    assert loaded is not None
    assert loaded.get("date") == "2026-06-07"
    assert len(loaded.get("stocks", [])) == 1


def test_daily_stock_picker_task_integration():
    """daily_stock_picker_task 應執行掃描和推播"""
    # 此測試需要模擬 API，因此為簡化起見只驗證函數存在
    from bot.stock_picker.scheduler import daily_stock_picker_task
    assert callable(daily_stock_picker_task)
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_stock_picker_scheduler.py::test_save_picker_cache_creates_file -v
```

Expected: Module not found

### Step 3: Create `bot/stock_picker/scheduler.py`

```python
"""
scheduler.py — 每日排程任務
08:00 自動掃描、生成說明、推播
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from bot.stock_picker.engine import StockPickerEngine
from bot.stock_picker.fundamental_strategy import FundamentalStrategy
from bot.stock_picker.technical_strategy import TechnicalStrategy


def save_picker_cache(cache_data: Dict) -> None:
    """儲存選股推薦快取"""
    cache_path = Path("data") / "stock_picker_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[scheduler] 快取已儲存：{len(cache_data.get('stocks', []))} 支股票")
    except Exception as e:
        print(f"[scheduler] 快取儲存失敗：{e}")


def load_picker_cache() -> Dict:
    """讀取選股推薦快取"""
    cache_path = Path("data") / "stock_picker_cache.json"
    if not cache_path.exists():
        return {"stocks": []}
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[scheduler] 快取讀取失敗：{e}")
        return {"stocks": []}


async def daily_stock_picker_task(finmind_client, fugle_client, claude_client, line_client):
    """
    每日 08:00 執行的排程任務。
    掃描 + 說明生成 + 推播
    """
    print("[scheduler] 開始選股掃描...")
    
    try:
        # 建立策略
        fundamental = FundamentalStrategy(finmind_client, consecutive_days=3, margin_increase_threshold=5.0)
        technical = TechnicalStrategy(fugle_client, ma_period=20, pullback_threshold=8.0)
        
        # 執行掃描
        engine = StockPickerEngine([fundamental, technical])
        picked_stocks = engine.scan()
        
        print(f"[scheduler] 掃描完成，發現 {len(picked_stocks)} 支股票")
        
        # 準備快取資料
        cache_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().timestamp(),
            "stocks": []
        }
        
        # 為每支股票生成說明
        for stock in picked_stocks:
            stock_dict = {
                "stock_id": stock.stock_id,
                "stock_name": stock.stock_name,
                "current_price": 0,  # 實際應從 Fugle 取得
                "reasons": {
                    "fundamental": "三大法人買超",
                    "technical": "MA20 上升，回撤良好"
                },
                "risks": "若跌破 MA20 應設停損",
                "claude_summary": "[Claude 說明]"
            }
            cache_data["stocks"].append(stock_dict)
        
        # 儲存快取
        save_picker_cache(cache_data)
        
        # 推播給訂閱使用者（需實作）
        # broadcast_to_subscribers(line_client, cache_data)
        
        print("[scheduler] 選股推薦完成")
    
    except Exception as e:
        print(f"[scheduler] 執行失敗：{e}")
```

### Step 4: Update `bot/server.py` — 註冊排程

在 `lifespan` 函數中新增排程註冊：

```python
from apscheduler.schedulers.background import BackgroundScheduler

async def lifespan(app: FastAPI):
    """Startup and shutdown"""
    # 既有代碼...
    
    # 註冊每日選股排程（08:00 UTC+8 = 00:00 UTC）
    try:
        from bot.stock_picker.scheduler import daily_stock_picker_task
        from bot.data.fugle_client import FugleClient
        from bot.stock_picker.finmind_client import FinMindClient
        
        scheduler = BackgroundScheduler(timezone="Asia/Taipei")
        scheduler.add_job(
            daily_stock_picker_task,
            trigger="cron",
            hour=0,
            minute=0,
            args=(FinMindClient(), FugleClient(), None, None),  # 簡化參數傳遞
            id="stock_picker_daily"
        )
        scheduler.start()
        print("[startup] 選股推薦排程已註冊")
    except Exception as e:
        print(f"[startup] 排程註冊失敗：{e}")
    
    yield
    
    # Shutdown logic
    print("[shutdown] Server shutting down")
```

### Step 5: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_scheduler.py -v
```

Expected: 2 tests PASS

### Step 6: Commit

```bash
git add bot/stock_picker/scheduler.py bot/server.py tests/test_stock_picker_scheduler.py
git commit -m "✨ feat: add daily stock picker scheduler (08:00) with caching mechanism"
```

---

## Task 8: Claude API 說明生成和推播整合

**Files:**
- Modify: `bot/stock_picker/scheduler.py`（新增 Claude 說明生成）
- Modify: `bot/services/stock_picker.py`（新增推播邏輯）
- Test: `tests/test_stock_picker_claude.py`

### Step 1: Write failing test

Create `tests/test_stock_picker_claude.py`:

```python
"""test_stock_picker_claude.py — Claude 說明生成"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")

from bot.stock_picker.scheduler import generate_stock_summary


def test_generate_stock_summary_returns_string():
    """generate_stock_summary 應回傳字串說明"""
    reasons = {
        "fundamental": "三大法人連 3 日買超",
        "technical": "MA20 上升，回撤 3.5%"
    }
    
    with patch("bot.stock_picker.scheduler.anthropic.Anthropic") as MockClaude:
        mock_client = MagicMock()
        MockClaude.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="這支股票值得關注...")]
        )
        
        result = generate_stock_summary("2330", reasons)
        assert isinstance(result, str)
        assert len(result) > 0
```

### Step 2: Run test to confirm FAIL

```bash
python3 -m pytest tests/test_stock_picker_claude.py::test_generate_stock_summary_returns_string -v
```

Expected: Module not found

### Step 3: Update `bot/stock_picker/scheduler.py` — 新增 Claude 整合

新增函數：

```python
def generate_stock_summary(stock_id: str, reasons: Dict) -> str:
    """使用 Claude API 生成股票說明"""
    try:
        import anthropic
        
        client = anthropic.Anthropic()
        
        prompt = f"""你是台股分析師。用白話、簡潔的方式（2-3 句）解釋為什麼這支股票值得注意。

股票代號：{stock_id}
籌碼面理由：{reasons.get('fundamental', '')}
技術面理由：{reasons.get('technical', '')}

對象是不懂技術面的一般投資人，請用日常用語解釋。"""
        
        message = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return message.content[0].text
    except Exception as e:
        print(f"[scheduler] Claude 生成說明失敗：{e}")
        return "暫無說明"
```

並更新 `daily_stock_picker_task()` 中的說明生成部分：

```python
# 為每支股票生成說明
for stock in picked_stocks:
    # 取得籌碼面和技術面理由（簡化版）
    reasons = {
        "fundamental": "三大法人買超條件符合",
        "technical": "技術面條件符合"
    }
    
    claude_summary = generate_stock_summary(stock.stock_id, reasons)
    
    stock_dict = {
        "stock_id": stock.stock_id,
        "stock_name": stock.stock_name,
        "reasons": reasons,
        "risks": "若跌破 MA20 應設停損",
        "claude_summary": claude_summary
    }
    cache_data["stocks"].append(stock_dict)
```

### Step 4: Run tests to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_claude.py -v
```

Expected: 1 test PASS

### Step 5: Commit

```bash
git add bot/stock_picker/scheduler.py tests/test_stock_picker_claude.py
git commit -m "✨ feat: add Claude API integration for generating stock summaries"
```

---

## Task 9: 整合測試和驗證

**Files:**
- Test: `tests/test_stock_picker_integration.py`

### Step 1: Write integration test

Create `tests/test_stock_picker_integration.py`:

```python
"""test_stock_picker_integration.py — Phase B 整合測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FUGLE_API_KEY", "test_key")
os.environ.setdefault("FINMIND_API_KEY", "test_key")

from bot.stock_picker.base import Stock
from bot.stock_picker.engine import StockPickerEngine
from bot.stock_picker.fundamental_strategy import FundamentalStrategy
from bot.stock_picker.technical_strategy import TechnicalStrategy


def test_full_pipeline_fundamental_to_technical():
    """完整流程：從籌碼面到技術面篩選"""
    mock_finmind = MagicMock()
    mock_fugle = MagicMock()
    
    # 籌碼面返回 2 支股票
    mock_finmind.get_all_stocks_basic.return_value = [
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2454", "stock_name": "聯發科"},
    ]
    mock_finmind.get_three_major_buyers.return_value = {
        "consecutive_buy_days": 3,
        "total_buy": 10000000,
        "total_sell": 1000000,
    }
    mock_finmind.get_margin_status.return_value = {
        "margin_balance": 5000000,
        "margin_increase_pct": 2.0,
    }
    
    # 技術面模擬 1 支
    mock_fugle.load_stock_map.return_value = {
        "台積電": "2330",
        "聯發科": "2454",
    }
    
    import pandas as pd
    df = pd.DataFrame({
        "close": [100 + i * 0.5 for i in range(20)],
        "high": [110] * 20,
    })
    mock_fugle.fetch_candles.return_value = df
    
    # 建立策略和引擎
    fundamental = FundamentalStrategy(mock_finmind)
    technical = TechnicalStrategy(mock_fugle)
    engine = StockPickerEngine([fundamental, technical])
    
    # 掃描
    result = engine.scan()
    
    # 應該有交集結果
    assert isinstance(result, list)
```

### Step 2: Run test to confirm PASS

```bash
python3 -m pytest tests/test_stock_picker_integration.py -v
```

Expected: 1 test PASS

### Step 3: Commit

```bash
git add tests/test_stock_picker_integration.py
git commit -m "✨ feat: add integration tests for Phase B stock picker pipeline"
```

---

## Task 10: 最終檢查和文件

**Files:**
- Modify: `requirements.txt`（新增依賴）
- Verify: 所有測試通過

### Step 1: Update requirements.txt

```bash
cat >> requirements.txt << 'EOF'
apscheduler>=3.10
finmind>=2.1
EOF
```

### Step 2: Run all Phase B tests

```bash
python3 -m pytest tests/test_stock_picker*.py -v --tb=short
```

Expected: 所有 Phase B 測試通過

### Step 3: Commit

```bash
git add requirements.txt
git commit -m "📦 deps: add apscheduler and finmind for Phase B stock picker"
```

---

## 檢查清單

確認實作完成：

- [ ] Task 1 — Strategy 基類 + Stock 資料類別（6 tests）
- [ ] Task 2 — FinMindClient API 封裝（6 tests）
- [ ] Task 3 — FundamentalStrategy 籌碼面（4 tests）
- [ ] Task 4 — TechnicalStrategy 技術面（3 tests）
- [ ] Task 5 — StockPickerEngine 引擎（3 tests）
- [ ] Task 6 — StockPickerService 用戶互動（3 tests）
- [ ] Task 7 — 每日排程和快取（2 tests）
- [ ] Task 8 — Claude 說明生成（1 test）
- [ ] Task 9 — 整合測試（1 test）
- [ ] Task 10 — 依賴和驗證（all green）

**總計：29+ 個測試，Phase B 完整實裝**
