"""
main.py — 主程式入口
負責載入設定、建立各元件、啟動監控主迴圈，支援 Ctrl+C 優雅退出
"""

import json
import signal
import sys
import time

from notifier import DiscordNotifier
from market_data import build_market_data
from strategy import StrategyEngine


def load_config(path: str) -> dict:
    """讀取 config.json，失敗時印錯誤並退出"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[錯誤] 找不到設定檔：{path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[錯誤] config.json 格式錯誤：{e}")
        sys.exit(1)


class Monitor:
    """主監控器：整合行情、策略、推播，驅動主迴圈"""

    def __init__(self, use_mock: bool):
        self._config = load_config("config.json")
        self._notifier = DiscordNotifier()
        self._market = build_market_data(self._config, use_mock)
        self._strategy = StrategyEngine(self._config)
        self._use_mock = use_mock
        self.running = True
        # 盡早註冊，避免 WebSocket connect() 阻塞時訊號無法傳遞
        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)

    def run(self) -> None:
        """啟動監控主迴圈，直到 Ctrl+C 或 running 被設為 False"""
        mode = "模擬" if self._use_mock else "真實"
        webhook_status = "已啟用" if self._notifier.enabled else "未設定（警報印於終端）"
        print(f"3312 監控啟動（模式：{mode}）｜ Discord Webhook：{webhook_status}")

        # 啟動行情來源（真實模式會建立 WebSocket 連線）
        try:
            self._market.start()
        except Exception as e:
            print(f"[錯誤] 行情來源啟動失敗：{e}")
            return

        interval = self._config.get("eval_interval_sec", 5)

        while self.running:
            try:
                snap = self._market.snapshot()
                alerts = self._strategy.evaluate(snap)

                # 發送所有觸發的警報
                for alert in alerts:
                    self._notifier.send(alert.title, alert.message, alert.color)

                # 心跳行：顯示即時狀態
                price = snap["target"]["price"]
                vol = snap["target"]["total_volume"]
                stop = self._strategy.current_stop
                price_str = f"{price}" if price is not None else "N/A"
                print(f"[heartbeat] 3312={price_str} 量={vol} 防守={stop}")

            except Exception as e:
                print(f"[警告] 主迴圈發生例外：{e}")

            # 用 0.5 秒小步迴圈睡滿 eval_interval_sec，讓 Ctrl+C 快速響應
            elapsed = 0.0
            while self.running and elapsed < interval:
                time.sleep(0.5)
                elapsed += 0.5

        # 優雅退出
        self._market.stop()
        print("已停止")

    def _handle_sigint(self, signum, frame) -> None:
        """Ctrl+C / SIGTERM 處理：設停止旗標，讓主迴圈自然退出"""
        print("\n收到中止訊號，正在停止...")
        self.running = False


if __name__ == "__main__":
    use_mock = "--mock" in sys.argv
    try:
        Monitor(use_mock).run()
    except KeyboardInterrupt:
        # WebSocket 內部攔截不到 SIGINT 時的最後防線
        print("\n已停止")
        sys.exit(0)
