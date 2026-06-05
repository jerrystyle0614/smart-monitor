"""
market_data.py — 行情來源模組
提供兩種模式：MockMarketData（模擬）與 RealMarketData（富果 Fugle 即時）
兩者的 snapshot() 回傳格式完全相同，strategy.py 與 main.py 對兩者透明
"""

import os
import copy
import json
import random
import threading
import time


def _empty_snap(config: dict) -> dict:
    """建立空白快照結構，供兩種模式共用"""
    return {
        "target": {
            "price": None,
            "total_volume": 0,
            "limit_up": None,
            "limit_up_opened": False,
            "last_large_order": 0,
            "_touched": False,  # 內部用：是否曾觸及漲停
        },
        "peers": {
            code: {"name": name, "price": None, "pct": 0.0}
            for code, name in config["peer_stocks"].items()
        },
        "group": {
            code: {"name": name, "price": None, "pct": 0.0}
            for code, name in config["group_stocks"].items()
        },
        "us": {ticker: 0.0 for ticker in config["us_tickers"]},
    }


class MockMarketData:
    """
    模擬模式：不需任何帳號，用隨機漫步模擬盤面
    讓策略邏輯與 Discord 推播整條流程可先跑通
    """

    def __init__(self, config: dict):
        self._config = config
        self._lock = threading.Lock()
        self._snap = _empty_snap(config)

        cost = config["cost_price"]
        # 模擬初始價格從成本價開始
        self._current_price = cost
        self._limit_up_price = round(cost * 1.1, 2)

        # 同業與集團的漂移累積量
        self._peer_drifts = {code: 0.0 for code in config["peer_stocks"]}
        self._group_drifts = {code: 0.0 for code in config["group_stocks"]}

        # 美股漲跌幅在啟動時決定，執行期間固定
        for ticker in config["us_tickers"]:
            self._snap["us"][ticker] = round(random.uniform(-6, 3), 2)

    def start(self) -> None:
        """啟動模擬，印提示訊息"""
        print("[模擬模式] 使用隨機漫步模擬盤面，所有數值均為虛構。")

        # 初始化漲停價
        with self._lock:
            self._snap["target"]["limit_up"] = self._limit_up_price
            self._snap["target"]["price"] = self._current_price

    def stop(self) -> None:
        """模擬模式無需清理"""
        pass

    def snapshot(self) -> dict:
        """更新一次模擬數據後回傳深拷貝快照"""
        self._tick()
        with self._lock:
            return copy.deepcopy(self._snap)

    def _tick(self) -> None:
        """每次呼叫 snapshot 時推進一步隨機漫步"""
        with self._lock:
            # 3312 價格隨機漂移 ±0.6
            drift = random.uniform(-0.6, 0.6)
            self._current_price = round(self._current_price + drift, 2)
            price = self._current_price
            limit_up = self._limit_up_price

            # 漲停打開偵測
            if price >= limit_up:
                self._snap["target"]["_touched"] = True
            if self._snap["target"]["_touched"] and price < limit_up:
                self._snap["target"]["limit_up_opened"] = True

            # 累計成交量緩慢增加
            self._snap["target"]["total_volume"] += random.randint(50, 300)

            # 約 20% 機率產生大單（55 或 120 張）
            if random.random() < 0.2:
                self._snap["target"]["last_large_order"] = random.choice([55, 120])
            else:
                self._snap["target"]["last_large_order"] = 0

            self._snap["target"]["price"] = price

            # 同業漲跌幅隨機累積漂移，讓它有機會超過門檻觸發警示
            for code in self._config["peer_stocks"]:
                self._peer_drifts[code] += random.uniform(-0.3, 0.2)
                pct = round(self._peer_drifts[code], 2)
                self._snap["peers"][code]["pct"] = pct
                self._snap["peers"][code]["price"] = round(
                    self._config["cost_price"] * (1 + pct / 100), 2
                )

            # 集團股同理
            for code in self._config["group_stocks"]:
                self._group_drifts[code] += random.uniform(-0.3, 0.2)
                pct = round(self._group_drifts[code], 2)
                self._snap["group"][code]["pct"] = pct
                self._snap["group"][code]["price"] = round(
                    self._config["cost_price"] * (1 + pct / 100), 2
                )


