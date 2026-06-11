# Telegram Bot 整合設計

## 目標

在現有 LINE Bot 架構下新增 Telegram Bot 支援，兩個平台並行運作，共用所有後端 service 邏輯（`router.py`、`services/`）不動。解決 LINE 每月 500 則免費推播上限問題。

---

## 架構概覽

```
smart-monitor/
├── bot/
│   ├── server.py              # 現有 LINE webhook（不動）
│   ├── telegram_server.py     # 新增：Telegram Bot webhook handler
│   ├── telegram_client.py     # 新增：push/reply 封裝（介面與 LineClient 一致）
│   ├── router.py              # 不動
│   ├── user_store.py          # 擴充：支援 platform 參數、路徑分離
│   ├── line_client.py         # 不動
│   ├── monitor_engine.py      # 擴充：支援多 store/client
│   └── services/              # 完全不動
│
├── bot/telegram/              # 新增目錄
│   ├── __init__.py
│   ├── keyboard.py            # Inline Keyboard 產生器
│   └── invite.py              # 邀請碼管理
│
├── data/
│   └── invites.json           # 邀請碼儲存
│
├── set_invite.py              # CLI：產生邀請碼
└── .env                       # 新增 TELEGRAM_BOT_TOKEN
```

---

## 一、資料層

### 使用者資料路徑分離

```
users/
├── line/
│   └── {line_uid}/
│       ├── profile.json
│       ├── watchlist.json
│       └── ...
└── telegram/
    └── {chat_id}/
        ├── profile.json
        ├── watchlist.json
        └── ...
```

現有 `users/{uid}/` 資料一次性遷移至 `users/line/{uid}/`。

### UserStore 擴充

```python
class UserStore:
    def __init__(self, platform: str = "line"):
        # platform: "line" | "telegram"
        self._base = Path(f"users/{platform}")
```

- LINE server 初始化：`UserStore(platform="line")`
- Telegram server 初始化：`UserStore(platform="telegram")`
- 兩個 store 完全獨立，互不干擾
- 未來換資料庫只改 `UserStore` 內部實作，介面不變

---

## 二、Telegram Client

### 介面（與 LineClient 一致）

```python
class TelegramClient:
    def push(self, chat_id: str, text: str) -> None:
        """主動推播訊息（無限制，免費）"""

    def reply(self, token: str, text: str) -> None:
        """回覆訊息，token 為 callback_query_id 或 message_id"""

    def send_menu(self, chat_id: str) -> None:
        """發送附 Inline Keyboard 的主選單"""
```

- 使用 `python-telegram-bot` 套件（v20+，async）
- `reply` 內部判斷 token 類型：callback_query → `answerCallbackQuery`；message → `sendMessage`
- 失敗只印警告，不 raise（與 LineClient 一致）

---

## 三、Telegram Server

### Webhook 設定

- 路由掛載在現有 FastAPI app：`POST /telegram/webhook`
- Telegram Bot token 設定：`TELEGRAM_BOT_TOKEN` 環境變數
- Cloudflare Tunnel 已有固定網址，直接複用

### 事件處理

```
收到 Update
    ├── /start 指令 → 進入邀請碼驗證流程
    ├── CallbackQuery（按鈕點擊）→ handle_message(chat_id, data, store, tg_client, query_id)
    └── Message（文字輸入）→ handle_message(chat_id, text, store, tg_client, message_id)
```

`handle_message` 直接呼叫現有 `router.py` 的 `handle_message`，完全透明。

---

## 四、邀請碼系統

### 格式與儲存

- 格式：`SM` + 4 位大寫英數字（例如 `SM8K3F`）
- 儲存：`data/invites.json`

```json
{
  "SM8K3F": {"plan": "pro", "used": false, "chat_id": null},
  "SMABC1": {"plan": "basic", "used": true, "chat_id": "123456789"}
}
```

### 啟用流程

```
/start
    ↓
已啟用 → 直接顯示主選單
未啟用 → 「請輸入邀請碼以啟用服務」
    ↓
輸入邀請碼
    ├── 無效/已使用 → 「邀請碼錯誤，請重新輸入」
    └── 有效 → 綁定 chat_id，設定方案，顯示主選單
```

### CLI 產生邀請碼

```bash
python set_invite.py --plan pro --count 3
# 輸出：SM8K3F, SMABC1, SMX9Y2
```

---

## 五、互動介面

### 主選單（Inline Keyboard）

```
📊 Smart Monitor 服務選單

[1️⃣ 股票監控]  [2️⃣ 盤前分析]
[3️⃣ 盤後分析]  [4️⃣ 選股推薦]
     [5️⃣ ETF 推薦]
```

### 問答流程

- 按下按鈕後進入問答，後續輸入維持文字
- 每題回覆附上 `[❌ 取消]` 按鈕可隨時中斷回主選單
- 驗證失敗時重問同一題（與 LINE 行為一致）

---

## 六、MonitorEngine 擴充

### 多平台推播

```python
class MonitorEngine:
    def __init__(self, stores: dict, clients: dict, discord):
        # stores: {"line": UserStore, "telegram": UserStore}
        # clients: {"line": LineClient, "telegram": TelegramClient}

    def _get_client(self, uid: str, platform: str):
        return self._clients[platform]
```

排程推播（盤前/盤後）和警報推播，逐一掃描兩個 store 的使用者，用對應 client 發送。

---

## 七、環境變數

| 變數 | 用途 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |

---

## 八、不在本次範圍

- 使用者資料庫遷移（後續另立計畫）
- LINE / Telegram 帳號綁定（同一人跨平台）
- Telegram 群組推播
