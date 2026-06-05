# P1 波段分析層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增每日盤前（08:30）與盤後（13:35）波段分析，用富果 REST 抓日 K，計算 20MA 與近 20 日高點回撤，透過 Discord 推播警報。

**Architecture:** 三個新檔案（`daily_data.py`, `swing_strategy.py`, `analyze.py`）完全獨立於現有即時層，共用 `notifier.py` 推播。`analyze.py` 為手動或排程入口，現有 `main.py` 完全不動。

**Tech Stack:** Python 3.10+, `fugle-marketdata` RestClient, `pandas`, `pytest`

---

## 檔案結構

```
stock_monitor/
├── config.json              ← 新增 5 個波段參數欄位
├── notifier.py              ← 不動
├── main.py                  ← 不動
├── market_data.py           ← 不動
├── strategy.py              ← 不動
│
├── daily_data.py            ← 【新增】富果 REST 抓日 K，回傳 DataFrame
├── swing_strategy.py        ← 【新增】計算 MA20/高點回撤，回傳 SwingResult
├── analyze.py               ← 【新增】入口，盤前/盤後分析，排程或手動執行
└── tests/
    ├── test_daily_data.py   ← 【新增】daily_data 單元測試（mock REST）
    ├── test_swing_strategy.py ← 【新增】swing_strategy 單元測試
    └── test_analyze.py      ← 【新增】analyze 整合測試（mock notifier）
```

---

## Task 1: 安裝 pandas 並更新 config.json

**Files:**
- Modify: `requirements.txt`
- Modify: `config.json`

- [ ] **Step 1: 安裝 pandas**

```bash
pip install pandas
```

Expected output: `Successfully installed pandas-x.x.x`

- [ ] **Step 2: 更新 requirements.txt**

將 `requirements.txt` 改為：

```
fugle-marketdata>=0.5
yfinance>=0.2
requests>=2.31
pandas>=2.0
```

- [ ] **Step 3: 新增波段參數到 config.json**

在 `config.json` 現有欄位後新增（保留所有原有欄位不動）：

```json
{
  "stock_id": "3312",
  "stock_name": "弘憶",
  "total_shares": 5000,
  "cost_price": 64.86,
  "target_stage_1": 75.0,
  "target_stage_2": 85.0,
  "stop_loss_moving": 67,
  "stop_loss_tightened": 67,
  "alert_volume_threshold": 7000,
  "large_order_lots": 50,
  "peer_stocks": { "2465": "麗臺", "3550": "聯穎" },
  "group_stocks": { "5471": "松翰" },
  "us_tickers": ["NVDA", "SMCI"],
  "us_drop_threshold_pct": 4.0,
  "peer_drop_threshold_pct": 5.0,
  "group_drop_threshold_pct": 4.0,
  "eval_interval_sec": 5,
  "swing_ma_days": 20,
  "swing_lookback_days": 20,
  "swing_pullback_warn_pct": 5.0,
  "swing_pullback_pct": 8.0,
  "swing_ma_warn_pct": 2.0
}
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt config.json
git commit -m "feat: add pandas dependency and swing analysis config params"
```

---

## Task 2: 建立 daily_data.py（富果 REST 日 K 抓取）

**Files:**
- Create: `daily_data.py`
- Create: `tests/test_daily_data.py`

- [ ] **Step 1: 建立 tests/ 目錄並寫失敗測試**

```bash
mkdir -p tests
touch tests/__init__.py
```

建立 `tests/test_daily_data.py`：

```python
"""
test_daily_data.py — daily_data 模組單元測試
使用 mock 取代真實 Fugle REST 呼叫，不需 API Key
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from daily_data import fetch_candles


def _make_mock_candles(n: int = 60) -> list[dict]:
    """產生 n 筆假日 K 資料"""
    return [
        {
            "date": f"2026-04-{i+1:02d}",
            "open": 65.0,
            "high": 66.0,
            "low": 64.0,
            "close": 65.5 + i * 0.1,
            "volume": 1000 + i * 10,
        }
        for i in range(n)
    ]


def test_fetch_candles_returns_dataframe():
    """fetch_candles 應回傳含必要欄位的 DataFrame"""
    mock_data = _make_mock_candles(60)

    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": mock_data}

        df = fetch_candles("3312", days=60)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 60


def test_fetch_candles_sorted_ascending():
    """回傳的 DataFrame 應依日期升冪排序（最舊在前）"""
    mock_data = _make_mock_candles(10)

    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": mock_data}

        df = fetch_candles("3312", days=10)

    assert df["date"].is_monotonic_increasing


def test_fetch_candles_raises_on_api_error():
    """Fugle REST 回傳空資料或例外時，應 raise RuntimeError"""
    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.side_effect = Exception("API error")

        with pytest.raises(RuntimeError, match="無法取得"):
            fetch_candles("3312", days=60)


def test_fetch_candles_raises_on_empty_data():
    """Fugle REST 回傳空列表時，應 raise RuntimeError"""
    with patch("daily_data.RestClient") as MockClient:
        instance = MockClient.return_value
        instance.stock.historical.candles.return_value = {"data": []}

        with pytest.raises(RuntimeError, match="無法取得"):
            fetch_candles("3312", days=60)
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/test_daily_data.py -v
```

