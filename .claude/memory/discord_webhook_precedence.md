---
name: discord_webhook_precedence
description: DiscordNotifier 的 webhook_url 必須「傳入參數優先、環境變數後備」，否則 error 頻道通知會誤發到一般頻道
metadata:
  type: feedback
---

`DiscordNotifier(webhook_url=...)` 明確傳入的 webhook 必須優先於環境變數 `DISCORD_WEBHOOK_URL`。

正確寫法（[notifier.py](../../notifier.py)）：
```python
self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
```

**錯誤寫法（曾發生的 bug，勿改回）：**
```python
self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or webhook_url  # ❌
```

**Why:** 一般頻道 `DISCORD_WEBHOOK_URL` 平時都有值，若把它放在 `or` 左邊會永遠短路，導致明確指定的 error 頻道（`DISCORD_ERROR_WEBHOOK_URL`，由 server 500 例外處理器透過 `DiscordNotifier(webhook_url=error_webhook)` 傳入）被忽略，錯誤通知全部誤發到一般頻道。

**How to apply:** 任何「預設值 or 覆寫值」的取值順序，明確傳入的參數要放在 `or` 左邊（優先），環境變數/預設值放右邊（後備）。已用 [tests/test_notifier.py](../../tests/test_notifier.py) 鎖住此行為，改動 notifier 取值順序前先看該測試。相關：error 通知走 `DISCORD_ERROR_WEBHOOK_URL`、一般通知走 `DISCORD_WEBHOOK_URL`。
