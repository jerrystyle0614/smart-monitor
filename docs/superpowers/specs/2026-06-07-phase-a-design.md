# Smart Monitor Phase A — 服務框架重寫設計文件

**日期：** 2026-06-07
**範疇：** 對話框架重寫，背景監控引擎不動

---

## 一、目標

用純數字選單 + 問答腳本引擎取代現有的自然語言解析流程，解決以下問題：
- Gemini 誤判股票代號
- 使用者不知道要輸入什麼
- 一人只能監控一支股票
- 敏感持股資料明文儲存
- Server 重啟後監控狀態遺失

---

## 二、架構總覽

```
LINE 使用者
    │
    ▼ Webhook (HTTPS)
FastAPI Server (bot/server.py)
    │
    ▼
ServiceRouter (bot/router.py)  ← 新建，取代 handlers.py
    │
    ├── PermissionMiddleware   ← 權限檢查
    │
    ├── 顯示服務選單
    │
    └── 分派給對應 Service
            │
            ├── StockMonitorService (bot/services/stock_monitor.py)
            ├── PreMarketService    (bot/services/pre_market.py)
            └── PostMarketService   (bot/services/post_market.py)

背景執行（不變）：
    MonitorEngine → Fugle REST API → LINE push + Discord
    排程 08:30/13:35 → analysis_runner → LINE push + Discord
```

---

## 三、檔案結構變更

### 新建
```
bot/
├── router.py                  # ServiceRouter 主路由
├── services/
│   ├── __init__.py
│   ├── base.py                # ScriptedService 問答腳本基底
│   ├── stock_monitor.py       # 股票監控服務
│   ├── pre_market.py          # 盤前分析服務
│   └── post_market.py         # 盤後分析服務
└── data/
    ├── __init__.py
    └── fugle_client.py        # Fugle API 統一封裝
```

### 修改
```
bot/
├── user_store.py              # 資料結構改為多股票列表 + 加密 + plan 欄位
└── server.py                  # 移除 CLEAR_ON_START 預設行為
```

### 移除
```
bot/
├── handlers.py                # 由 router.py 取代
├── state_machine.py           # 由 services/base.py 取代
└── claude_parser.py           # Gemini 移除；Fugle 驗證移到 data/fugle_client.py
```

### 不動
```
bot/monitor_engine.py
bot/analysis_runner.py
bot/line_client.py
notifier.py
daily_data.py
swing_strategy.py
strategy.py
```

---

## 四、資料結構設計

### 使用者資料目錄
```
users/{line_user_id}/
├── profile.json     # 使用者身份與權限
├── state.json       # 對話狀態（目前在哪個服務、哪個步驟）
└── watchlist.json   # 監控清單（最多 3 支，加密）
```

### profile.json
```json
{
  "uid": "U38e4afa2715ad162749bc3976cf33da1",
  "plan": "free",
  "plan_expires": null,
  "created_at": "2026-06-07T00:00:00"
}
```

**plan 值：**
- `"free"` — 只能使用股票監控（1 支）
- `"basic"` — 監控（3 支）+ 盤前/盤後分析
- `"pro"` — 全部服務（未來含選股推薦）

### state.json
```json
{
  "service": null,
  "step": null,
  "draft": {},
  "edit_index": null,
  "msg_timestamps": [],
  "cooldown_blocked_until": 0
}
```

**欄位說明：**
- `service` — 目前進行中的服務名稱（`"stock_monitor"` / `"pre_market"` / `"post_market"` / `null`）
- `step` — 目前問答步驟索引（0, 1, 2...）
- `draft` — 問答過程中暫存的欄位值
- `edit_index` — 修改模式時，正在修改第幾支股票（0-based）

### watchlist.json
```json
{
  "stocks": [
    {
      "stock_id": "2330",
      "stock_name": "台積電",
      "total_shares": "ENCRYPTED",
      "cost_price": "ENCRYPTED",
      "stop_loss_moving": "ENCRYPTED",
      "target_stage_1": "ENCRYPTED",
      "alerts_fired": {
        "stop": false,
        "target1": false
      }
    }
  ]
}
```

