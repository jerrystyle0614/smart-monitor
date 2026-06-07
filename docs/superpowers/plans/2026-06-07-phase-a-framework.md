# Phase A 服務框架重寫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用純數字選單 + 問答腳本引擎取代現有 Gemini 自然語言解析流程，支援一人最多 3 支股票監控，敏感欄位 AES 加密，server 重啟後自動恢復監控狀態。

**Architecture:** 新建 `bot/router.py`（ServiceRouter）取代 `handlers.py`，`bot/services/` 目錄下各服務定義問答腳本，`bot/data/fugle_client.py` 統一 Fugle API 呼叫，`bot/crypto.py` 提供 AES-256-GCM 加解密。資料結構改為三個 JSON 檔案（profile / state / watchlist），背景監控引擎（MonitorEngine）不動。

**Tech Stack:** Python 3.9、`cryptography>=41.0`（AES-256-GCM）、Fugle REST API、LINE Messaging API

**重要：Python 3.9 限制** — 不可使用 `X | Y` 型別語法、`list[str]`、`dict[str, str]`，改用 `Optional[X]`、`List[str]`、`Dict[str, str]`（from typing import）

---

## 檔案結構總覽

### 新建
| 檔案 | 說明 |
|------|------|
| `bot/crypto.py` | AES-256-GCM 加解密 |
| `bot/data/__init__.py` | 空白 |
| `bot/data/fugle_client.py` | Fugle API 統一封裝 |
| `bot/services/__init__.py` | 空白 |
| `bot/services/base.py` | ScriptedService 問答腳本基底 |
| `bot/services/stock_monitor.py` | 股票監控服務 |
| `bot/services/pre_market.py` | 盤前分析服務 |
| `bot/services/post_market.py` | 盤後分析服務 |
| `bot/router.py` | ServiceRouter 主路由 |
| `tests/test_crypto.py` | 加密測試 |
| `tests/test_fugle_client.py` | Fugle 客戶端測試 |
| `tests/test_user_store_v2.py` | 新版 UserStore 測試 |
| `tests/test_scripted_service.py` | 問答腳本引擎測試 |
| `tests/test_router.py` | ServiceRouter 測試 |

### 修改
| 檔案 | 說明 |
|------|------|
| `bot/user_store.py` | 完整重寫，支援多股票 + 加密 + plan |
| `bot/server.py` | 更新 import，移除 handlers 依賴 |
| `bot/monitor_engine.py` | 更新 `get_all_monitoring_users` 使用新資料結構 |
| `bot/analysis_runner.py` | 更新股票設定讀取方式 |
| `start_bot.sh` | 移除 `CLEAR_ON_START=1` 預設 |
| `requirements.txt` | 加入 `cryptography>=41.0` |
| `.env` | 加入 `ENCRYPT_KEY` |

### 移除（Task 6 最後才移除）
| 檔案 | 說明 |
|------|------|
| `bot/handlers.py` | 由 router.py 取代 |
| `bot/state_machine.py` | 由 services/base.py 取代 |
| `bot/claude_parser.py` | Gemini 移除，Fugle 驗證移到 fugle_client.py |

---

## Task 1：AES 加解密模組

**Files:**
- Create: `bot/crypto.py`
- Create: `tests/test_crypto.py`

- [ ] **Step 1: 安裝 cryptography 套件**

```bash
pip3 install cryptography
```

在 `requirements.txt` 加入：
```
cryptography>=41.0
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_crypto.py`：

```python
"""test_crypto.py — AES-256-GCM 加解密測試"""
import os
import pytest

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)  # 測試用固定金鑰

from bot.crypto import encrypt, decrypt, encrypt_fields, decrypt_fields, CryptoError


def test_encrypt_decrypt_roundtrip():
    """加密後解密應還原原始值"""
    original = "64.86"
    assert decrypt(encrypt(original)) == original


def test_encrypt_produces_different_output():
    """相同輸入每次加密結果應不同（GCM 隨機 nonce）"""
    v = "900.0"
    assert encrypt(v) != encrypt(v)


def test_decrypt_invalid_raises():
    """解密無效密文應拋出 CryptoError"""
    with pytest.raises(CryptoError):
        decrypt("not-valid-ciphertext")


def test_encrypt_fields():
    """encrypt_fields 只加密指定欄位"""
    data = {"stock_id": "2330", "cost_price": "900.0", "stock_name": "台積電"}
    result = encrypt_fields(data, ["cost_price"])
    assert result["stock_id"] == "2330"
    assert result["stock_name"] == "台積電"
    assert result["cost_price"] != "900.0"
    assert decrypt(result["cost_price"]) == "900.0"


def test_decrypt_fields():
    """decrypt_fields 還原指定欄位"""
    data = {"stock_id": "2330", "cost_price": "900.0"}
    encrypted = encrypt_fields(data, ["cost_price"])
    decrypted = decrypt_fields(encrypted, ["cost_price"])
    assert decrypted["cost_price"] == "900.0"


def test_decrypt_fields_skips_none():
    """decrypt_fields 遇到 None 值應略過不處理"""
    data = {"stop_loss": None, "cost_price": "900.0"}
    encrypted = encrypt_fields(data, ["cost_price"])
    result = decrypt_fields(encrypted, ["cost_price", "stop_loss"])
    assert result["stop_loss"] is None
    assert result["cost_price"] == "900.0"
```

- [ ] **Step 3: 執行確認失敗**

```bash
cd /Users/jerry/Projects/Personal/experiments/smart-monitor
python3 -m pytest tests/test_crypto.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.crypto'`

- [ ] **Step 4: 實作 `bot/crypto.py`**

```python
"""
crypto.py — AES-256-GCM 加解密模組
敏感欄位（持股成本、張數、停損、目標）加密儲存
"""

import os
import base64
from typing import Optional, List, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(Exception):
    """加解密失敗"""


def _get_key() -> bytes:
    """從環境變數讀取 32 bytes AES 金鑰（64 hex 字元）"""
    key_hex = os.environ.get("ENCRYPT_KEY", "")
    if len(key_hex) != 64:
        raise CryptoError("ENCRYPT_KEY 必須是 64 字元 hex 字串（32 bytes）")
    return bytes.fromhex(key_hex)


def encrypt(value: str) -> str:
    """
    加密字串，回傳 base64 編碼的 nonce+密文。
    每次加密產生不同的隨機 nonce，確保相同輸入輸出不同。
    """
    try:
        key = _get_key()
        nonce = os.urandom(12)  # GCM 標準 nonce 長度
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("utf-8")
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(f"加密失敗：{e}") from e


def decrypt(value: str) -> str:
    """解密 base64 編碼的 nonce+密文，回傳原始字串"""
    try:
        key = _get_key()
        raw = base64.b64decode(value.encode("utf-8"))
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(f"解密失敗：{e}") from e


def encrypt_fields(data: Dict, fields: List[str]) -> Dict:
    """批次加密 dict 中指定欄位（None 值略過），回傳新 dict"""
    result = dict(data)
    for field in fields:
        val = result.get(field)
        if val is not None:
            result[field] = encrypt(str(val))
    return result


def decrypt_fields(data: Dict, fields: List[str]) -> Dict:
    """批次解密 dict 中指定欄位（None 值略過），回傳新 dict"""
    result = dict(data)
    for field in fields:
        val = result.get(field)
        if val is not None:
            result[field] = decrypt(str(val))
    return result
```

- [ ] **Step 5: 在 `.env` 加入 ENCRYPT_KEY**

