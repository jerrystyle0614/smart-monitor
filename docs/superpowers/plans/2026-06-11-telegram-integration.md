# Telegram Bot 整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在現有 LINE Bot 架構下新增 Telegram Bot 支援，兩個平台並行，共用 router.py + services/ 邏輯。

**Architecture:** UserStore 加入 platform 參數將資料路徑分離為 `users/line/` 和 `users/telegram/`；TelegramClient 實作與 LineClient 相同的 push/reply 介面；MonitorEngine 擴充為支援多個 store/client；Telegram webhook 掛載在同一個 FastAPI app 的 `/telegram/webhook`。

**Tech Stack:** python-telegram-bot v20+（async）、現有 FastAPI、現有 router.py/services/（不動）

---

## 檔案結構

### 新增
- `bot/telegram/client.py` — TelegramClient（push/reply/send_menu）
- `bot/telegram/webhook.py` — Telegram webhook 路由（register 函式）
- `bot/telegram/keyboard.py` — Inline Keyboard 產生器（主選單 + 取消按鈕）
- `bot/telegram/invite.py` — 邀請碼驗證/綁定（verify_invite、bind_invite）
- `set_invite.py` — CLI 產生邀請碼
- `data/invites.json` — 邀請碼儲存（初始為空 `{}`）
- `tests/test_telegram_client.py`
- `tests/test_telegram_invite.py`
- `tests/test_telegram_webhook.py`

### 修改
- `bot/user_store.py` — 新增 `platform` 參數，`data_dir` 改為 `users/{platform}`
- `bot/monitor_engine.py` — `__init__` 改接受 `stores: dict` + `clients: dict`
- `bot/server.py` — lifespan 初始化兩個 store/client，掛載 Telegram webhook
- `bot/scheduler/jobs.py` — 移除寫死的 `LineClient`，改由外部注入
- `requirements.txt` — 新增 `python-telegram-bot>=20.0`

### 資料遷移
- `users/{uid}/` → `users/line/{uid}/`（一次性 script，含驗證）

---

## Task 1: UserStore 支援 platform 參數

**Files:**
- Modify: `bot/user_store.py`
- Test: `tests/test_user_store.py`

- [ ] **Step 1: 讀現有測試確認基線**

```bash
cd /Users/jerry/Projects/Personal/experiments/smart-monitor
python -m pytest tests/test_user_store.py -q
```
Expected: 全部 PASS（記錄數量作為基線）

- [ ] **Step 2: 寫失敗測試**

在 `tests/test_user_store.py` 尾端加入：

```python
def test_platform_line_uses_line_subdir(tmp_path):
    """platform='line' 時資料應存在 users/line/{uid}/ 下"""
    store = UserStore(platform="line")
    store.data_dir = str(tmp_path / "users" / "line")
    Path(store.data_dir).mkdir(parents=True, exist_ok=True)
    store.set_plan("U123", "pro")
    assert (tmp_path / "users" / "line" / "U123" / "profile.json").exists()

def test_platform_telegram_uses_telegram_subdir(tmp_path):
    """platform='telegram' 時資料應存在 users/telegram/{chat_id}/ 下"""
    store = UserStore(platform="telegram")
    store.data_dir = str(tmp_path / "users" / "telegram")
    Path(store.data_dir).mkdir(parents=True, exist_ok=True)
    store.set_plan("123456789", "basic")
    assert (tmp_path / "users" / "telegram" / "123456789" / "profile.json").exists()

def test_default_platform_is_line(tmp_path):
    """預設 platform 應為 line"""
    store = UserStore()
    assert "line" in store.data_dir
```

- [ ] **Step 3: 執行確認失敗**

```bash
python -m pytest tests/test_user_store.py::test_platform_line_uses_line_subdir tests/test_user_store.py::test_platform_telegram_uses_telegram_subdir tests/test_user_store.py::test_default_platform_is_line -v
```
Expected: FAIL（UserStore 不接受 platform 參數）

- [ ] **Step 4: 修改 UserStore**

在 `bot/user_store.py` 中修改 `__init__`：