Expected: `ImportError: No module named 'daily_data'`

- [ ] **Step 3: 建立 daily_data.py**

```python
"""
daily_data.py — 富果 REST 日 K 抓取模組
使用 RestClient 取得歷史收盤資料，回傳 pandas DataFrame
"""

import os
from datetime import date, timedelta

import pandas as pd
from fugle_marketdata import RestClient


def fetch_candles(symbol: str, days: int = 60) -> pd.DataFrame:
    """
    抓取指定股票最近 N 個交易日的日 K。

    Args:
        symbol: 股票代號，例如 "3312"
        days:   抓取天數（日曆天，實際交易日會少於此數）

    Returns:
        DataFrame，欄位：date, open, high, low, close, volume
        依 date 升冪排序（最舊在前）

    Raises:
        RuntimeError: API Key 未設定、或無法取得資料
    """
    api_key = os.environ.get("FUGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未設定 FUGLE_API_KEY 環境變數。請先申請富果 API 金鑰。"
        )

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()

    try:
        client = RestClient(api_key=api_key)
        resp = client.stock.historical.candles(
            symbol=symbol,
            from_=start_date,
            to=end_date,
            fields="open,high,low,close,volume",
        )
        raw = resp.get("data", [])
    except Exception as e:
        raise RuntimeError(f"無法取得 {symbol} 日 K 資料：{e}") from e

    if not raw:
        raise RuntimeError(f"無法取得 {symbol} 日 K 資料：回傳為空")

    df = pd.DataFrame(raw, columns=["date", "open", "high", "low", "close", "volume"])
    df = df.sort_values("date").reset_index(drop=True)
    return df
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/test_daily_data.py -v
```

Expected:
```
PASSED tests/test_daily_data.py::test_fetch_candles_returns_dataframe
PASSED tests/test_daily_data.py::test_fetch_candles_sorted_ascending
PASSED tests/test_daily_data.py::test_fetch_candles_raises_on_api_error
PASSED tests/test_daily_data.py::test_fetch_candles_raises_on_empty_data
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add daily_data.py tests/__init__.py tests/test_daily_data.py
git commit -m "feat: add daily_data module with Fugle REST candle fetching"
```

---

## Task 3: 建立 swing_strategy.py（波段指標計算與訊號判斷）

**Files:**
- Create: `swing_strategy.py`
- Create: `tests/test_swing_strategy.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_swing_strategy.py`：