```bash
python3 -c "import secrets; print('ENCRYPT_KEY=' + secrets.token_hex(32))"
```

把輸出的一行加到 `.env` 檔案。

- [ ] **Step 6: 執行確認通過**

```bash
python3 -m pytest tests/test_crypto.py -v
```

Expected: 6 個測試全部 PASS

- [ ] **Step 7: Commit**

```bash
git add bot/crypto.py tests/test_crypto.py requirements.txt
git commit -m "✨ feat: add AES-256-GCM encryption module"
```

---

## Task 2：FugleClient 統一封裝

**Files:**
- Create: `bot/data/__init__.py`
- Create: `bot/data/fugle_client.py`
- Create: `tests/test_fugle_client.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_fugle_client.py`：

```python
"""test_fugle_client.py — FugleClient 單元測試（mock HTTP）"""
import pytest
from unittest.mock import patch, MagicMock
from bot.data.fugle_client import FugleClient


@pytest.fixture
def client():
    return FugleClient(api_key="test-key")


def _mock_quote(name="台積電", close=920.0, pct=-0.84):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "symbol": "2330", "name": name,
        "closePrice": close, "changePercent": pct,
        "lastPrice": close,
    }
    return m


def test_get_quote_success(client):
    """get_quote 成功時回傳 dict 含 name、close_price、change_pct"""
    with patch("requests.get", return_value=_mock_quote()):
        result = client.get_quote("2330")
    assert result["name"] == "台積電"
    assert result["close_price"] == 920.0
    assert result["change_pct"] == -0.84


def test_get_quote_not_found(client):
    """股票代號不存在時回傳 None"""
    m = MagicMock()
    m.status_code = 404
    with patch("requests.get", return_value=m):
        result = client.get_quote("9999")
    assert result is None


def test_get_quote_network_error(client):
    """網路錯誤時回傳 None，不崩潰"""
    with patch("requests.get", side_effect=Exception("timeout")):
        result = client.get_quote("2330")
    assert result is None


def test_verify_stock_by_id(client):
    """用代號驗證股票，回傳 stock_id 和 stock_name"""
    with patch("requests.get", return_value=_mock_quote()):
        result = client.verify_stock("2330")
    assert result == {"stock_id": "2330", "stock_name": "台積電"}


def test_verify_stock_not_found(client):
    """代號和名稱都找不到時回傳 None"""
    m = MagicMock()
    m.status_code = 404
    with patch("requests.get", return_value=m):
        result = client.verify_stock("9999")
    assert result is None


def test_verify_stock_by_name(client):
    """用名稱驗證股票，從 stock_map 查代號"""
    client._stock_map = {"台積電": "2330"}
    with patch.object(client, "get_quote", return_value={"name": "台積電", "close_price": 920.0, "change_pct": -0.84}):
        result = client.verify_stock("台積電")
    assert result == {"stock_id": "2330", "stock_name": "台積電"}
```

- [ ] **Step 2: 執行確認失敗**

```bash
python3 -m pytest tests/test_fugle_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.data'`

- [ ] **Step 3: 建立 `bot/data/__init__.py`**

```bash
mkdir -p bot/data && touch bot/data/__init__.py
```

- [ ] **Step 4: 實作 `bot/data/fugle_client.py`**

```python
"""
fugle_client.py — Fugle REST API 統一封裝
整合 quote、日K、股票驗證等呼叫
"""

import os
import requests
from typing import Optional, Dict
import pandas as pd
from datetime import date, timedelta


class FugleClient:
    BASE = "https://api.fugle.tw/marketdata/v1.0/stock"

    def __init__(self, api_key: Optional[str] = None):
        self._key = api_key or os.environ.get("FUGLE_API_KEY", "")
        self._stock_map: Dict[str, str] = {}  # {名稱: 代號}

    def _headers(self) -> dict:
        return {"X-API-KEY": self._key}

    def get_quote(self, stock_id: str) -> Optional[dict]:
        """
        取得即時報價。
        回傳 {"name", "close_price", "change_pct"} 或 None
        """
        try:
            r = requests.get(
                f"{self.BASE}/intraday/quote/{stock_id}",
                headers=self._headers(),
                timeout=8,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            return {
                "stock_id": stock_id,
                "name": data.get("name", ""),
                "close_price": data.get("closePrice") or data.get("lastPrice"),
                "change_pct": data.get("changePercent"),
            }
        except Exception as e:
            print(f"[FugleClient] get_quote {stock_id} 失敗：{e}")
            return None

    def verify_stock(self, stock_id_or_name: str) -> Optional[dict]:
        """
        驗證股票是否存在。
        1. 先當成代號查 quote API
        2. 查不到再從 stock_map 用名稱找代號
        回傳 {"stock_id": "2330", "stock_name": "台積電"} 或 None
        """
        # 先嘗試當代號
        quote = self.get_quote(stock_id_or_name)
        if quote and quote.get("name"):
            return {"stock_id": stock_id_or_name, "stock_name": quote["name"]}

        # 再嘗試當名稱
        if stock_id_or_name in self._stock_map:
            sid = self._stock_map[stock_id_or_name]
            quote2 = self.get_quote(sid)
            if quote2:
                return {"stock_id": sid, "stock_name": quote2["name"]}

        return None

    def fetch_candles(self, stock_id: str, days: int = 60) -> pd.DataFrame:
        """取得日K資料，回傳 DataFrame（date, open, high, low, close, volume）"""
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=days)).isoformat()
        try:
            from fugle_marketdata import RestClient
            client = RestClient(api_key=self._key)
            resp = client.stock.historical.candles(
                symbol=stock_id, from_=start, to=end,
                fields="open,high,low,close,volume",
            )
            raw = resp.get("data", [])
            if not raw:
                raise RuntimeError(f"無法取得 {stock_id} 日K：回傳為空")
            df = pd.DataFrame(raw, columns=["date", "open", "high", "low", "close", "volume"])
            return df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            raise RuntimeError(f"fetch_candles {stock_id} 失敗：{e}") from e

    def load_stock_map(self) -> Dict[str, str]:
        """載入全市場股票清單（名稱→代號），快取到 self._stock_map"""
        combined: Dict[str, str] = {}
        for exchange in ("TWSE", "TPEx"):
            try:
                r = requests.get(
                    f"{self.BASE}/intraday/tickers",
                    headers=self._headers(),
                    params={"type": "EQUITY", "exchange": exchange},
                    timeout=15,
                )
                if r.status_code == 200:
                    for item in r.json().get("data", []):
                        name = item.get("name", "").strip()
                        symbol = item.get("symbol", "").strip()
                        if name and symbol:
                            combined[name] = symbol
            except Exception as e:
                print(f"[FugleClient] load_stock_map {exchange} 失敗：{e}")
        self._stock_map = combined
        print(f"[FugleClient] 已載入 {len(self._stock_map)} 筆股票資料")
        return combined
```

- [ ] **Step 5: 執行確認通過**

```bash
python3 -m pytest tests/test_fugle_client.py -v
```

Expected: 6 個測試全部 PASS

- [ ] **Step 6: Commit**

```bash
git add bot/data/ tests/test_fugle_client.py
git commit -m "✨ feat: add FugleClient unified API wrapper"
```

---

## Task 3：UserStore 完整重寫

**Files:**
- Modify: `bot/user_store.py` (完整重寫)
- Create: `tests/test_user_store_v2.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_user_store_v2.py`：