```python
class UserStore:
    data_dir = os.environ.get("USER_DATA_DIR", "users/line")

    def __init__(self, platform: str = "line"):
        env_val = os.environ.get("USER_DATA_DIR")
        if env_val and env_val != UserStore.data_dir:
            self.data_dir = env_val
        else:
            self.data_dir = f"users/{platform}"
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: 執行確認通過**

```bash
python -m pytest tests/test_user_store.py -q
```
Expected: 全部 PASS（包含新增的 3 個測試）

- [ ] **Step 6: Commit**

```bash
git add bot/user_store.py tests/test_user_store.py
git commit -m "✨ feat: add platform parameter to UserStore for path isolation"
```

---

## Task 2: 資料遷移 users/ → users/line/

**Files:**
- Create: `migrate_users.py`

- [ ] **Step 1: 確認現有資料**

```bash
ls users/
```
Expected: 看到多個 `U...` 開頭的目錄

- [ ] **Step 2: 建立遷移 script**

建立 `migrate_users.py`：

```python
"""
migrate_users.py — 將 users/{uid}/ 遷移至 users/line/{uid}/
執行前請先備份 users/ 目錄
"""
import shutil
from pathlib import Path

SRC = Path("users")
DST = Path("users/line")

def migrate():
    if not SRC.exists():
        print("users/ 不存在，略過")
        return

    DST.mkdir(parents=True, exist_ok=True)

    moved = 0
    skipped = 0
    for user_dir in SRC.iterdir():
        # 只搬移 LINE uid（U 開頭）或純數字以外的目錄
        if not user_dir.is_dir():
            continue
        name = user_dir.name
        # 跳過已遷移的 line/ telegram/ 子目錄
        if name in ("line", "telegram"):
            continue

        dst_user = DST / name
        if dst_user.exists():
            print(f"  [skip] {name} 已存在於 users/line/")
            skipped += 1
            continue

        shutil.copytree(str(user_dir), str(dst_user))
        print(f"  [copy] {name} → users/line/{name}")
        moved += 1

    print(f"\n完成：搬移 {moved} 個，略過 {skipped} 個")
    print("確認正確後，手動刪除 users/ 下的舊目錄：")
    for user_dir in SRC.iterdir():
        if user_dir.is_dir() and user_dir.name not in ("line", "telegram"):
            print(f"  rm -rf {user_dir}")

if __name__ == "__main__":
    migrate()
```

- [ ] **Step 3: 執行遷移（複製，不刪除原始）**

```bash
python migrate_users.py
```
Expected: 看到每個 uid 的 `[copy]` 訊息，無 error

- [ ] **Step 4: 確認遷移結果**

```bash
ls users/line/
```
Expected: 看到與 `users/` 相同的 uid 目錄列表

- [ ] **Step 5: 確認 server 仍正常（使用新路徑）**

```bash
source .env && python3 -c "
from bot.user_store import UserStore
store = UserStore(platform='line')
users = store.get_all_monitoring_users()
print('LINE users:', users)
"
```
Expected: 印出原有使用者的 uid 列表

- [ ] **Step 6: 刪除舊目錄**

```bash
# 確認 users/line/ 內容正確後才執行
for d in users/U*/; do rm -rf "$d"; done
```

- [ ] **Step 7: Commit**

```bash
git add migrate_users.py
git commit -m "✨ feat: add user data migration script for platform path separation"
```

---

## Task 3: MonitorEngine 支援多 store/client

**Files:**
- Modify: `bot/monitor_engine.py`
- Test: `tests/test_monitor_engine.py`

- [ ] **Step 1: 讀現有測試確認基線**

```bash
python -m pytest tests/test_monitor_engine.py -q
```
Expected: 全部 PASS

- [ ] **Step 2: 寫失敗測試**

在 `tests/test_monitor_engine.py` 尾端加入：

```python
def test_monitor_engine_accepts_stores_and_clients_dict():
    """MonitorEngine 應接受 stores dict 和 clients dict"""
    from bot.monitor_engine import MonitorEngine
    from unittest.mock import MagicMock

    line_store = MagicMock()
    tg_store = MagicMock()
    line_client = MagicMock()
    tg_client = MagicMock()
    discord = MagicMock()

    engine = MonitorEngine(
        stores={"line": line_store, "telegram": tg_store},
        clients={"line": line_client, "telegram": tg_client},
        discord=discord,
    )
    assert engine._stores["line"] is line_store
    assert engine._clients["telegram"] is tg_client

def test_monitor_engine_get_client_returns_correct_client():
    """_get_client 應根據 platform 回傳對應 client"""
    from bot.monitor_engine import MonitorEngine
    from unittest.mock import MagicMock

    line_client = MagicMock()
    tg_client = MagicMock()
    engine = MonitorEngine(
        stores={"line": MagicMock(), "telegram": MagicMock()},
        clients={"line": line_client, "telegram": tg_client},
        discord=MagicMock(),
    )
    assert engine._get_client("telegram") is tg_client
    assert engine._get_client("line") is line_client