class RealMarketData:
    """
    富果 Fugle 即時模式：透過 WebSocket 接收 aggregates channel 推播
    免費方案上限 5 訂閱數，4 檔各訂 1 個剛好在限制內
    """

    def __init__(self, config: dict):
        self._config = config
        self._lock = threading.Lock()
        self._snap = _empty_snap(config)
        self._client = None
        self._stock = None
        self._stopping = False  # 主動停止時不觸發重連

    def start(self) -> None:
        """
        建立 WebSocket 連線並訂閱 aggregates channel
        缺少 FUGLE_API_KEY 時 raise RuntimeError
        """
        from fugle_marketdata import WebSocketClient  # 只在真實模式下 import

        api_key = os.environ.get("FUGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未設定 FUGLE_API_KEY 環境變數。"
                "請先申請富果 API 金鑰，或改用 --mock 模式。"
            )

        self._client = WebSocketClient(api_key=api_key)
        self._stock = self._client.stock

        # 註冊回呼
        self._stock.on("message", self._handle_message)
        self._stock.on("disconnect", self._handle_disconnect)
        self._stock.on("error", self._handle_error)

        # 建立連線
        self._stock.connect()

        # 訂閱 4 檔股票的 aggregates channel（剛好符合免費方案 5 訂閱上限）
        all_codes = (
            [self._config["stock_id"]]
            + list(self._config["peer_stocks"].keys())
            + list(self._config["group_stocks"].keys())
        )
        for code in all_codes:
            self._stock.subscribe({"channel": "aggregates", "symbol": code})

        # 啟動時抓一次美股前夜收盤數據
        self._fetch_us_overnight()

    def stop(self) -> None:
        """中斷 WebSocket 連線"""
        self._stopping = True
        try:
            if self._stock:
                self._stock.disconnect()
        except Exception as e:
            print(f"[警告] 中斷連線時發生錯誤：{e}")

    def snapshot(self) -> dict:
        """加鎖後回傳快照深拷貝"""
        with self._lock:
            return copy.deepcopy(self._snap)

    def _handle_message(self, message) -> None:
        """
        處理 WebSocket 推播訊息
        只處理 event == "data" 且 channel == "aggregates" 的訊息
        用 threading.Lock 保護共享狀態（回呼跑在 WebSocket 的 IO 執行緒）
        """
        try:
            if isinstance(message, str):
                msg = json.loads(message)
            else:
                msg = message

            if msg.get("event") != "data" or msg.get("channel") != "aggregates":
                return

            data = msg["data"]
            symbol = data["symbol"]
            cfg = self._config

            with self._lock:
                if symbol == cfg["stock_id"]:
                    # 更新主監控股 3312
                    price = data["lastPrice"]
                    vol = data["total"]["tradeVolume"]
                    single = data["lastSize"]

                    # 第一次收到 referencePrice 時計算並快取漲停價
                    if self._snap["target"]["limit_up"] is None:
                        ref = data["referencePrice"]
                        self._snap["target"]["limit_up"] = round(ref * 1.1, 2)

                    limit_up = self._snap["target"]["limit_up"]

                    # 漲停打開偵測
                    if price >= limit_up:
                        self._snap["target"]["_touched"] = True
                    if self._snap["target"].get("_touched") and price < limit_up:
                        self._snap["target"]["limit_up_opened"] = True

                    self._snap["target"]["price"] = price
                    self._snap["target"]["total_volume"] = int(vol)
                    self._snap["target"]["last_large_order"] = int(single)

                elif symbol in cfg["peer_stocks"]:
                    # 更新同業股
                    self._snap["peers"][symbol] = {
                        "name": cfg["peer_stocks"][symbol],
                        "price": data["lastPrice"],
                        "pct": data["changePercent"],
                    }

                elif symbol in cfg["group_stocks"]:
                    # 更新集團股
                    self._snap["group"][symbol] = {
                        "name": cfg["group_stocks"][symbol],
                        "price": data["lastPrice"],
                        "pct": data["changePercent"],
                    }

        except Exception as e:
            print(f"[警告] 處理訊息時發生錯誤：{e}")

    def _handle_disconnect(self, *args) -> None:
        """斷線時印警告並嘗試重連；主動停止時跳過重連"""
        if self._stopping:
            return
        print("[警告] WebSocket 斷線，5 秒後嘗試重連...")
        time.sleep(5)
        try:
            self._stock.connect()
            # 重新訂閱
            all_codes = (
                [self._config["stock_id"]]
                + list(self._config["peer_stocks"].keys())
                + list(self._config["group_stocks"].keys())
            )
            for code in all_codes:
                self._stock.subscribe({"channel": "aggregates", "symbol": code})
            print("[資訊] 重連成功，已重新訂閱所有標的。")
        except Exception as e:
            print(f"[警告] 重連失敗：{e}")

    def _handle_error(self, error) -> None:
        """WebSocket 錯誤只印，不崩潰"""
        print(f"[警告] WebSocket 錯誤：{error}")

    def _fetch_us_overnight(self) -> None:
        """抓美股前夜收盤數據，啟動時執行一次，失敗只印警告"""
        import yfinance as yf  # 延遲 import，mock 模式不需此套件
        for ticker in self._config["us_tickers"]:
            try:
                hist = yf.Ticker(ticker).history(period="5d")
                if len(hist) >= 2:
                    last = hist["Close"].iloc[-1]
                    prev = hist["Close"].iloc[-2]
                    pct = round((last - prev) / prev * 100, 2)
                    with self._lock:
                        self._snap["us"][ticker] = pct
                    print(f"[資訊] {ticker} 前夜收盤：{pct:+.2f}%")
            except Exception as e:
                print(f"[警告] 抓取 {ticker} 數據失敗：{e}")


def build_market_data(config: dict, use_mock: bool):
    """工廠函式：依模式建立對應的行情物件"""
    return MockMarketData(config) if use_mock else RealMarketData(config)