```python
"""test_user_store_v2.py — 新版 UserStore 測試"""
import os
import pytest

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.user_store import UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(str(tmp_path))


# --- profile ---

def test_get_plan_default(store):
    assert store.get_plan("u1") == "free"


def test_set_get_plan(store):
    store.set_plan("u1", "basic")
    assert store.get_plan("u1") == "basic"


# --- state ---

def test_get_service_default(store):
    assert store.get_current_service("u1") is None


def test_set_get_service(store):
    store.set_service_state("u1", "stock_monitor", step=0, draft={})
    assert store.get_current_service("u1") == "stock_monitor"
    assert store.get_current_step("u1") == 0


def test_clear_service_state(store):
    store.set_service_state("u1", "stock_monitor", step=1, draft={"stock_id": "2330"})
    store.clear_service_state("u1")
    assert store.get_current_service("u1") is None
    assert store.get_draft("u1") == {}


def test_update_draft(store):
    store.set_service_state("u1", "stock_monitor", step=0, draft={})
    store.update_draft("u1", "stock_id", "2330")
    assert store.get_draft("u1")["stock_id"] == "2330"


# --- watchlist ---

def test_watchlist_empty(store):
    assert store.get_watchlist("u1") == []


def test_add_stock_encrypts_sensitive(store):
    stock = {
        "stock_id": "2330", "stock_name": "台積電",
        "total_shares": 5000, "cost_price": 900.0,
        "stop_loss_moving": 850.0, "target_stage_1": None,
    }
    store.add_stock("u1", stock)
    wl = store.get_watchlist("u1")
    assert len(wl) == 1
    assert wl[0]["stock_id"] == "2330"
    assert wl[0]["cost_price"] == 900.0  # 解密後應是原值


def test_add_stock_limit(store):
    for i in range(3):
        store.add_stock("u1", {
            "stock_id": str(1000 + i), "stock_name": f"股票{i}",
            "total_shares": 1000, "cost_price": 100.0,
            "stop_loss_moving": None, "target_stage_1": None,
        })
    with pytest.raises(ValueError, match="已達監控上限"):
        store.add_stock("u1", {
            "stock_id": "9999", "stock_name": "超出",
            "total_shares": 1000, "cost_price": 100.0,
            "stop_loss_moving": None, "target_stage_1": None,
        })


def test_remove_stock(store):
    store.add_stock("u1", {
        "stock_id": "2330", "stock_name": "台積電",
        "total_shares": 1000, "cost_price": 900.0,
        "stop_loss_moving": None, "target_stage_1": None,
    })
    store.remove_stock("u1", 0)
    assert store.get_watchlist("u1") == []


def test_get_all_monitoring_users(store):
    store.add_stock("u1", {
        "stock_id": "2330", "stock_name": "台積電",
        "total_shares": 1000, "cost_price": 900.0,
        "stop_loss_moving": None, "target_stage_1": None,
    })
    store.add_stock("u2", {
        "stock_id": "2454", "stock_name": "聯發科",
        "total_shares": 1000, "cost_price": 1200.0,
        "stop_loss_moving": None, "target_stage_1": None,
    })
    users = store.get_all_monitoring_users()
    assert set(users) == {"u1", "u2"}


def test_get_alert_fired(store):
    store.add_stock("u1", {
        "stock_id": "2330", "stock_name": "台積電",
        "total_shares": 1000, "cost_price": 900.0,
        "stop_loss_moving": None, "target_stage_1": None,
    })
    assert store.get_alert_fired("u1", 0, "stop") is False
    store.set_alert_fired("u1", 0, "stop", True)
    assert store.get_alert_fired("u1", 0, "stop") is True
```

- [ ] **Step 2: 執行確認失敗**

```bash
python3 -m pytest tests/test_user_store_v2.py -v 2>&1 | head -20
```

Expected: 多個 AttributeError（新方法不存在）

- [ ] **Step 3: 完整重寫 `bot/user_store.py`**