```

- [ ] **Step 3: 執行確認失敗**

```bash
python -m pytest tests/test_monitor_engine.py::test_monitor_engine_accepts_stores_and_clients_dict tests/test_monitor_engine.py::test_monitor_engine_get_client_returns_correct_client -v
```
Expected: FAIL

- [ ] **Step 4: 修改 MonitorEngine.__init__**

在 `bot/monitor_engine.py` 中修改 `MonitorEngine.__init__`：

```python
class MonitorEngine:
    def __init__(self, stores, clients, discord):
        # stores: {"line": UserStore, "telegram": UserStore}
        # clients: {"line": LineClient, "telegram": TelegramClient}
        self._stores = stores
        self._clients = clients
        self._discord = discord
        # 向下相容：保留 _store/_line 指向 line 平台
        self._store = stores.get("line") or next(iter(stores.values()))
        self._line = clients.get("line") or next(iter(clients.values()))
        self._running = False
        self._thread = None
        self._analysis_fired = set()

    def _get_client(self, platform: str):
        return self._clients.get(platform, self._line)

    def _get_store(self, platform: str):
        return self._stores.get(platform, self._store)
```

並在 `_scan_all` 和 `_run_analysis_all` 中改為遍歷所有平台：

```python
def _scan_all(self):
    """掃描所有平台的 MONITORING 使用者並處理警報"""
    for platform, store in self._stores.items():
        client = self._get_client(platform)
        users = store.get_all_monitoring_users()
        for uid in users:
            try:
                alerts = self._check_user_with_store(uid, store)
                if alerts:
                    self._dispatch_with_client(uid, alerts, client)
            except Exception as e:
                print(f"[monitor] 處理使用者 {uid}（{platform}）失敗：{e}")
```

在原本 `_check_user` 改名為 `_check_user_with_store(uid, store)`，將 `self._store` 替換為傳入的 `store` 參數；`_dispatch` 改名為 `_dispatch_with_client(uid, alerts, client)`，將 `self._line` 替換為傳入的 `client` 參數。

`_run_analysis_all` 同理，改為：

```python
def _run_analysis_all(self, mode) -> None:
    for platform, store in self._stores.items():
        client = self._get_client(platform)
        self._run_analysis_for_store(store, client, mode)
```

將原本 `_run_analysis_all` 的邏輯搬入新的 `_run_analysis_for_store(store, client, mode)`，把所有 `self._store` → `store`，`self._line` → `client`。

- [ ] **Step 5: 更新 server.py lifespan**

在 `bot/server.py` 中修改 lifespan 初始化：

```python
_line_store = UserStore(platform="line")
_tg_store   = UserStore(platform="telegram")
_line = LineClient()
# TelegramClient 在 Task 6 完成前先用 None 佔位
_engine = MonitorEngine(
    stores={"line": _line_store, "telegram": _tg_store},
    clients={"line": _line},
    discord=discord,
)
```

並將 `line_webhook.register(app, _store, _line)` 改為 `line_webhook.register(app, _line_store, _line)`。

- [ ] **Step 6: 執行所有測試確認通過**

```bash
python -m pytest tests/test_monitor_engine.py -q
```
Expected: 全部 PASS（含新增 2 個）

- [ ] **Step 7: 確認 server 啟動正常**

```bash
source .env && python3 -c "from bot.server import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add bot/monitor_engine.py bot/server.py tests/test_monitor_engine.py
git commit -m "✨ feat: extend MonitorEngine to support multiple platform stores/clients"
```

---

## Task 4: 邀請碼系統

**Files:**
- Create: `bot/telegram/invite.py`
- Create: `data/invites.json`
- Create: `set_invite.py`
- Test: `tests/test_telegram_invite.py`

- [ ] **Step 1: 建立空的 invites.json**

```bash
mkdir -p data
echo '{}' > data/invites.json
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_telegram_invite.py`：

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_generate_invite_code_format():
    """產生的邀請碼格式應為 SM + 4 位大寫英數字"""
    from bot.telegram.invite import generate_code
    code = generate_code()
    assert code.startswith("SM")
    assert len(code) == 6
    assert code[2:].isupper() or code[2:].isdigit() or code[2:].isalnum()


def test_verify_invite_valid(tmp_path):
    """有效且未使用的邀請碼應通過驗證，回傳方案名稱"""
    from bot.telegram.invite import verify_invite, INVITES_PATH
    invites = {"SM8K3F": {"plan": "pro", "used": False, "chat_id": None}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SM8K3F")
    assert result == "pro"


def test_verify_invite_already_used(tmp_path):
    """已使用的邀請碼應回傳 None"""
    from bot.telegram.invite import verify_invite, INVITES_PATH
    invites = {"SMABC1": {"plan": "basic", "used": True, "chat_id": "999"}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SMABC1")
    assert result is None


def test_verify_invite_invalid_code(tmp_path):
    """不存在的邀請碼應回傳 None"""
    from bot.telegram.invite import verify_invite, INVITES_PATH
    inv_path = tmp_path / "invites.json"
    inv_path.write_text("{}")
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        result = verify_invite("SMXXXX")
    assert result is None


def test_bind_invite_marks_used(tmp_path):
    """bind_invite 應將邀請碼標為 used 並記錄 chat_id"""
    from bot.telegram.invite import bind_invite, INVITES_PATH
    invites = {"SM8K3F": {"plan": "pro", "used": False, "chat_id": None}}
    inv_path = tmp_path / "invites.json"
    inv_path.write_text(json.dumps(invites))
    with patch("bot.telegram.invite.INVITES_PATH", inv_path):
        bind_invite("SM8K3F", "123456789")
        data = json.loads(inv_path.read_text())
    assert data["SM8K3F"]["used"] is True
    assert data["SM8K3F"]["chat_id"] == "123456789"
```