```python
"""
test_swing_strategy.py — swing_strategy 模組單元測試
直接建構 DataFrame 測試，不需任何外部 API
"""

import pytest
import pandas as pd
from swing_strategy import SwingResult, analyze_swing
from notifier import COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_INFO


def _make_df(closes: list[float]) -> pd.DataFrame:
    """建構測試用 DataFrame，只需提供收盤價序列"""
    n = len(closes)
    return pd.DataFrame({
        "date": [f"2026-{i+1:02d}-01" for i in range(n)],
        "open":  closes,
        "high":  [c + 1 for c in closes],
        "low":   [c - 1 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_analyze_swing_returns_result():
    """analyze_swing 應回傳 SwingResult"""
    closes = [65.0] * 25
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    assert isinstance(result, SwingResult)
    assert result.close == pytest.approx(65.0)
    assert result.ma20 == pytest.approx(65.0)


def test_no_signal_when_above_ma_and_low_pullback():
    """均線上方且回撤小，應無警報（綠燈）"""
    closes = [60.0] * 19 + [65.0]  # 最新收盤高於 MA20
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    assert result.alerts == []


def test_red_alert_when_close_below_ma20():
    """收盤跌破 20MA 應觸發紅燈警報"""
    # 前 19 天收 70，最後一天跌到 60（遠低於 MA20 ≈ 69.5）
    closes = [70.0] * 19 + [60.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_RED in colors


def test_yellow_alert_when_close_near_ma20():
    """距 MA20 不足 2% 應觸發黃燈預警"""
    # MA20 ≈ 65.0，最新收盤 65.5（+0.77%，< 2% 警戒）
    closes = [65.0] * 19 + [65.5]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_YELLOW in colors


def test_red_alert_when_pullback_over_8pct():
    """從近 20 日高點回撤 ≥ 8% 應觸發紅燈"""
    # 近 20 日最高 80，最新收盤 73（回撤 8.75%）
    closes = [70.0] * 15 + [80.0] * 4 + [73.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_RED in colors


def test_yellow_alert_when_pullback_5_to_8pct():
    """從近 20 日高點回撤 5~8% 應觸發黃燈預警"""
    # 近 20 日最高 80，最新收盤 75（回撤 6.25%）
    closes = [70.0] * 15 + [80.0] * 4 + [75.0]
    result = analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                           pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
    colors = [a.color for a in result.alerts]
    assert COLOR_YELLOW in colors


def test_insufficient_data_raises():
    """資料筆數不足 ma_days 時應 raise ValueError"""
    closes = [65.0] * 10  # 只有 10 筆，ma_days=20
    with pytest.raises(ValueError, match="資料不足"):
        analyze_swing(_make_df(closes), lookback=20, ma_days=20,
                      pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/test_swing_strategy.py -v
```

Expected: `ImportError: No module named 'swing_strategy'`

- [ ] **Step 3: 建立 swing_strategy.py**

```python
"""
swing_strategy.py — 波段指標計算與訊號判斷
接收日 K DataFrame，計算 MA20 與近 20 日高點回撤，回傳 SwingResult
"""

from dataclasses import dataclass, field

import pandas as pd

from notifier import COLOR_INFO, COLOR_YELLOW, COLOR_RED
from strategy import Alert


@dataclass
class SwingResult:
    """波段分析結果"""
    close: float           # 最新收盤價
    ma20: float            # 20 日均線
    high20: float          # 近 20 日最高收盤
    pct_from_ma20: float   # 距 MA20 偏離 %（正=上方，負=下方）
    pullback_pct: float    # 從高點回撤 %
    alerts: list[Alert] = field(default_factory=list)


def analyze_swing(
    df: pd.DataFrame,
    lookback: int,
    ma_days: int,
    pullback_warn: float,
    pullback_alert: float,
    ma_warn: float,
) -> SwingResult:
    """
    計算波段技術指標並判斷訊號。

    Args:
        df:             日 K DataFrame（date, open, high, low, close, volume）
        lookback:       高點回撤的觀察天數（取近 N 日最高收盤）
        ma_days:        均線天數
        pullback_warn:  高點回撤黃燈門檻（%）
        pullback_alert: 高點回撤紅燈門檻（%）
        ma_warn:        距 MA 黃燈門檻（%），正數在均線上方才算

    Returns:
        SwingResult，alerts 為空表示無異常

    Raises:
        ValueError: 資料筆數不足 ma_days
    """
    if len(df) < ma_days:
        raise ValueError(
            f"資料不足：需要至少 {ma_days} 筆，目前只有 {len(df)} 筆"
        )

    close_latest = float(df["close"].iloc[-1])
    ma20 = float(df["close"].tail(ma_days).mean())
    high20 = float(df["close"].tail(lookback).max())

    pct_from_ma20 = round((close_latest - ma20) / ma20 * 100, 2)
    pullback_pct = round((high20 - close_latest) / high20 * 100, 2)

    alerts: list[Alert] = []

    # 跌破 20MA → 紅燈
    if close_latest < ma20:
        alerts.append(Alert(
            title="跌破 20 日均線",
            message=(
                f"收盤 {close_latest} 元，已跌破 MA20（{ma20:.2f} 元）\n"
                f"偏離幅度 {pct_from_ma20:+.2f}%，波段趨勢轉弱，請注意出場時機。"
            ),
            color=COLOR_RED,
        ))
    # 逼近 20MA（上方但不足 ma_warn%）→ 黃燈
    elif 0 <= pct_from_ma20 < ma_warn:
        alerts.append(Alert(
            title="均線支撐即將測試",
            message=(
                f"收盤 {close_latest} 元，距 MA20（{ma20:.2f} 元）僅 {pct_from_ma20:+.2f}%\n"
                f"若明日跌破 {ma20:.2f} 元，建議考慮減碼。"
            ),
            color=COLOR_YELLOW,
        ))

    # 高點回撤 ≥ pullback_alert% → 紅燈
    if pullback_pct >= pullback_alert:
        alerts.append(Alert(
            title="高點回撤警示",
            message=(
                f"收盤 {close_latest} 元，距近 {lookback} 日高點（{high20} 元）"
                f"已回撤 {pullback_pct:.2f}%\n"
                f"超過 {pullback_alert}% 警戒線，動能減弱，請評估出場。"
            ),
            color=COLOR_RED,
        ))
    # 高點回撤 pullback_warn~pullback_alert% → 黃燈
    elif pullback_warn <= pullback_pct < pullback_alert:
        alerts.append(Alert(
            title="高點回撤預警",
            message=(
                f"收盤 {close_latest} 元，距近 {lookback} 日高點（{high20} 元）"
                f"已回撤 {pullback_pct:.2f}%\n"
                f"接近 {pullback_alert}% 警戒，請留意。"
            ),
            color=COLOR_YELLOW,
        ))

    return SwingResult(
        close=close_latest,
        ma20=ma20,
        high20=high20,
        pct_from_ma20=pct_from_ma20,
        pullback_pct=pullback_pct,
        alerts=alerts,
    )
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/test_swing_strategy.py -v
```