```python
"""
user_store.py — 使用者資料讀寫模組（v2）
三個 JSON 檔案：profile.json / state.json / watchlist.json
敏感欄位使用 AES-256-GCM 加密
"""

import json
import time
from pathlib import Path
from typing import Optional, List, Dict

from bot.crypto import encrypt_fields, decrypt_fields, CryptoError

MAX_STOCKS = 3
SENSITIVE_FIELDS = ["total_shares", "cost_price", "stop_loss_moving", "target_stage_1"]

COOLDOWN_WINDOW_SEC = 30
COOLDOWN_MSG_LIMIT = 5
COOLDOWN_BLOCK_SEC = 60


class UserStore:
    def __init__(self, base_dir: str = "users"):
        self._base = Path(base_dir)

    # ── 目錄與路徑 ────────────────────────────────────────────

    def _dir(self, uid: str) -> Path:
        d = self._base / uid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _read(self, uid: str, filename: str) -> dict:
        path = self._dir(uid) / filename
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, uid: str, filename: str, data: dict) -> None:
        path = self._dir(uid) / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── profile.json（使用者身份與權限）────────────────────────

    def get_plan(self, uid: str) -> str:
        return self._read(uid, "profile.json").get("plan", "free")

    def set_plan(self, uid: str, plan: str) -> None:
        data = self._read(uid, "profile.json")
        data["plan"] = plan
        self._write(uid, "profile.json", data)

    # ── state.json（對話狀態）──────────────────────────────────

    def get_current_service(self, uid: str) -> Optional[str]:
        return self._read(uid, "state.json").get("service")

    def get_current_step(self, uid: str) -> int:
        return self._read(uid, "state.json").get("step", 0)

    def get_draft(self, uid: str) -> dict:
        return self._read(uid, "state.json").get("draft", {})

    def get_edit_index(self, uid: str) -> Optional[int]:
        return self._read(uid, "state.json").get("edit_index")

    def set_service_state(self, uid: str, service: str, step: int, draft: dict,
                          edit_index: Optional[int] = None) -> None:
        data = self._read(uid, "state.json")
        data["service"] = service
        data["step"] = step
        data["draft"] = draft
        data["edit_index"] = edit_index
        self._write(uid, "state.json", data)

    def advance_step(self, uid: str) -> None:
        data = self._read(uid, "state.json")
        data["step"] = data.get("step", 0) + 1
        self._write(uid, "state.json", data)

    def update_draft(self, uid: str, field: str, value) -> None:
        data = self._read(uid, "state.json")
        draft = data.get("draft", {})
        draft[field] = value
        data["draft"] = draft
        self._write(uid, "state.json", data)

    def clear_service_state(self, uid: str) -> None:
        data = self._read(uid, "state.json")
        data["service"] = None
        data["step"] = 0
        data["draft"] = {}
        data["edit_index"] = None
        self._write(uid, "state.json", data)

    # ── watchlist.json（監控清單）──────────────────────────────

    def _read_watchlist_raw(self, uid: str) -> List[dict]:
        """讀取加密的原始 watchlist"""
        return self._read(uid, "watchlist.json").get("stocks", [])

    def get_watchlist(self, uid: str) -> List[dict]:
        """讀取並解密 watchlist，回傳明文資料"""
        stocks = []
        for item in self._read_watchlist_raw(uid):
            try:
                decrypted = decrypt_fields(item, SENSITIVE_FIELDS)
                # 將字串還原為數值
                for field in ["total_shares", "cost_price", "stop_loss_moving", "target_stage_1"]:
                    val = decrypted.get(field)
                    if val is not None:
                        try:
                            decrypted[field] = float(val) if "." in str(val) else int(val)
                        except (ValueError, TypeError):
                            pass
                stocks.append(decrypted)
            except CryptoError as e:
                print(f"[UserStore] 解密失敗 uid={uid}：{e}")
        return stocks

    def add_stock(self, uid: str, stock: dict) -> None:
        """新增一支股票到 watchlist，超過上限時 raise ValueError"""
        raw = self._read_watchlist_raw(uid)
        if len(raw) >= MAX_STOCKS:
            raise ValueError(f"已達監控上限（{MAX_STOCKS} 支）")
        stock_with_alerts = dict(stock)
        stock_with_alerts["alerts_fired"] = {"stop": False, "target1": False}
        encrypted = encrypt_fields(stock_with_alerts, SENSITIVE_FIELDS)
        raw.append(encrypted)
        self._write(uid, "watchlist.json", {"stocks": raw})

    def update_stock(self, uid: str, index: int, stock: dict) -> None:
        """更新指定索引的股票設定"""
        raw = self._read_watchlist_raw(uid)
        if index < 0 or index >= len(raw):
            raise IndexError(f"索引 {index} 超出範圍")
        alerts = raw[index].get("alerts_fired", {"stop": False, "target1": False})
        stock_with_alerts = dict(stock)
        stock_with_alerts["alerts_fired"] = {"stop": False, "target1": False}  # 修改後重置
        raw[index] = encrypt_fields(stock_with_alerts, SENSITIVE_FIELDS)
        self._write(uid, "watchlist.json", {"stocks": raw})

    def remove_stock(self, uid: str, index: int) -> None:
        """刪除指定索引的股票"""
        raw = self._read_watchlist_raw(uid)
        if index < 0 or index >= len(raw):
            raise IndexError(f"索引 {index} 超出範圍")
        raw.pop(index)
        self._write(uid, "watchlist.json", {"stocks": raw})

    def get_all_monitoring_users(self) -> List[str]:
        """回傳所有有監控股票的使用者 ID 列表"""
        result = []
        if not self._base.exists():
            return result
        for user_dir in self._base.iterdir():
            if user_dir.is_dir():
                wl_path = user_dir / "watchlist.json"
                if wl_path.exists():
                    try:
                        with open(wl_path, encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("stocks"):
                            result.append(user_dir.name)
                    except Exception:
                        pass
        return result

    def get_alert_fired(self, uid: str, stock_index: int, alert_key: str) -> bool:
        """取得指定股票的警報旗標"""
        raw = self._read_watchlist_raw(uid)
        if stock_index >= len(raw):
            return False
        return raw[stock_index].get("alerts_fired", {}).get(alert_key, False)

    def set_alert_fired(self, uid: str, stock_index: int, alert_key: str, value: bool) -> None:
        """設定指定股票的警報旗標"""
        raw = self._read_watchlist_raw(uid)
        if stock_index >= len(raw):
            return
        if "alerts_fired" not in raw[stock_index]:
            raw[stock_index]["alerts_fired"] = {}
        raw[stock_index]["alerts_fired"][alert_key] = value
        self._write(uid, "watchlist.json", {"stocks": raw})

    def reset_alerts(self, uid: str, stock_index: int) -> None:
        """重置指定股票的所有警報旗標"""
        raw = self._read_watchlist_raw(uid)
        if stock_index < len(raw):
            raw[stock_index]["alerts_fired"] = {"stop": False, "target1": False}
            self._write(uid, "watchlist.json", {"stocks": raw})

    # ── 冷卻機制 ───────────────────────────────────────────────

    def check_cooldown(self, uid: str) -> bool:
        """冷卻機制：30 秒內超過 5 則訊息則封鎖 60 秒"""
        now = time.time()
        data = self._read(uid, "state.json")
        blocked_until = data.get("cooldown_blocked_until", 0)
        if now < blocked_until:
            return True
        timestamps = data.get("msg_timestamps", [])
        timestamps.append(now)
        timestamps = [t for t in timestamps if now - t <= COOLDOWN_WINDOW_SEC]
        data["msg_timestamps"] = timestamps
        if len(timestamps) > COOLDOWN_MSG_LIMIT:
            data["cooldown_blocked_until"] = now + COOLDOWN_BLOCK_SEC
            self._write(uid, "state.json", data)
            return True
        self._write(uid, "state.json", data)
        return False
```

- [ ] **Step 4: 執行確認通過**

```bash
python3 -m pytest tests/test_user_store_v2.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add bot/user_store.py tests/test_user_store_v2.py
git commit -m "✨ feat: rewrite UserStore with multi-stock watchlist and AES encryption"
```

---

## Task 4：問答腳本引擎基底

**Files:**
- Create: `bot/services/__init__.py`
- Create: `bot/services/base.py`
- Create: `tests/test_scripted_service.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_scripted_service.py`：

```python
"""test_scripted_service.py — 問答腳本引擎測試"""
import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.services.base import ScriptedService, Step


def _make_number_service():
    """建立一個簡單的兩步驟測試服務"""
    def validate_positive(text):
        try:
            v = float(text)
            if v <= 0:
                return False, None, "請輸入正數"
            return True, v, ""
        except ValueError:
            return False, None, "請輸入數字"

    class TestService(ScriptedService):
        name = "test"
        steps = [
            Step("field_a", "請輸入 A：", validate_positive),
            Step("field_b", "請輸入 B（可跳過）：", validate_positive, optional=True),
        ]

        def on_complete(self, uid, draft, store, line):
            line.reply("完成！")

    return TestService()


def test_start_asks_first_question():
    """start() 應發送第一個問題"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_draft.return_value = {}
    line = MagicMock()
    svc.start("u1", store, line, reply_token="tok")
    line.reply.assert_called_once()
    assert "請輸入 A" in line.reply.call_args[0][1]


def test_valid_input_advances_step():
    """合法輸入應前進到下一題"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_current_step.return_value = 0
    store.get_draft.return_value = {}
    line = MagicMock()
    result = svc.handle_input("u1", "100", store, line, reply_token="tok")
    assert result == "CONTINUE"
    store.update_draft.assert_called_once_with("u1", "field_a", 100.0)
    store.advance_step.assert_called_once()


def test_invalid_input_repeats_question():
    """非法輸入應重問同一題"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_current_step.return_value = 0
    store.get_draft.return_value = {}
    line = MagicMock()
    result = svc.handle_input("u1", "abc", store, line, reply_token="tok")
    assert result == "CONTINUE"
    store.advance_step.assert_not_called()
    line.reply.assert_called_once()
    assert "請輸入數字" in line.reply.call_args[0][1]


def test_cancel_returns_cancel():
    """輸入「取消」應回傳 CANCEL"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_current_step.return_value = 0
    line = MagicMock()
    result = svc.handle_input("u1", "取消", store, line, reply_token="tok")
    assert result == "CANCEL"


def test_skip_optional_step():
    """選填步驟輸入「跳過」應儲存 None 並前進"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_current_step.return_value = 1
    store.get_draft.return_value = {"field_a": 100.0}
    line = MagicMock()
    result = svc.handle_input("u1", "跳過", store, line, reply_token="tok")
    assert result == "DONE"
    store.update_draft.assert_called_once_with("u1", "field_b", None)


def test_last_step_returns_done():
    """最後一步完成應回傳 DONE 並呼叫 on_complete"""
    svc = _make_number_service()
    store = MagicMock()
    store.get_current_step.return_value = 1
    store.get_draft.return_value = {"field_a": 100.0}
    line = MagicMock()
    result = svc.handle_input("u1", "200", store, line, reply_token="tok")
    assert result == "DONE"
    line.reply.assert_called_with("tok", "完成！")
```

- [ ] **Step 2: 執行確認失敗**