- [ ] **Step 3: 執行確認失敗**

```bash
python -m pytest tests/test_telegram_invite.py -v
```
Expected: FAIL（模組不存在）

- [ ] **Step 4: 實作 bot/telegram/invite.py**

```python
"""
telegram/invite.py — 邀請碼管理
格式：SM + 4 位大寫英數字（例如 SM8K3F）
"""
import json
import random
import string
from pathlib import Path
from typing import Optional

INVITES_PATH = Path("data/invites.json")


def _load() -> dict:
    if not INVITES_PATH.exists():
        return {}
    try:
        return json.loads(INVITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    INVITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    INVITES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_code() -> str:
    """產生一個唯一的邀請碼（SM + 4 位大寫英數字）"""
    data = _load()
    while True:
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        code = f"SM{suffix}"
        if code not in data:
            return code


def verify_invite(code: str) -> Optional[str]:
    """驗證邀請碼是否有效。有效回傳方案名稱，無效回傳 None。"""
    data = _load()
    entry = data.get(code)
    if not entry:
        return None
    if entry.get("used"):
        return None
    return entry.get("plan")


def bind_invite(code: str, chat_id: str) -> None:
    """將邀請碼標為已使用並記錄 chat_id。"""
    data = _load()
    if code in data:
        data[code]["used"] = True
        data[code]["chat_id"] = chat_id
        _save(data)
```

- [ ] **Step 5: 實作 set_invite.py（CLI）**

```python
"""
set_invite.py — 產生邀請碼 CLI
用法：python set_invite.py --plan pro --count 3
"""
import argparse
import json
from bot.telegram.invite import generate_code, INVITES_PATH, _load, _save


def main():
    parser = argparse.ArgumentParser(description="產生 Smart Monitor 邀請碼")
    parser.add_argument("--plan", choices=["free", "basic", "pro"], default="pro")
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    data = _load()
    codes = []
    for _ in range(args.count):
        code = generate_code()
        data[code] = {"plan": args.plan, "used": False, "chat_id": None}
        codes.append(code)

    _save(data)
    print(", ".join(codes))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 執行確認測試通過**

```bash
python -m pytest tests/test_telegram_invite.py -v
```
Expected: 5 個 PASS

- [ ] **Step 7: 測試 CLI**

```bash
python set_invite.py --plan pro --count 2
```
Expected: 印出兩個邀請碼，例如 `SMX9Y2, SM3KF1`，並寫入 `data/invites.json`

- [ ] **Step 8: Commit**

```bash
git add bot/telegram/invite.py set_invite.py data/invites.json tests/test_telegram_invite.py
git commit -m "✨ feat: add Telegram invite code system"
```

---

## Task 5: Telegram Keyboard

**Files:**
- Create: `bot/telegram/keyboard.py`
- Test: `tests/test_telegram_keyboard.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_telegram_keyboard.py`：

```python
def test_main_menu_keyboard_has_5_services():
    """主選單應有 5 個服務按鈕"""
    from bot.telegram.keyboard import main_menu_keyboard
    kb = main_menu_keyboard()
    buttons = [btn for row in kb for btn in row]
    assert len(buttons) == 5


def test_main_menu_keyboard_callback_data():
    """每個按鈕的 callback_data 應對應 1-5"""
    from bot.telegram.keyboard import main_menu_keyboard
    kb = main_menu_keyboard()
    datas = [btn["callback_data"] for row in kb for btn in row]
    assert set(datas) == {"1", "2", "3", "4", "5"}