Expected:
```
PASSED tests/test_swing_strategy.py::test_analyze_swing_returns_result
PASSED tests/test_swing_strategy.py::test_no_signal_when_above_ma_and_low_pullback
PASSED tests/test_swing_strategy.py::test_red_alert_when_close_below_ma20
PASSED tests/test_swing_strategy.py::test_yellow_alert_when_close_near_ma20
PASSED tests/test_swing_strategy.py::test_red_alert_when_pullback_over_8pct
PASSED tests/test_swing_strategy.py::test_yellow_alert_when_pullback_5_to_8pct
PASSED tests/test_swing_strategy.py::test_insufficient_data_raises
7 passed
```

- [ ] **Step 5: Commit**

```bash
git add swing_strategy.py tests/test_swing_strategy.py
git commit -m "feat: add swing_strategy module with MA20 and pullback signal detection"
```

---

## Task 4: 建立 analyze.py（盤前/盤後分析入口）

**Files:**
- Create: `analyze.py`
- Create: `tests/test_analyze.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_analyze.py`：

```python
"""
test_analyze.py — analyze 模組整合測試
mock daily_data 與 notifier，驗證輸出格式與推播邏輯
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, call
from analyze import run_analysis, Mode


def _make_df(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "date": [f"2026-{i+1:02d}-01" for i in range(n)],
        "open":  closes,
        "high":  [c + 1 for c in closes],
        "low":   [c - 1 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def _make_config() -> dict:
    return {
        "stock_id": "3312",
        "stock_name": "弘憶",
        "cost_price": 64.86,
        "swing_ma_days": 20,
        "swing_lookback_days": 20,
        "swing_pullback_warn_pct": 5.0,
        "swing_pullback_pct": 8.0,
        "swing_ma_warn_pct": 2.0,
    }


def test_run_analysis_premarket_sends_notification(capsys):
    """盤前模式：run_analysis 應呼叫 notifier.send 一次"""
    closes = [65.0] * 25
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.PREMARKET)

    mock_notifier.send.assert_called_once()
    title, message, color = mock_notifier.send.call_args[0]
    assert "盤前分析" in title


def test_run_analysis_postmarket_sends_notification(capsys):
    """盤後模式：run_analysis 應呼叫 notifier.send 一次"""
    closes = [65.0] * 25
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.POSTMARKET)

    mock_notifier.send.assert_called_once()
    title, _, _ = mock_notifier.send.call_args[0]
    assert "盤後分析" in title


def test_run_analysis_red_alert_sends_extra_notification():
    """有紅燈警報時，應額外再呼叫一次 notifier.send"""
    # 收盤跌破 MA20 → 紅燈
    closes = [70.0] * 19 + [60.0]
    config = _make_config()

    with patch("analyze.fetch_candles", return_value=_make_df(closes)):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.POSTMARKET)

    # 1 次摘要 + 至少 1 次警報
    assert mock_notifier.send.call_count >= 2


def test_run_analysis_handles_fetch_error(capsys):
    """fetch_candles 失敗時，應印錯誤訊息，不 raise"""
    config = _make_config()

    with patch("analyze.fetch_candles", side_effect=RuntimeError("API 失敗")):
        mock_notifier = MagicMock()
        run_analysis(config, mock_notifier, mode=Mode.PREMARKET)

    captured = capsys.readouterr()
    assert "失敗" in captured.out
    mock_notifier.send.assert_not_called()
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/test_analyze.py -v
```