```bash
python3 -m pytest tests/test_scripted_service.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'bot.services'`

- [ ] **Step 3: 建立 `bot/services/__init__.py`**

```bash
mkdir -p bot/services && touch bot/services/__init__.py
```

- [ ] **Step 4: 實作 `bot/services/base.py`**

```python
"""
base.py — 問答腳本引擎基底類別
定義 Step 和 ScriptedService，各服務繼承後只需定義 steps 和 on_complete
"""

from typing import List, Callable, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Step:
    """問答腳本的單一步驟"""
    field: str                    # 儲存到 draft 的欄位名
    question: str                 # 問題文字
    validate: Callable            # fn(text) -> (ok: bool, value: Any, error_msg: str)
    optional: bool = False        # 是否可輸入「跳過」略過


class ScriptedService:
    """
    問答腳本基底類別。
    子類別定義 name、steps、on_complete 即可。
    """
    name: str = ""
    steps: List[Step] = field(default_factory=list)

    def start(self, uid: str, store, line, reply_token: str) -> None:
        """進入服務，初始化狀態並發送第一個問題"""
        store.set_service_state(uid, self.name, step=0, draft={})
        line.reply(reply_token, self._question_text(0))

    def handle_input(self, uid: str, text: str, store, line,
                     reply_token: str) -> str:
        """
        處理使用者輸入。
        回傳：
          "CANCEL"   — 使用者取消，呼叫者應清除狀態並顯示主選單
          "CONTINUE" — 繼續問答（合法或非法輸入均回傳此值）
          "DONE"     — 問答完成
        """
        text = text.strip()

        # 取消指令
        if text in ("取消", "cancel", "Cancel"):
            return "CANCEL"

        step_idx = store.get_current_step(uid)
        if step_idx >= len(self.steps):
            return "DONE"

        step = self.steps[step_idx]

        # 選填步驟可以跳過
        if step.optional and text in ("跳過", "skip"):
            store.update_draft(uid, step.field, None)
            store.advance_step(uid)
            return self._finish_or_next(uid, step_idx, store, line, reply_token)

        # 驗證輸入
        ok, value, error_msg = step.validate(text)
        if not ok:
            line.reply(reply_token, f"❌ {error_msg}\n\n{self._question_text(step_idx)}")
            return "CONTINUE"

        # 儲存並前進
        store.update_draft(uid, step.field, value)
        store.advance_step(uid)
        return self._finish_or_next(uid, step_idx, store, line, reply_token)

    def _finish_or_next(self, uid: str, completed_step_idx: int,
                        store, line, reply_token: str) -> str:
        """判斷是否還有下一題，或呼叫 on_complete"""
        next_idx = completed_step_idx + 1
        if next_idx >= len(self.steps):
            draft = store.get_draft(uid)
            self.on_complete(uid, draft, store, line, reply_token)
            return "DONE"
        line.reply(reply_token, self._question_text(next_idx))
        return "CONTINUE"

    def _question_text(self, step_idx: int) -> str:
        """取得指定步驟的問題文字"""
        step = self.steps[step_idx]
        suffix = "（輸入『跳過』略過）" if step.optional else ""
        return f"{step.question}{suffix}"

    def on_complete(self, uid: str, draft: dict, store, line, reply_token: str) -> None:
        """問答完成後執行，子類別覆寫此方法"""
        raise NotImplementedError
```

- [ ] **Step 5: 執行確認通過**

```bash
python3 -m pytest tests/test_scripted_service.py -v
```

Expected: 7 個測試全部 PASS

- [ ] **Step 6: Commit**

```bash
git add bot/services/ tests/test_scripted_service.py
git commit -m "✨ feat: add ScriptedService question-answer engine base class"
```

---

## Task 5：三個服務腳本

**Files:**
- Create: `bot/services/stock_monitor.py`
- Create: `bot/services/pre_market.py`
- Create: `bot/services/post_market.py`

- [ ] **Step 1: 實作 `bot/services/stock_monitor.py`**

```python
"""
stock_monitor.py — 股票監控服務
問答腳本：股票 → 張數 → 均價 → 停損（選填）→ 確認
"""

from typing import Tuple, Any, Optional
from bot.services.base import ScriptedService, Step
from bot.data.fugle_client import FugleClient

MAX_STOCKS = 3

_fugle = FugleClient()


def _validate_stock(text: str) -> Tuple[bool, Any, str]:
    """驗證股票名稱或代號，成功回傳 {"stock_id", "stock_name"}"""
    result = _fugle.verify_stock(text.strip())
    if result:
        return True, result, ""
    return False, None, f"找不到「{text}」，請重新輸入股票名稱或代號"


def _validate_shares(text: str) -> Tuple[bool, Any, str]:
    try:
        v = int(float(text.replace("張", "").strip()))
        if v <= 0:
            return False, None, "請輸入正整數，例如：5"
        return True, v * 1000, ""  # 張 → 股
    except ValueError:
        return False, None, "請輸入正整數，例如：5"


def _validate_price(text: str) -> Tuple[bool, Any, str]:
    try:
        v = float(text.replace("元", "").strip())
        if v <= 0:
            return False, None, "請輸入正數，例如：900"
        return True, v, ""
    except ValueError:
        return False, None, "請輸入數字，例如：900"


class AddStockService(ScriptedService):
    """新增股票監控的問答腳本"""
    name = "stock_monitor_add"
    steps = [
        Step("stock_info",      "請問要監控哪支股票？（輸入名稱或代號）", _validate_stock),
        Step("total_shares",    "持有幾張？", _validate_shares),
        Step("cost_price",      "買入均價是多少元？", _validate_price),
        Step("stop_loss_moving","停損價是多少元？", _validate_price, optional=True),
    ]

    def on_complete(self, uid: str, draft: dict, store, line, reply_token: str) -> None:
        stock_info = draft.get("stock_info", {})
        stock_id = stock_info.get("stock_id", "")
        stock_name = stock_info.get("stock_name", "")
        total_shares = draft.get("total_shares", 0)
        cost_price = draft.get("cost_price", 0.0)
        stop_loss = draft.get("stop_loss_moving")

        # 顯示確認卡片，等待使用者確認
        quote = _fugle.get_quote(stock_id)
        close = quote["close_price"] if quote else None
        pct = quote["change_pct"] if quote else None

        close_line = f"收盤：{close} 元（{pct:+.2f}%）" if close else "收盤：查詢中"
        stop_line = f"停損：{stop_loss} 元" if stop_loss else "停損：未設定"
        lots = total_shares // 1000

        card = (
            f"📋 確認監控條件\n\n"
            f"股票：{stock_name}（{stock_id}）\n"
            f"{close_line}\n"
            f"持股：{lots} 張\n"
            f"均價：{cost_price} 元\n"
            f"{stop_line}\n\n"
            f"輸入「確認」開始監控\n"
            f"輸入「取消」重新設定"
        )

        # 切換到等待確認狀態
        store.set_service_state(uid, "stock_monitor_confirm", step=0, draft=draft)
        line.reply(reply_token, card)


def _show_watchlist(uid: str, store, line, push: bool = False) -> str:
    """顯示目前監控清單，回傳訊息文字"""
    stocks = store.get_watchlist(uid)
    count = len(stocks)

    if count == 0:
        msg = (
            "📈 股票監控\n\n"
            "目前沒有監控中的股票。\n\n"
            "輸入「新增」開始設定\n"
            "輸入「取消」回到主選單"
        )
    else:
        lines = [f"📈 股票監控（{count}/{MAX_STOCKS}）\n"]
        for i, s in enumerate(stocks):
            quote = _fugle.get_quote(s["stock_id"])
            price_line = ""
            if quote and quote.get("close_price"):
                price_line = f"現價 {quote['close_price']} 元（{quote['change_pct']:+.2f}%）"
            cost = s.get("cost_price", 0)
            stop = s.get("stop_loss_moving")
            stop_str = f"停損 {stop} 元" if stop else "停損未設"
            lines.append(
                f"{i+1}️⃣ {s['stock_name']}（{s['stock_id']}）\n"
                f"   均價 {cost} 元｜{stop_str}\n"
                f"   {price_line}"
            )
        lines.append(
            "\n可用指令：\n"
            "➕ 新增\n"
            "✏️ 修改 [數字]\n"
            "🗑 刪除 [數字]\n"
            "輸入「取消」回到主選單"
        )
        msg = "\n".join(lines)
    return msg
```