def test_cancel_keyboard_has_one_button():
    """取消鍵盤應只有一個 ❌ 取消 按鈕"""
    from bot.telegram.keyboard import cancel_keyboard
    kb = cancel_keyboard()
    buttons = [btn for row in kb for btn in row]
    assert len(buttons) == 1
    assert buttons[0]["callback_data"] == "cancel"
```

- [ ] **Step 2: 執行確認失敗**

```bash
python -m pytest tests/test_telegram_keyboard.py -v
```
Expected: FAIL

- [ ] **Step 3: 實作 bot/telegram/keyboard.py**

```python
"""
telegram/keyboard.py — Inline Keyboard 產生器
回傳 list[list[dict]] 格式，供 TelegramClient 使用
"""
from typing import List


def main_menu_keyboard() -> List[List[dict]]:
    """主選單 Inline Keyboard（2-2-1 排列）"""
    return [
        [
            {"text": "1️⃣ 股票監控", "callback_data": "1"},
            {"text": "2️⃣ 盤前分析", "callback_data": "2"},
        ],
        [
            {"text": "3️⃣ 盤後分析", "callback_data": "3"},
            {"text": "4️⃣ 選股推薦", "callback_data": "4"},
        ],
        [
            {"text": "5️⃣ ETF 推薦", "callback_data": "5"},
        ],
    ]


def cancel_keyboard() -> List[List[dict]]:
    """問答流程中的取消按鈕"""
    return [
        [{"text": "❌ 取消", "callback_data": "cancel"}],
    ]


def to_inline_markup(keyboard: List[List[dict]]) -> dict:
    """將 list[list[dict]] 轉為 Telegram InlineKeyboardMarkup dict"""
    return {
        "inline_keyboard": [
            [
                {"text": btn["text"], "callback_data": btn["callback_data"]}
                for btn in row
            ]
            for row in keyboard
        ]
    }
```

- [ ] **Step 4: 執行確認通過**

```bash
python -m pytest tests/test_telegram_keyboard.py -v
```
Expected: 3 個 PASS

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/keyboard.py tests/test_telegram_keyboard.py
git commit -m "✨ feat: add Telegram inline keyboard builder"
```

---

## Task 6: TelegramClient

**Files:**
- Create: `bot/telegram/client.py`
- Modify: `requirements.txt`
- Test: `tests/test_telegram_client.py`

- [ ] **Step 1: 安裝套件**

```bash
pip install "python-telegram-bot>=20.0"
echo "python-telegram-bot>=20.0" >> requirements.txt
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_telegram_client.py`：

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_telegram_client_push_calls_send_message():
    """push() 應呼叫 Telegram sendMessage API"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.push("123456789", "hello")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "sendMessage" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "123456789"
        assert call_args[1]["json"]["text"] == "hello"


def test_telegram_client_push_silent_on_error():
    """push() 失敗時只印警告，不 raise"""
    with patch("bot.telegram.client.requests.post", side_effect=Exception("net error")):
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.push("123456789", "hello")  # 不應 raise


def test_telegram_client_reply_with_message_id():
    """reply(message_id, text) 應呼叫 sendMessage"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.reply("msg:123456789:999", "pong")
        mock_post.assert_called_once()
        assert "sendMessage" in mock_post.call_args[0][0]


def test_telegram_client_send_menu_includes_keyboard():
    """send_menu() 應發送含 inline_keyboard 的訊息"""
    with patch("bot.telegram.client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from bot.telegram.client import TelegramClient
        client = TelegramClient(token="fake_token")
        client.send_menu("123456789")
        call_json = mock_post.call_args[1]["json"]
        assert "reply_markup" in call_json
        assert "inline_keyboard" in call_json["reply_markup"]
```

- [ ] **Step 3: 執行確認失敗**

```bash
python -m pytest tests/test_telegram_client.py -v
```
Expected: FAIL

- [ ] **Step 4: 實作 bot/telegram/client.py**

```python
"""
telegram/client.py — Telegram Bot API 推播/回覆封裝
介面與 bot/line/client.py 的 LineClient 保持一致（push / reply）
使用 requests 直接呼叫 Bot API（同步），避免引入 async 複雜度
"""
import os
import requests
from typing import Optional
from bot.telegram.keyboard import main_menu_keyboard, to_inline_markup

_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: Optional[str] = None):
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def _url(self, method: str) -> str:
        return _BASE.format(token=self._token, method=method)

    def _post(self, method: str, payload: dict) -> None:
        try:
            resp = requests.post(self._url(method), json=payload, timeout=10)
            if resp.status_code not in (200, 201):
                print(f"[警告] Telegram {method} 失敗：{resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"[警告] Telegram {method} 失敗：{e}")

    def push(self, chat_id: str, text: str) -> None:
        """主動推播訊息給使用者"""
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def reply(self, token: str, text: str) -> None:
        """回覆訊息。token 格式：
        - callback_query → 'cbq:{callback_query_id}:{chat_id}'
        - message → 'msg:{chat_id}:{message_id}'
        """
        parts = token.split(":", 2)
        kind = parts[0] if parts else "msg"

        if kind == "cbq" and len(parts) == 3:
            # answerCallbackQuery（顯示通知）+ sendMessage
            self._post("answerCallbackQuery", {
                "callback_query_id": parts[1],
            })
            self._post("sendMessage", {
                "chat_id": parts[2],
                "text": text,
                "reply_markup": to_inline_markup(main_menu_keyboard())
                if text.startswith("📊") else None,
            })
        else:
            # 純文字 reply
            chat_id = parts[1] if len(parts) >= 2 else token
            self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def send_menu(self, chat_id: str) -> None:
        """發送附 Inline Keyboard 的主選單"""
        self._post("sendMessage", {
            "chat_id": chat_id,
            "text": "📊 Smart Monitor 服務選單\n\n請選擇服務：",
            "reply_markup": to_inline_markup(main_menu_keyboard()),
        })

    def send_with_cancel(self, chat_id: str, text: str) -> None:
        """發送附取消按鈕的訊息（問答中使用）"""
        from bot.telegram.keyboard import cancel_keyboard
        self._post("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": to_inline_markup(cancel_keyboard()),
        })