**加密欄位：** `total_shares`、`cost_price`、`stop_loss_moving`、`target_stage_1`

使用 AES-256-GCM 加密，金鑰從環境變數 `ENCRYPT_KEY` 讀取（32 bytes hex）。
`stock_id`、`stock_name`、`alerts_fired` 不加密（不敏感）。

---

## 五、ServiceRouter 設計

### 路由邏輯
```python
def handle_message(uid, text, store, line):
    # 1. 冷卻檢查
    if store.check_cooldown(uid):
        line.reply("傳送太快，請稍後再試")
        return

    # 2. 問答進行中 → 交給對應服務處理
    service = store.get_current_service(uid)
    if service:
        result = service.handle_input(uid, text, store, line)
        if result == "CANCEL":
            store.clear_service_state(uid)
            show_menu(uid, line)
        return

    # 3. 顯示選單或解析選項
    show_menu_or_route(uid, text, store, line)
```

### 服務選單
```
━━━━━━━━━━━━━━━━━━━━━
📊 Smart Monitor

請選擇服務：
1️⃣ 股票監控
2️⃣ 盤前分析
3️⃣ 盤後分析

輸入數字選擇，或輸入「狀態」查看目前監控
━━━━━━━━━━━━━━━━━━━━━
```

### 選單路由規則
| 輸入 | 行為 |
|------|------|
| `1` | 進入股票監控服務 |
| `2` | 進入盤前分析服務 |
| `3` | 進入盤後分析服務 |
| `狀態` / `status` | 顯示監控清單 |
| `說明` / `help` | 顯示使用說明 |
| 其他 | 顯示服務選單 |

### 權限中介層
```python
SERVICE_PERMISSIONS = {
    "stock_monitor": ["free", "basic", "pro"],
    "pre_market":    ["basic", "pro"],
    "post_market":   ["basic", "pro"],
    "stock_picker":  ["pro"],  # Phase B
}

def check_permission(uid, service_name, store) -> bool:
    plan = store.get_plan(uid)
    allowed = SERVICE_PERMISSIONS.get(service_name, [])
    return plan in allowed
```

權限不足時回覆：
```
⚠️ 此功能需要升級方案才能使用。
請聯絡管理員了解升級方式。
```

---

## 六、問答腳本引擎設計

### ScriptedService 基底類別
```python
class Step:
    field: str           # 儲存到 draft 的欄位名
    question: str        # 問題文字
    validate: Callable   # fn(text) -> (ok, value, error_msg)
    optional: bool       # 是否可輸入「跳過」略過

class ScriptedService:
    name: str
    steps: List[Step]

    def start(self, uid, store, line) -> None:
        """進入服務，顯示第一題"""

    def handle_input(self, uid, text, store, line) -> str:
        """
        處理使用者輸入。
        回傳 "CONTINUE" 繼續、"DONE" 完成、"CANCEL" 取消
        """

    def on_complete(self, uid, draft, store, line) -> None:
        """問答完成後執行（儲存資料、顯示確認卡片等）"""
```

### 輸入處理流程
```
使用者輸入
    │
    ├── 「取消」─────────────────► 清除狀態，回到選單
    │
    ├── 「跳過」（選填欄位）────► 儲存 None，進下一題
    │
    ├── 驗證通過 ───────────────► 儲存到 draft，進下一題
    │                             若是最後一題 → on_complete()
    │
    └── 驗證失敗 ───────────────► 顯示錯誤提示，重問同題
```

---

## 七、股票監控服務設計

### 主選單（進入服務後）
```
📈 股票監控

你的監控清單（1/3）：
1️⃣ 台積電（2330）｜均價 900 元｜停損 850 元

請選擇操作：
➕ 新增
✏️ 修改 [數字]
🗑 刪除 [數字]
📊 狀態

或輸入「取消」回到主選單
```

### 新增股票問答腳本（4 步）