Expected: `ImportError: No module named 'analyze'`

- [ ] **Step 3: 建立 analyze.py**

```python
"""
analyze.py — 波段分析入口
手動執行或由排程觸發，執行盤前（08:30）或盤後（13:35）分析
用法：
    python analyze.py --pre     盤前分析
    python analyze.py --post    盤後分析
    python analyze.py           依當前時間自動判斷
"""

import json
import sys
import datetime
from enum import Enum

from daily_data import fetch_candles
from notifier import DiscordNotifier, COLOR_INFO, COLOR_GREEN, COLOR_YELLOW, COLOR_RED
from swing_strategy import analyze_swing, SwingResult
from strategy import Alert


class Mode(Enum):
    PREMARKET  = "premarket"
    POSTMARKET = "postmarket"


def _detect_mode() -> Mode:
    """依當前時間自動判斷盤前或盤後"""
    now = datetime.datetime.now().time()
    cutoff = datetime.time(13, 0)
    return Mode.POSTMARKET if now >= cutoff else Mode.PREMARKET


def _format_premarket(stock_name: str, stock_id: str, result: SwingResult) -> tuple[str, str]:
    """回傳盤前分析的 (title, message)"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"📊 盤前分析｜{now_str}"

    signal_line = "✅ 無異常，可續抱"
    if any(a.color == COLOR_RED for a in result.alerts):
        signal_line = "🔴 注意：有警示訊號，請謹慎"
    elif any(a.color == COLOR_YELLOW for a in result.alerts):
        signal_line = "🟡 留意：有預警訊號"

    message = (
        f"【{stock_id} {stock_name}】\n"
        f"  昨收  {result.close} 元\n"
        f"  MA20  {result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%，"
        f"{'均線上方' if result.pct_from_ma20 >= 0 else '均線下方'}）\n"
        f"  高點  {result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
        f"  訊號  {signal_line}"
    )
    return title, message


def _format_postmarket(stock_name: str, stock_id: str, result: SwingResult, prev_close: float) -> tuple[str, str]:
    """回傳盤後分析的 (title, message)"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"📊 盤後分析｜{now_str}"

    pct_change = round((result.close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    if result.pct_from_ma20 >= 2.0:
        tomorrow = f"續抱，若跌破 {result.ma20:.2f} 考慮減碼"
    elif 0 <= result.pct_from_ma20 < 2.0:
        tomorrow = f"留意：明日若跌破 {result.ma20:.2f} 元（MA20）建議減碼"
    else:
        tomorrow = f"警示：已跌破 MA20（{result.ma20:.2f} 元），評估出場"

    message = (
        f"【{stock_id} {stock_name}】\n"
        f"  今收  {result.close} 元（{pct_change:+.2f}%）\n"
        f"  MA20  {result.ma20:.2f} 元（{result.pct_from_ma20:+.2f}%）\n"
        f"  高點  {result.high20} 元（回撤 {result.pullback_pct:.2f}%）\n"
        f"  明日  {tomorrow}"
    )
    return title, message


def run_analysis(config: dict, notifier: DiscordNotifier, mode: Mode) -> None:
    """
    執行一次波段分析並推播結果。

    Args:
        config:   config.json 載入的設定 dict
        notifier: DiscordNotifier 實例
        mode:     PREMARKET 或 POSTMARKET
    """
    stock_id   = config["stock_id"]
    stock_name = config["stock_name"]
    ma_days    = config["swing_ma_days"]
    lookback   = config["swing_lookback_days"]

    try:
        df = fetch_candles(stock_id, days=lookback + 10)
    except RuntimeError as e:
        print(f"[錯誤] 抓取 {stock_id} 日 K 失敗：{e}")
        return

    try:
        result = analyze_swing(
            df,
            lookback=lookback,
            ma_days=ma_days,
            pullback_warn=config["swing_pullback_warn_pct"],
            pullback_alert=config["swing_pullback_pct"],
            ma_warn=config["swing_ma_warn_pct"],
        )
    except ValueError as e:
        print(f"[錯誤] 分析失敗：{e}")
        return

    # 組摘要訊息並推播
    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else result.close
    if mode == Mode.PREMARKET:
        title, message = _format_premarket(stock_name, stock_id, result)
        summary_color = COLOR_INFO
    else:
        title, message = _format_postmarket(stock_name, stock_id, result, prev_close)
        summary_color = COLOR_INFO

    print(f"\n{'═'*45}")
    print(f"{title}")
    print(f"{'─'*45}")
    print(message)
    print(f"{'═'*45}\n")

    notifier.send(title, message, summary_color)

    # 額外推播各個警報訊號
    for alert in result.alerts:
        print(f"[警報] {alert.title}")
        notifier.send(alert.title, alert.message, alert.color)


def _load_config(path: str = "config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--pre" in args:
        mode = Mode.PREMARKET
    elif "--post" in args:
        mode = Mode.POSTMARKET
    else:
        mode = _detect_mode()

    config   = _load_config()
    notifier = DiscordNotifier()
    run_analysis(config, notifier, mode)
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/test_analyze.py -v
```