```

- [ ] **Step 5: 修正 reply 測試中的 null reply_markup**

`reply()` 在非選單情況傳送 `reply_markup: None` 會造成 API 錯誤，修正如下：

```python
    # 在 reply() 的 sendMessage 呼叫中
    payload = {"chat_id": chat_id, "text": text}
    if text.startswith("📊"):
        payload["reply_markup"] = to_inline_markup(main_menu_keyboard())
    self._post("sendMessage", payload)
```

- [ ] **Step 6: 執行確認通過**

```bash
python -m pytest tests/test_telegram_client.py -v
```
Expected: 4 個 PASS

- [ ] **Step 7: Commit**

```bash
git add bot/telegram/client.py requirements.txt tests/test_telegram_client.py
git commit -m "✨ feat: add TelegramClient with push/reply/send_menu interface"
```

---

## Task 7: Telegram Webhook Handler

**Files:**
- Create: `bot/telegram/webhook.py`
- Test: `tests/test_telegram_webhook.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_telegram_webhook.py`：

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_app(store, tg_client):
    app = FastAPI()
    from bot.telegram.webhook import register
    register(app, store, tg_client)
    return app


def test_webhook_text_message_routes_to_handle_message():
    """文字訊息應呼叫 router 的 handle_message"""
    store = MagicMock()
    store.get_plan.return_value = "pro"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 123456789, "is_bot": False, "first_name": "Jerry"},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1700000000,
            "text": "1",
        }
    }
    with patch("bot.telegram.webhook.handle_message") as mock_handle:
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    mock_handle.assert_called_once()
    call_args = mock_handle.call_args[0]
    assert call_args[0] == "123456789"
    assert call_args[1] == "1"


def test_webhook_start_command_unregistered_asks_invite():
    """/start 對未啟用使用者應回覆邀請碼提示"""
    store = MagicMock()
    store.get_plan.return_value = "free"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 2,
        "message": {
            "message_id": 101,
            "from": {"id": 999, "is_bot": False, "first_name": "New"},
            "chat": {"id": 999, "type": "private"},
            "date": 1700000000,
            "text": "/start",
        }
    }
    with patch("bot.telegram.webhook.verify_invite", return_value=None):
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    tg_client.push.assert_called_once()
    assert "邀請碼" in tg_client.push.call_args[0][1]


def test_webhook_callback_query_routes_to_handle_message():
    """Callback query 應呼叫 router 的 handle_message"""
    store = MagicMock()
    store.get_plan.return_value = "pro"
    tg_client = MagicMock()
    app = _make_app(store, tg_client)
    client = TestClient(app)

    payload = {
        "update_id": 3,
        "callback_query": {
            "id": "abc123",
            "from": {"id": 123456789, "is_bot": False, "first_name": "Jerry"},
            "message": {
                "message_id": 200,
                "chat": {"id": 123456789, "type": "private"},
                "date": 1700000000,
                "text": "選單",
            },
            "data": "2",
        }
    }
    with patch("bot.telegram.webhook.handle_message") as mock_handle:
        resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    mock_handle.assert_called_once()
    call_args = mock_handle.call_args[0]
    assert call_args[0] == "123456789"
    assert call_args[1] == "2"
```