```
Step 1 — 股票
問：「請問要監控哪支股票？（輸入名稱或代號）」
驗：呼叫 Fugle API 確認股票存在
誤：「找不到此股票，請重新輸入名稱或代號」

Step 2 — 張數
問：「持有幾張？」
驗：正整數（1 以上）
誤：「請輸入正整數，例如：5」

Step 3 — 均價
問：「買入均價是多少元？」
驗：正數
誤：「請輸入數字，例如：900」

Step 4 — 停損價（選填）
問：「停損價是多少元？（輸入『跳過』略過）」
驗：正數 或 「跳過」
誤：「請輸入數字，或輸入『跳過』略過」
```

### 完成後確認卡片
```
📋 確認監控條件

股票：台積電（2330）
收盤：920 元（-0.84%）
持股：5 張
均價：900 元
停損：850 元（-5.56%）

輸入「確認」開始監控
輸入「取消」重新設定
```

### 確認後監控清單訊息
```
✅ 已開始監控台積電（2330）

📊 你的監控清單（2/3）

1️⃣ 台積電（2330）
   均價 900 元｜停損 850 元
   現價 920 元（+2.22%）

2️⃣ 聯發科（2454）
   均價 1,200 元｜停損 1,100 元
   現價 1,180 元（-1.67%）

可用指令：新增 / 修改 1 / 刪除 1
```

### 監控上限提示
```
⚠️ 你已達到監控上限（3/3）
如需新增，請先刪除一支：刪除 1
```

---

## 八、盤前/盤後分析服務設計

### 盤前分析問答腳本（2 步）
```
Step 1 — 股票
問：「請問要分析哪支股票？（輸入名稱或代號）」
驗：Fugle API 確認存在

Step 2 — 確認
完成後立即執行分析並推播
```

### 盤後分析問答腳本
同盤前，步驟相同，呼叫 `AnalysisMode.POSTMARKET`。

---

## 九、加密設計

### 使用套件
```
cryptography>=41.0  # AES-256-GCM
```

### 環境變數
```
ENCRYPT_KEY=<32 bytes hex，共 64 字元>
```

產生方式：
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 加解密介面
```python
# bot/crypto.py
def encrypt(value: str) -> str:
    """加密字串，回傳 base64 編碼的密文"""

def decrypt(value: str) -> str:
    """解密 base64 密文，回傳原始字串"""

def encrypt_fields(data: dict, fields: list) -> dict:
    """批次加密指定欄位，回傳新 dict"""

def decrypt_fields(data: dict, fields: list) -> dict:
    """批次解密指定欄位，回傳新 dict"""
```

### 加密欄位清單
```python
SENSITIVE_FIELDS = ["total_shares", "cost_price", "stop_loss_moving", "target_stage_1"]
```

---

## 十、狀態恢復設計

### 移除 CLEAR_ON_START 預設行為

`start_bot.sh` 移除 `export CLEAR_ON_START=1`。

`server.py` 的 `_clear_user_data()` 改為：只在 `CLEAR_ON_START=1` 時執行（已有此保護），不再預設清空。

### MonitorEngine 啟動恢復

`MonitorEngine` 啟動時掃描 `users/` 目錄，找出所有有 `watchlist.json` 且含監控股票的使用者，自動加入監控迴圈。

`UserStore.get_all_monitoring_users()` 已支援此功能，不需修改。

---

## 十一、fugle_client.py 統一封裝

整合目前分散在 `handlers.py`、`claude_parser.py`、`monitor_engine.py` 的 Fugle 呼叫：

```python
class FugleClient:
    def get_quote(self, stock_id: str) -> Optional[dict]:
        """取得即時報價（含 closePrice、changePercent、name）"""

    def verify_stock(self, stock_id_or_name: str) -> Optional[dict]:
        """
        輸入代號或名稱，驗證股票是否存在。
        優先用代號查，查不到再用名稱搜尋。
        回傳 {"stock_id": "2330", "stock_name": "台積電"} 或 None
        """

    def fetch_candles(self, stock_id: str, days: int = 60) -> pd.DataFrame:
        """取得日K資料"""

    def load_stock_map(self) -> dict:
        """載入全市場股票清單（名稱→代號）"""
```

---

## 十二、不在此次範疇內

- Claude AI 深度分析（Phase C）
- FinMind 籌碼資料（Phase B）
- 選股推薦服務（Phase B）
- 後台管理介面
- 資料庫遷移