- [ ] **Step 2: 實作 `bot/services/pre_market.py`**

```python
"""
pre_market.py — 盤前分析服務
問答腳本：股票 → 立即執行分析推播
"""

from typing import Tuple, Any
from bot.services.base import ScriptedService, Step
from bot.data.fugle_client import FugleClient
from bot.analysis_runner import run_analysis_for_user, AnalysisMode
from notifier import DiscordNotifier
import json

_fugle = FugleClient()


def _validate_stock(text: str) -> Tuple[bool, Any, str]:
    result = _fugle.verify_stock(text.strip())
    if result:
        return True, result, ""
    return False, None, f"找不到「{text}」，請重新輸入股票名稱或代號"


class PreMarketService(ScriptedService):
    name = "pre_market"
    steps = [
        Step("stock_info", "請問要分析哪支股票？（輸入名稱或代號）", _validate_stock),
    ]

    def on_complete(self, uid: str, draft: dict, store, line, reply_token: str) -> None:
        stock_info = draft.get("stock_info", {})
        cfg = {
            "stock_id": stock_info.get("stock_id"),
            "stock_name": stock_info.get("stock_name"),
            "cost_price": None,
        }
        swing_cfg = {}
        try:
            with open("config.json", encoding="utf-8") as f:
                swing_cfg = json.load(f)
        except Exception:
            pass

        line.reply(reply_token, "⏳ 分析中，請稍候...")
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
        if result:
            line.push(uid, f"{result['title']}\n\n{result['message']}")
            DiscordNotifier().send(result["title"], result["message"], result["color"])
            for alert in result["alerts"]:
                line.push(uid, f"{alert.title}\n\n{alert.message}")
                DiscordNotifier().send(alert.title, alert.message, alert.color)
        else:
            line.push(uid, "⚠️ 分析失敗，請確認股票代號是否正確。")
        store.clear_service_state(uid)
```

- [ ] **Step 3: 實作 `bot/services/post_market.py`**

```python
"""
post_market.py — 盤後分析服務
問答腳本：股票 → 立即執行分析推播
"""

from typing import Tuple, Any
from bot.services.base import ScriptedService, Step
from bot.data.fugle_client import FugleClient
from bot.analysis_runner import run_analysis_for_user, AnalysisMode
from notifier import DiscordNotifier
import json

_fugle = FugleClient()


def _validate_stock(text: str) -> Tuple[bool, Any, str]:
    result = _fugle.verify_stock(text.strip())
    if result:
        return True, result, ""
    return False, None, f"找不到「{text}」，請重新輸入股票名稱或代號"


class PostMarketService(ScriptedService):
    name = "post_market"
    steps = [
        Step("stock_info", "請問要分析哪支股票？（輸入名稱或代號）", _validate_stock),
    ]

    def on_complete(self, uid: str, draft: dict, store, line, reply_token: str) -> None:
        stock_info = draft.get("stock_info", {})
        cfg = {
            "stock_id": stock_info.get("stock_id"),
            "stock_name": stock_info.get("stock_name"),
            "cost_price": None,
        }
        swing_cfg = {}
        try:
            with open("config.json", encoding="utf-8") as f:
                swing_cfg = json.load(f)
        except Exception:
            pass

        line.reply(reply_token, "⏳ 分析中，請稍候...")
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.POSTMARKET)
        if result:
            line.push(uid, f"{result['title']}\n\n{result['message']}")
            DiscordNotifier().send(result["title"], result["message"], result["color"])
            for alert in result["alerts"]:
                line.push(uid, f"{alert.title}\n\n{alert.message}")
                DiscordNotifier().send(alert.title, alert.message, alert.color)
        else:
            line.push(uid, "⚠️ 分析失敗，請確認股票代號是否正確。")
        store.clear_service_state(uid)
```

- [ ] **Step 4: 執行語法檢查**

```bash
python3 -c "from bot.services.stock_monitor import AddStockService; print('OK')"
python3 -c "from bot.services.pre_market import PreMarketService; print('OK')"
python3 -c "from bot.services.post_market import PostMarketService; print('OK')"
```

Expected: 三行都印 `OK`

- [ ] **Step 5: Commit**

```bash
git add bot/services/
git commit -m "✨ feat: add StockMonitor, PreMarket, PostMarket service scripts"
```

---

## Task 6：ServiceRouter + 整合 + 移除舊檔案

**Files:**
- Create: `bot/router.py`
- Create: `tests/test_router.py`
- Modify: `bot/server.py`
- Modify: `bot/monitor_engine.py`
- Modify: `start_bot.sh`
- Delete: `bot/handlers.py`, `bot/state_machine.py`, `bot/claude_parser.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_router.py`：

```python
"""test_router.py — ServiceRouter 測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)

from bot.router import handle_message, handle_follow

MENU_TEXT = "Smart Monitor"


def _make_deps(service=None, step=0, draft=None):
    store = MagicMock()
    store.check_cooldown.return_value = False
    store.get_current_service.return_value = service
    store.get_current_step.return_value = step
    store.get_draft.return_value = draft or {}
    store.get_plan.return_value = "basic"
    line = MagicMock()
    return store, line


def test_follow_sends_welcome(tmp_path):
    store, line = _make_deps()
    handle_follow("u1", store, line)
    assert line.push.call_count == 2


def test_unknown_input_shows_menu():
    store, line = _make_deps()
    handle_message("u1", "你好", store, line, "tok")
    text = line.reply.call_args[0][1]
    assert MENU_TEXT in text


def test_select_1_starts_stock_monitor():
    store, line = _make_deps()
    with patch("bot.router.StockMonitorRouter.handle_entry") as mock:
        handle_message("u1", "1", store, line, "tok")
        mock.assert_called_once()


def test_select_2_starts_pre_market():
    store, line = _make_deps()
    with patch("bot.router.PreMarketService.start") as mock:
        handle_message("u1", "2", store, line, "tok")
        mock.assert_called_once()


def test_select_3_starts_post_market():
    store, line = _make_deps()
    with patch("bot.router.PostMarketService.start") as mock:
        handle_message("u1", "3", store, line, "tok")
        mock.assert_called_once()


def test_service_in_progress_routes_to_service():
    store, line = _make_deps(service="pre_market")
    with patch("bot.router.PreMarketService.handle_input", return_value="CONTINUE") as mock:
        handle_message("u1", "2330", store, line, "tok")
        mock.assert_called_once()


def test_cancel_during_service_shows_menu():
    store, line = _make_deps(service="pre_market")
    with patch("bot.router.PreMarketService.handle_input", return_value="CANCEL"):
        handle_message("u1", "取消", store, line, "tok")
    store.clear_service_state.assert_called_once_with("u1")
    text = line.reply.call_args[0][1]
    assert MENU_TEXT in text


def test_cooldown_blocks_message():
    store, line = _make_deps()
    store.check_cooldown.return_value = True
    handle_message("u1", "1", store, line, "tok")
    text = line.reply.call_args[0][1]
    assert "太快" in text


def test_no_permission_blocks_service():
    store, line = _make_deps()
    store.get_plan.return_value = "free"
    handle_message("u1", "2", store, line, "tok")  # 盤前分析需要 basic
    text = line.reply.call_args[0][1]
    assert "升級" in text
```

