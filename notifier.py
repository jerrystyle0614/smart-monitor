"""
notifier.py — Discord Webhook 推播模組
透過 embed 格式發送警報；未設定 webhook 時直接印到終端機
"""

import os
import datetime
from typing import Optional
import requests

# 色碼常數：用於 Discord embed 左側色條
COLOR_INFO   = 0x95A5A6  # 灰：純資訊
COLOR_GREEN  = 0x2ECC71  # 綠：獲利出場
COLOR_YELLOW = 0xF1C40F  # 黃：連動警示
COLOR_RED    = 0xE74C3C  # 紅：停損 / 利空


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        # 優先讀環境變數，其次用傳入參數
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or webhook_url
        self.enabled = bool(self.webhook_url)

    def send(self, title: str, message: str, color: int = 0x3498DB) -> None:
        """發送警報：有 webhook 就 POST，沒有就印到終端機"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.enabled:
            self._send_discord(title, message, color, timestamp)
        else:
            self._print_fallback(title, message, timestamp)

    def _send_discord(self, title: str, message: str, color: int, timestamp: str) -> None:
        """POST Discord embed 訊息；非 200/204 只印警告，不 raise"""
        payload = {
            "embeds": [
                {
                    "title": f"📢 {title}",
                    "description": message,
                    "color": color,
                    "footer": {"text": timestamp},
                }
            ]
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                print(f"[警告] Discord 回應異常：{resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[警告] Discord 推播失敗：{e}")

    def _print_fallback(self, title: str, message: str, timestamp: str) -> None:
        """無 webhook 時直接印終端機，讓測試時也能看到完整警報"""
        sep = "=" * 50
        print(f"\n{sep}")
        print(f"📢 {title}")
        print(f"{message}")
        print(f"─ {timestamp}")
        print(f"{sep}\n")