- [ ] **Step 2: 執行確認失敗**

```bash
python -m pytest tests/test_telegram_webhook.py -v
```
Expected: FAIL

- [ ] **Step 3: 實作 bot/telegram/webhook.py**

```python
"""
telegram/webhook.py — Telegram Webhook 路由
處理 Telegram Update 事件：/start 邀請碼驗證、訊息、CallbackQuery
"""
import json
import logging
from fastapi import Request

from bot.router import handle_message, handle_follow
from bot.telegram.invite import verify_invite, bind_invite

logger = logging.getLogger(__name__)

# 待啟用狀態：chat_id → 等待邀請碼輸入
_pending_invite: set = set()


def register(app, store, tg_client):
    """將 Telegram webhook 路由掛載到 FastAPI app"""

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request):
        try:
            update = await request.json()
        except Exception:
            return {"ok": False}

        # --- Message（文字訊息）---
        message = update.get("message")
        if message:
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "")
            message_id = str(message.get("message_id", ""))
            if not chat_id or not text:
                return {"ok": True}

            reply_token = f"msg:{chat_id}:{message_id}"
            logger.info("[telegram] chat_id={} text={!r}".format(chat_id, text))

            # /start 指令
            if text.startswith("/start"):
                plan = store.get_plan(chat_id)
                if plan and plan != "free":
                    # 已啟用 → 顯示選單
                    tg_client.send_menu(chat_id)
                else:
                    # 未啟用 → 要求邀請碼
                    _pending_invite.add(chat_id)
                    tg_client.push(chat_id, "👋 歡迎使用 Smart Monitor！\n\n請輸入邀請碼以啟用服務：")
                return {"ok": True}

            # 等待邀請碼輸入
            if chat_id in _pending_invite:
                code = text.strip().upper()
                plan = verify_invite(code)
                if plan:
                    bind_invite(code, chat_id)
                    store.set_plan(chat_id, plan)
                    _pending_invite.discard(chat_id)
                    handle_follow(chat_id, store, tg_client)
                    tg_client.send_menu(chat_id)
                else:
                    tg_client.push(chat_id, "❌ 邀請碼錯誤或已使用，請重新輸入：")
                return {"ok": True}

            # 一般訊息 → 路由
            handle_message(chat_id, text, store, tg_client, reply_token)
            return {"ok": True}

        # --- CallbackQuery（按鈕點擊）---
        callback_query = update.get("callback_query")
        if callback_query:
            query_id = callback_query.get("id", "")
            chat_id = str(callback_query.get("from", {}).get("id", ""))
            data = callback_query.get("data", "")
            if not chat_id or not data:
                return {"ok": True}

            reply_token = f"cbq:{query_id}:{chat_id}"
            logger.info("[telegram] callback chat_id={} data={!r}".format(chat_id, data))
            handle_message(chat_id, data, store, tg_client, reply_token)
            return {"ok": True}

        return {"ok": True}
```

- [ ] **Step 4: 執行確認通過**