- [ ] **Step 2: 執行確認失敗**

```bash
python3 -m pytest tests/test_router.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'bot.router'`

- [ ] **Step 3: 實作 `bot/router.py`**

```python
"""
router.py — ServiceRouter 主路由
取代原有的 handlers.py，使用純數字選單引導使用者
"""

from bot.services.stock_monitor import AddStockService, _show_watchlist, MAX_STOCKS
from bot.services.pre_market import PreMarketService
from bot.services.post_market import PostMarketService
from bot.user_store import UserStore

COOLDOWN_BLOCK_SEC = 60

# 服務實例（singleton）
_ADD_STOCK    = AddStockService()
_PRE_MARKET   = PreMarketService()
_POST_MARKET  = PostMarketService()

# 服務名稱 → 實例對應
_SERVICE_MAP = {
    "stock_monitor_add":     _ADD_STOCK,
    "stock_monitor_confirm": None,  # 等待確認，特殊處理
    "pre_market":            _PRE_MARKET,
    "post_market":           _POST_MARKET,
}

# 服務權限設定
SERVICE_PERMISSIONS = {
    "1": ["free", "basic", "pro"],   # 股票監控
    "2": ["basic", "pro"],           # 盤前分析
    "3": ["basic", "pro"],           # 盤後分析
}

WELCOME_MSG_1 = (
    "👋 你好！我是 Smart Monitor 股市助理。\n\n"
    "我能幫你監控個股、分析盤勢，\n"
    "在關鍵時刻即時通知你。\n\n"
    "⚠️ 所有對話只有你和我，其他人看不到。\n"
    "📌 本助理依設定條件發送提醒，不構成投資建議。"
)

WELCOME_MSG_2 = _build_menu()


def _build_menu() -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 Smart Monitor\n\n"
        "請選擇服務：\n"
        "1️⃣ 股票監控\n"
        "2️⃣ 盤前分析\n"
        "3️⃣ 盤後分析\n\n"
        "輸入數字選擇，或輸入「狀態」查看監控清單\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


def handle_follow(uid: str, store, line) -> None:
    """處理加好友事件"""
    line.push(uid, WELCOME_MSG_1)
    line.push(uid, _build_menu())


def handle_message(uid: str, text: str, store, line, reply_token: str) -> None:
    """處理訊息事件"""
    text = text.strip()

    # 1. 冷卻檢查
    if store.check_cooldown(uid):
        line.reply(reply_token, f"⚠️ 傳送太快，請稍後再試。")
        return

    # 2. 問答進行中 → 交給對應服務處理
    current = store.get_current_service(uid)
    if current:
        _route_to_service(uid, current, text, store, line, reply_token)
        return

    # 3. 處理選單指令
    _handle_menu(uid, text, store, line, reply_token)


def _route_to_service(uid: str, service_name: str, text: str,
                      store, line, reply_token: str) -> None:
    """將訊息路由到目前進行中的服務"""
    # 特殊：等待確認狀態
    if service_name == "stock_monitor_confirm":
        _handle_confirm(uid, text, store, line, reply_token)
        return

    svc = _SERVICE_MAP.get(service_name)
    if svc is None:
        store.clear_service_state(uid)
        line.reply(reply_token, _build_menu())
        return

    result = svc.handle_input(uid, text, store, line, reply_token)
    if result == "CANCEL":
        store.clear_service_state(uid)
        line.reply(reply_token, _build_menu())
    elif result == "DONE":
        store.clear_service_state(uid)


def _handle_confirm(uid: str, text: str, store, line, reply_token: str) -> None:
    """處理股票監控的確認步驟"""
    if text in ("確認", "yes", "ok"):
        draft = store.get_draft(uid)
        stock_info = draft.get("stock_info", {})
        stock = {
            "stock_id": stock_info.get("stock_id"),
            "stock_name": stock_info.get("stock_name"),
            "total_shares": draft.get("total_shares"),
            "cost_price": draft.get("cost_price"),
            "stop_loss_moving": draft.get("stop_loss_moving"),
            "target_stage_1": None,
        }
        try:
            store.add_stock(uid, stock)
            store.clear_service_state(uid)
            msg = _show_watchlist(uid, store, line)
            line.reply(reply_token,
                       f"✅ 已開始監控 {stock['stock_name']}（{stock['stock_id']}）\n\n{msg}")
        except ValueError as e:
            store.clear_service_state(uid)
            line.reply(reply_token, f"⚠️ {e}")
    elif text in ("取消", "cancel"):
        store.clear_service_state(uid)
        line.reply(reply_token, _build_menu())
    else:
        line.reply(reply_token, "請輸入「確認」開始監控，或「取消」重新設定。")


def _handle_menu(uid: str, text: str, store, line, reply_token: str) -> None:
    """處理主選單指令"""
    if text == "狀態":
        msg = _show_watchlist(uid, store, line)
        line.reply(reply_token, msg)
        return

    if text in ("說明", "help"):
        line.reply(reply_token, _build_menu())
        return

    # 股票監控子指令（新增/修改/刪除）
    if text == "新增" or (text.startswith("修改 ") or text.startswith("刪除 ")):
        _handle_stock_sub_command(uid, text, store, line, reply_token)
        return

    # 數字選單
    if text not in ("1", "2", "3"):
        line.reply(reply_token, _build_menu())
        return

    # 權限檢查
    plan = store.get_plan(uid)
    allowed_plans = SERVICE_PERMISSIONS.get(text, [])
    if plan not in allowed_plans:
        line.reply(reply_token,
                   "⚠️ 此功能需要升級方案才能使用。\n請聯絡管理員了解升級方式。")
        return

    # 啟動對應服務
    if text == "1":
        StockMonitorRouter.handle_entry(uid, store, line, reply_token)
    elif text == "2":
        _PRE_MARKET.start(uid, store, line, reply_token)
    elif text == "3":
        _POST_MARKET.start(uid, store, line, reply_token)


def _handle_stock_sub_command(uid: str, text: str, store, line, reply_token: str) -> None:
    """處理股票監控的新增/修改/刪除指令"""
    plan = store.get_plan(uid)
    if plan not in SERVICE_PERMISSIONS["1"]:
        line.reply(reply_token, "⚠️ 此功能需要升級方案才能使用。")
        return

    if text == "新增":
        stocks = store.get_watchlist(uid)
        if len(stocks) >= MAX_STOCKS:
            line.reply(reply_token,
                       f"⚠️ 你已達到監控上限（{MAX_STOCKS}/{MAX_STOCKS}）\n"
                       f"請先刪除一支：刪除 1")
            return
        _ADD_STOCK.start(uid, store, line, reply_token)
        return

    if text.startswith("刪除 "):
        try:
            idx = int(text.split()[1]) - 1
            stocks = store.get_watchlist(uid)
            if idx < 0 or idx >= len(stocks):
                line.reply(reply_token, "⚠️ 請輸入有效的序號，例如：刪除 1")
                return
            name = stocks[idx]["stock_name"]
            store.remove_stock(uid, idx)
            msg = _show_watchlist(uid, store, line)
            line.reply(reply_token, f"✅ 已刪除 {name} 的監控\n\n{msg}")
        except (ValueError, IndexError):
            line.reply(reply_token, "⚠️ 請輸入有效的序號，例如：刪除 1")
        return

    if text.startswith("修改 "):
        try:
            idx = int(text.split()[1]) - 1
            stocks = store.get_watchlist(uid)
            if idx < 0 or idx >= len(stocks):
                line.reply(reply_token, "⚠️ 請輸入有效的序號，例如：修改 1")
                return
            store.set_service_state(uid, "stock_monitor_add", step=0,
                                    draft={}, edit_index=idx)
            _ADD_STOCK.start(uid, store, line, reply_token)
        except (ValueError, IndexError):
            line.reply(reply_token, "⚠️ 請輸入有效的序號，例如：修改 1")
        return


class StockMonitorRouter:
    """股票監控服務的入口路由"""

    @staticmethod
    def handle_entry(uid: str, store, line, reply_token: str) -> None:
        """顯示監控清單或直接進入新增流程"""
        stocks = store.get_watchlist(uid)
        if not stocks:
            _ADD_STOCK.start(uid, store, line, reply_token)
        else:
            msg = _show_watchlist(uid, store, line)
            line.reply(reply_token, msg)
```