Expected:
```
PASSED tests/test_analyze.py::test_run_analysis_premarket_sends_notification
PASSED tests/test_analyze.py::test_run_analysis_postmarket_sends_notification
PASSED tests/test_analyze.py::test_run_analysis_red_alert_sends_extra_notification
PASSED tests/test_analyze.py::test_run_analysis_handles_fetch_error
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add analyze.py tests/test_analyze.py
git commit -m "feat: add analyze.py entry point for pre/post market swing analysis"
```

---

## Task 5: 全套測試 + 手動驗收

**Files:**
- 無新增檔案

- [ ] **Step 1: 執行全套測試**

```bash
pytest tests/ -v
```

Expected: 全部 15 個測試 PASSED，0 FAILED

- [ ] **Step 2: mock 模式手動驗收（不需 API Key）**

```bash
python analyze.py --pre
```

Expected 輸出範例：
```
═════════════════════════════════════════════
📊 盤前分析｜2026-06-05 08:30
─────────────────────────────────────────────
【3312 弘憶】
  昨收  68.50 元
  MA20  66.20 元（+3.47%，均線上方）
  高點  71.00 元（回撤 3.52%）
  訊號  ✅ 無異常，可續抱
═════════════════════════════════════════════
```

若未設定 `FUGLE_API_KEY`，預期印出：
```
[錯誤] 抓取 3312 日 K 失敗：未設定 FUGLE_API_KEY 環境變數。請先申請富果 API 金鑰。
```

這是正常行為（無 Key 就無法呼叫 REST）。

- [ ] **Step 3: 設定 macOS 排程（launchd）**

建立 `~/Library/LaunchAgents/com.smartmonitor.analyze.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.smartmonitor.analyze</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/jerry/Projects/Personal/experiments/smart-monitor/analyze.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict>
      <key>Hour</key><integer>8</integer>
      <key>Minute</key><integer>30</integer>
    </dict>
    <dict>
      <key>Hour</key><integer>13</integer>
      <key>Minute</key><integer>35</integer>
    </dict>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/jerry/Projects/Personal/experiments/smart-monitor</string>
  <key>StandardOutPath</key>
  <string>/tmp/smartmonitor-analyze.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/smartmonitor-analyze-err.log</string>
</dict>
</plist>
```

載入排程：
```bash
launchctl load ~/Library/LaunchAgents/com.smartmonitor.analyze.plist
```

確認已載入：
```bash
launchctl list | grep smartmonitor
```

Expected: 看到 `com.smartmonitor.analyze`

- [ ] **Step 4: 最終 Commit**

```bash
git add docs/superpowers/plans/2026-06-05-p1-swing-analysis.md
git commit -m "docs: add P1 swing analysis implementation plan"
```

---

## 自審檢查清單

- [x] 規格 P1 所有需求均有對應任務（daily_data, swing_strategy, analyze, 排程）
- [x] 無 TBD / TODO 佔位符
- [x] 型別一致：`SwingResult`, `analyze_swing`, `run_analysis`, `Mode` 在各任務間命名一致
- [x] 測試均有實際程式碼，不是描述性文字
- [x] 現有檔案（main.py, strategy.py, market_data.py, notifier.py）完全不動