```bash
python -m pytest tests/test_telegram_webhook.py -v
```
Expected: 3 個 PASS

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/webhook.py tests/test_telegram_webhook.py
git commit -m "✨ feat: add Telegram webhook handler with invite code flow"
```

---

## Task 8: 整合到 server.py + 設定 Telegram webhook URL

**Files:**
- Modify: `bot/server.py`

- [ ] **Step 1: 更新 server.py lifespan 完整版**

將 `bot/server.py` 改為：

```python
"""
server.py — FastAPI app 主體
負責 lifespan 管理、全域例外處理、health endpoint
LINE webhook：bot/line/webhook.py
Telegram webhook：bot/telegram/webhook.py
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from bot.line.client import LineClient
from bot.line import webhook as line_webhook
from bot.telegram.client import TelegramClient
from bot.telegram import webhook as tg_webhook
from bot.user_store import UserStore
from bot.data.fugle_client import FugleClient
from bot.monitor_engine import MonitorEngine
from bot.scheduler.manager import SchedulerManager
from bot.scheduler.jobs import ScheduledJobs
from notifier import DiscordNotifier

logger = logging.getLogger(__name__)

_line_store = UserStore(platform="line")
_tg_store   = UserStore(platform="telegram")
_line       = LineClient()
_tg         = TelegramClient()
_engine     = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine

    try:
        from bot.data.fugle_client import FugleClient
        FugleClient().load_stock_map()
        logger.info("[startup] Stock map loaded")
    except Exception as e:
        logger.error("[startup] Stock map load failed: {}".format(e))

    discord = DiscordNotifier()
    _engine = MonitorEngine(
        stores={"line": _line_store, "telegram": _tg_store},
        clients={"line": _line, "telegram": _tg},
        discord=discord,
    )
    _engine.start()

    try:
        scheduled_jobs = ScheduledJobs(
            user_store=_line_store,
            line_client=_line,
            stock_picker_engine=None,
        )
        scheduler_manager = SchedulerManager()
        scheduler_manager.start(scheduled_jobs)
        app.state.scheduler_manager = scheduler_manager
        logger.info("[startup] Scheduler manager initialized and started")
    except Exception as e:
        logger.error("[startup] Scheduler initialization failed: {}".format(e))

    # 設定 Telegram webhook URL（若 token 已設定）
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
    if tg_token and tg_webhook_url:
        try:
            import requests
            url = f"https://api.telegram.org/bot{tg_token}/setWebhook"
            resp = requests.post(url, json={"url": tg_webhook_url}, timeout=10)
            logger.info("[startup] Telegram webhook set: {}".format(resp.json()))
        except Exception as e:
            logger.error("[startup] Telegram webhook setup failed: {}".format(e))

    yield

    if hasattr(app.state, 'scheduler_manager'):
        if app.state.scheduler_manager.is_running:
            app.state.scheduler_manager.stop()
            logger.info("[shutdown] Scheduler manager stopped")

    if _engine:
        _engine.stop()


app = FastAPI(lifespan=lifespan)

line_webhook.register(app, _line_store, _line)
tg_webhook.register(app, _tg_store, _tg)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    import asyncio
    import traceback
    from fastapi.responses import JSONResponse

    tb = traceback.format_exc()
    logger.error("[server] Unhandled exception on {}: {}".format(request.url.path, exc), exc_info=True)

    max_len = 3800
    tb_display = tb if len(tb) <= max_len else tb[:max_len] + "\n…（已截斷）"
    msg = "**路徑：** `{}`\n**錯誤：** `{}`\n\n```\n{}\n```".format(request.url.path, exc, tb_display)

    error_webhook = os.environ.get("DISCORD_ERROR_WEBHOOK_URL")
    if error_webhook:
        notifier = DiscordNotifier(webhook_url=error_webhook)
        await asyncio.to_thread(notifier.send, "🚨 Server Error 500", msg, 0xE74C3C)

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: 新增環境變數到 .env**

在 `.env` 中加入：

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_URL=https://smart.aurabizon.com/telegram/webhook
```

- [ ] **Step 3: 重啟 server 確認啟動正常**

```bash
find . -name "*.pyc" -delete
pkill -f "uvicorn bot.server" 2>/dev/null
sleep 2
launchctl unload ~/Library/LaunchAgents/com.smartmonitor.bot.plist 2>/dev/null
sleep 1
launchctl load ~/Library/LaunchAgents/com.smartmonitor.bot.plist
sleep 4
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 4: 確認 Telegram webhook 端點正常**

```bash
curl -s http://localhost:8000/telegram/webhook -X POST \
  -H "Content-Type: application/json" \
  -d '{"update_id": 1}'
```
Expected: `{"ok":true}`

- [ ] **Step 5: 更新 plist 加入新環境變數**

在 `/Users/jerry/Library/LaunchAgents/com.smartmonitor.bot.plist` 的 `EnvironmentVariables` dict 中加入：

```xml
<key>TELEGRAM_BOT_TOKEN</key>
<string>your_actual_token</string>
<key>TELEGRAM_WEBHOOK_URL</key>
<string>https://smart.aurabizon.com/telegram/webhook</string>
```

- [ ] **Step 6: Commit**

```bash
git add bot/server.py
git commit -m "✨ feat: integrate Telegram into server lifespan and register webhook"
```

---

## Task 9: 執行全套測試 + 端對端驗證

- [ ] **Step 1: 執行全套測試**

```bash
python -m pytest tests/ -q --ignore=tests/test_analysis_engine.py
```
Expected: 大部分 PASS，失敗只有已知的舊 fallback 測試

- [ ] **Step 2: 產生邀請碼並用 Telegram 測試**

```bash
source .env && python set_invite.py --plan pro --count 1
```
Expected: 印出一個邀請碼（例如 `SM8K3F`）

在 Telegram 搜尋你的 Bot，傳送 `/start`，輸入邀請碼，確認收到主選單。

- [ ] **Step 3: 測試 Telegram 手動盤前分析**

在 Telegram 按「2️⃣ 盤前分析」，輸入股票代號（例如 `2330`），確認收到分析結果。

- [ ] **Step 4: 確認 LINE 仍正常**

在 LINE 傳訊確認原有功能不受影響。

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "✨ feat: complete Telegram Bot integration"
```