- [ ] **Step 4: 執行測試**

```bash
python3 -m pytest tests/test_router.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 更新 `bot/server.py`**

將 `bot/server.py` 中的 import 從 handlers 改為 router：

```python
# 舊
from bot.handlers import handle_follow, handle_message
from bot.claude_parser import load_stock_map

# 新
from bot.router import handle_follow, handle_message
from bot.data.fugle_client import FugleClient

_fugle_client = FugleClient()
```

在 lifespan 中：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    _clear_user_data()
    _fugle_client.load_stock_map()  # 改用新的 FugleClient
    discord = DiscordNotifier()
    _engine = MonitorEngine(_store, _line, discord)
    _engine.start()
    yield
    if _engine:
        _engine.stop()
```

- [ ] **Step 6: 更新 `bot/monitor_engine.py`**

`MonitorEngine._check_user` 改用新版 `UserStore` 的 watchlist 結構：

```python
def _scan_all(self):
    users = self._store.get_all_monitoring_users()
    for uid in users:
        try:
            stocks = self._store.get_watchlist(uid)
            for idx, stock_cfg in enumerate(stocks):
                alerts = self._check_stock(uid, idx, stock_cfg)
                if alerts:
                    self._dispatch(uid, alerts)
        except Exception as e:
            print(f"[monitor] 處理使用者 {uid} 失敗：{e}")

def _check_stock(self, uid: str, stock_index: int, cfg: dict) -> list:
    """查詢單支股票股價並比對條件"""
    stock_id = cfg.get("stock_id")
    stock_name = cfg.get("stock_name", "")
    cost = cfg.get("cost_price")
    stop = cfg.get("stop_loss_moving")
    target1 = cfg.get("target_stage_1")

    price = fetch_price(stock_id)
    if price is None:
        return []

    alerts = []

    if (stop is not None and price <= stop
            and not self._store.get_alert_fired(uid, stock_index, "stop")):
        pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
        alerts.append({
            "title": "⚠️ 停損觸發",
            "message": (f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                        f"已跌破停損價 {stop} 元，建議評估出場。"),
            "color": 0xE74C3C,
            "fired_key": "stop",
            "stock_index": stock_index,
        })

    if (target1 is not None and price >= target1
            and not self._store.get_alert_fired(uid, stock_index, "target1")):
        pct = f"{(price - cost) / cost * 100:+.2f}%" if cost else ""
        alerts.append({
            "title": "🎯 目標一達成",
            "message": (f"【{stock_id} {stock_name}】現價 {price} 元 {pct}\n"
                        f"已達目標一 {target1} 元，可考慮獲利了結。"),
            "color": 0x2ECC71,
            "fired_key": "target1",
            "stock_index": stock_index,
        })

    return alerts

def _dispatch(self, uid: str, alerts: list) -> None:
    for alert in alerts:
        self._line.push(uid, f"{alert['title']}\n\n{alert['message']}")
        self._discord.send(alert["title"], alert["message"], alert["color"])
        self._store.set_alert_fired(uid, alert["stock_index"], alert["fired_key"], True)
```

- [ ] **Step 7: 更新 `start_bot.sh`**

移除 `CLEAR_ON_START=1`，保留 `FORCE_TRADING_HOURS=1`（測試用）：

```bash
#!/bin/bash
cd "$(dirname "$0")"
source .env

echo "[Smart Monitor Bot] 啟動 Cloudflare Tunnel..."
cloudflared tunnel run smart-monitor &
TUNNEL_PID=$!

for i in $(seq 1 15); do
    if curl -s --max-time 2 https://smart.aurabizon.com/health > /dev/null 2>&1; then
        echo "[Smart Monitor Bot] Tunnel 已就緒"
        break
    fi
    sleep 1
done

echo "[Smart Monitor Bot] 啟動 webhook server..."
export FORCE_TRADING_HOURS=1
python3 -m uvicorn bot.server:app --port 8000

kill $TUNNEL_PID 2>/dev/null
```

- [ ] **Step 8: 移除舊檔案**

```bash
rm bot/handlers.py bot/state_machine.py bot/claude_parser.py
```

- [ ] **Step 9: 執行全部測試**

```bash
python3 -m pytest tests/test_crypto.py tests/test_fugle_client.py \
  tests/test_user_store_v2.py tests/test_scripted_service.py \
  tests/test_router.py -v
```

Expected: 全部 PASS

- [ ] **Step 10: 啟動確認**

```bash
source .env
timeout 8 python3 -m uvicorn bot.server:app --port 8000 2>&1 | head -15
```

Expected:
```
[server] 使用者資料已清空（測試模式）  ← 或無此行（CLEAR_ON_START 未設）
[FugleClient] 已載入 XXXX 筆股票資料
[monitor] 背景監控引擎已啟動
```

- [ ] **Step 11: Commit**

```bash
git add bot/router.py bot/server.py bot/monitor_engine.py start_bot.sh
git rm bot/handlers.py bot/state_machine.py bot/claude_parser.py
git commit -m "✨ feat: Phase A complete - ServiceRouter, scripted services, multi-stock watchlist"
git push origin main
```

---

## 自我審查

**Spec coverage:**
- ✅ 純數字選單（1/2/3），移除 Gemini
- ✅ 問答腳本引擎（ScriptedService + Step）
- ✅ 股票監控：新增/修改/刪除，最多 3 支
- ✅ 盤前/盤後分析服務腳本
- ✅ AES-256-GCM 加密敏感欄位
- ✅ plan 欄位 + 權限中介層
- ✅ 移除 CLEAR_ON_START 預設，重啟後自動恢復監控
- ✅ FugleClient 統一封裝
- ✅ MonitorEngine 更新為多股票結構

**Placeholder scan:** 無 TBD 或待補項目

**Type consistency:**
- `Step.validate` 回傳 `(bool, Any, str)`，`handle_input` 正確解構
- `store.get_alert_fired(uid, stock_index, alert_key)` 新增 `stock_index` 參數，`monitor_engine._dispatch` 使用 `alert["stock_index"]` 一致
- `store.get_watchlist` 回傳解密後的 list，`_show_watchlist` 和 `_check_stock` 都接收此格式
