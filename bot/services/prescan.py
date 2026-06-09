"""
prescan.py — 每日盤後預掃股票池
每日 13:40 自動執行，掃描上市上櫃前 300 大股票，
初步過濾後存為候選清單供選股推薦使用。
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple, Optional

PRESCAN_DIR = Path("cache/prescan")
PRESCAN_TOP_N = 300

# 原 36 支清單，作為 prescan 失敗時的 fallback
_FALLBACK_UNIVERSE = [
    # 大型權值股
    ("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"),
    ("2308", "台達電"), ("2382", "廣達"), ("3711", "日月光投控"),
    ("2303", "聯電"), ("2412", "中華電"), ("2881", "富邦金"),
    ("2882", "國泰金"), ("2886", "兆豐金"), ("2891", "中信金"),
    # ETF
    ("0050", "元大台灣50"), ("0056", "元大高股息"),
    ("00878", "國泰永續高息"), ("00940", "元大台灣價值高息"),
    ("00919", "群益台灣精選高息"), ("006208", "富邦台50"),
    # 中型科技股
    ("2379", "瑞昱"), ("3034", "聯詠"), ("6505", "台塑化"),
    ("2395", "研華"), ("3008", "大立光"), ("2357", "華碩"),
    ("2376", "技嘉"), ("5880", "合庫金"), ("2892", "第一金"),
    # 低價股
    ("2002", "中鋼"), ("1301", "台塑"), ("1303", "南亞"),
    ("1326", "台化"), ("2207", "和泰車"), ("9910", "豐泰"),
]


def _fetch_candles_yf(stock_id: str, days: int = 60):
    """用 yfinance 抓台股日 K，格式與 fetch_candles 相容。"""
    import yfinance as yf
    import pandas as pd

    ticker = yf.Ticker(f"{stock_id}.TW")
    period = f"{max(days // 20, 3)}mo"
    df = ticker.history(period=period)
    if df is None or df.empty:
        return None

    df = df.dropna(subset=["Close"])  # 排除尚未收盤的當日 NaN
    if df.empty:
        return None

    df = df.reset_index()
    df["date"] = df["Date"].astype(str).str[:10]
    df["open"] = df["Open"]
    df["high"] = df["High"]
    df["low"] = df["Low"]
    df["close"] = df["Close"]
    df["volume"] = (df["Volume"] / 1000).round().astype(int)  # 股 → 張
    return df[["date", "open", "high", "low", "close", "volume"]].tail(days)


def run_prescan() -> int:
    """
    執行盤後預掃，回傳寫入候選股數量。
    失敗只印 warning，不 raise。
    日 K 資料來源：yfinance（不消耗 Fugle API 配額）
    """
    from bot.stock_picker.finmind_client import FinMindClient
    import pandas as pd

    try:
        PRESCAN_DIR.mkdir(parents=True, exist_ok=True)
        finmind = FinMindClient()

        # 取得全市場清單
        all_stocks = finmind.get_all_stocks_basic()
        if not all_stocks:
            print("[prescan] 無法取得全市場清單，放棄")
            return 0

        # 排除 ETF（代號 > 4 碼 or 代號以 0 開頭）、KY 股、代號含英文字母
        def _is_valid(s):
            sid = s.get("stock_id", "")
            name = s.get("stock_name", "")
            if not sid.isdigit():
                return False
            if len(sid) != 4:
                return False
            if sid.startswith("0"):
                return False
            if "KY" in name:
                return False
            return True

        valid_stocks = [s for s in all_stocks if _is_valid(s)]

        # 去重（FinMind 清單可能有重複條目）
        seen = set()
        unique_stocks = []
        for s in valid_stocks:
            sid = s["stock_id"]
            if sid not in seen:
                seen.add(sid)
                unique_stocks.append(s)
        valid_stocks = unique_stocks

        print(f"[prescan] 開始掃描 {len(valid_stocks)} 支股票...")

        scored = []
        for s in valid_stocks:
            stock_id = s["stock_id"]
            stock_name = s["stock_name"]
            try:
                df = _fetch_candles_yf(stock_id, days=60)
                if df is None or len(df) < 20:
                    continue

                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

                close = float(df["close"].iloc[-1])
                avg_vol_20 = float(df["volume"].tail(20).mean())

                # 初步過濾：排除警示/全額交割 + 低流動性
                if close <= 5:
                    continue
                if avg_vol_20 < 500:
                    continue

                # 投信沒有明顯賣超
                institutional = finmind.get_three_major_buyers(stock_id, days=5)
                trust_net = 0.0
                if institutional:
                    trust_net = institutional.get("trust_net", 0.0)
                if trust_net < 0:
                    continue

                scored.append({"stock_id": stock_id, "stock_name": stock_name, "_vol": avg_vol_20})

            except Exception as e:
                print(f"[prescan] {stock_id} 略過：{e}")
                continue

        # 依近 20 日均量降序排列，取前 N 支
        scored.sort(key=lambda x: x["_vol"], reverse=True)
        passed = [{"stock_id": s["stock_id"], "stock_name": s["stock_name"]} for s in scored[:PRESCAN_TOP_N]]

        # 寫入快取
        today_str = date.today().isoformat()
        out_path = PRESCAN_DIR / f"{today_str}.json"
        out_data = {
            "date": today_str,
            "count": len(passed),
            "stocks": passed,
        }
        out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[prescan] 完成，候選股 {len(passed)} 支，存至 {out_path}")
        return len(passed)

    except Exception as e:
        print(f"[prescan] 預掃失敗：{e}")
        return 0


def load_prescan_candidates() -> List[Tuple[str, str]]:
    """
    讀取近期 prescan 結果。
    Fallback 順序：當日 → 前1日 → 前2日 → _FALLBACK_UNIVERSE
    回傳 [(stock_id, stock_name), ...]
    """
    for days_ago in range(3):
        target_date = (date.today() - timedelta(days=days_ago)).isoformat()
        path = PRESCAN_DIR / f"{target_date}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                stocks = data.get("stocks", [])
                if stocks:
                    result = [(s["stock_id"], s["stock_name"]) for s in stocks]
                    if days_ago > 0:
                        print(f"[prescan] 使用 {days_ago} 日前的快取（{target_date}）")
                    return result
            except Exception as e:
                print(f"[prescan] 讀取 {path} 失敗：{e}")
                continue

    print("[prescan] 無可用 prescan 快取，使用 fallback 清單（36 支）")
    return list(_FALLBACK_UNIVERSE)
