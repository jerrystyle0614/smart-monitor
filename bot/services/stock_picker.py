"""
stock_picker.py — 選股推薦服務
三步問答：資金 → 持有期間 → 風險偏好 → AI 策略選擇 → 技術面篩選 → 推薦 5 檔
"""

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

from bot.services.base import ScriptedService, Step


MAX_DAILY_QUERIES = 10
CACHE_DIR = Path("cache/stock_picker")


# ---------- 快取 ----------

def _cache_key(risk: str, period: str, capital_tier: str) -> str:
    raw = f"{date.today().isoformat()}_{risk}_{period}_{capital_tier}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _capital_tier(capital: float) -> str:
    if capital < 10000:
        return "under1w"
    elif capital < 50000:
        return "1w_5w"
    elif capital < 200000:
        return "5w_20w"
    else:
        return "over20w"


def _load_cache(key: str) -> Optional[List]:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(key: str, data: List) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[stock_picker] 快取儲存失敗：{e}")


# ---------- 每日查詢次數 ----------

def _query_count_path(uid: str) -> Path:
    return Path("users") / uid / "picker_queries.json"


def _get_query_count(uid: str) -> int:
    path = _query_count_path(uid)
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != date.today().isoformat():
            return 0
        return data.get("count", 0)
    except Exception:
        return 0


def _increment_query_count(uid: str) -> int:
    path = _query_count_path(uid)
    count = _get_query_count(uid) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date.today().isoformat(), "count": count}, f)
    return count


# ---------- 技術面篩選 ----------

# 預設掃描的股票池（涵蓋各類型，避免掃全市場太慢）
_SCAN_UNIVERSE = [
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
    # 低價股（方便小資族）
    ("2002", "中鋼"), ("1301", "台塑"), ("1303", "南亞"),
    ("1326", "台化"), ("2207", "和泰車"), ("9910", "豐泰"),
]


def _scan_stocks(strategy_type: str, capital: float) -> List[Dict]:
    """
    技術面篩選：MA20 方向 + 收盤位置 + 成交量 + 回撤
    依策略調整篩選條件嚴格度
    """
    from daily_data import fetch_candles
    import pandas as pd

    # 依策略設定篩選參數
    params = {
        "aggressive_short":  {"ma_above": True,  "pullback_max": 12, "vol_ratio_min": 1.1},
        "momentum_mid":      {"ma_above": True,  "pullback_max": 8,  "vol_ratio_min": 1.0},
        "defensive_band":    {"ma_above": True,  "pullback_max": 5,  "vol_ratio_min": 0.8},
        "high_yield_stable": {"ma_above": False, "pullback_max": 8,  "vol_ratio_min": 0.5},
        "dca_stable":        {"ma_above": False, "pullback_max": 10, "vol_ratio_min": 0.5},
    }.get(strategy_type, {"ma_above": True, "pullback_max": 8, "vol_ratio_min": 1.0})

    results = []

    for stock_id, stock_name in _SCAN_UNIVERSE:
        try:
            df = fetch_candles(stock_id, days=60)
            if df is None or len(df) < 20:
                continue

            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

            close = float(df["close"].iloc[-1])
            ma20 = float(df["close"].tail(20).mean())
            high20 = float(df["close"].tail(20).max())
            avg_vol = float(df["volume"].tail(20).mean())
            today_vol = float(df["volume"].iloc[-1])

            pullback = (high20 - close) / high20 * 100 if high20 > 0 else 0
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0
            pct_from_ma = (close - ma20) / ma20 * 100 if ma20 > 0 else 0

            # 篩選條件
            if params["ma_above"] and close <= ma20:
                continue
            if pullback > params["pullback_max"]:
                continue
            if vol_ratio < params["vol_ratio_min"]:
                continue

            # 資金可否買整張
            one_lot_cost = close * 1000
            can_buy_lot = capital >= one_lot_cost

            results.append({
                "stock_id": stock_id,
                "stock_name": stock_name,
                "close": close,
                "ma20": round(ma20, 2),
                "pullback": round(pullback, 2),
                "pct_from_ma": round(pct_from_ma, 2),
                "vol_ratio": round(vol_ratio, 2),
                "one_lot_cost": int(one_lot_cost),
                "can_buy_lot": can_buy_lot,
            })

        except Exception as e:
            print(f"[stock_picker] 篩選 {stock_id} 失敗：{e}")
            continue

    # 依回撤從小到大排序（較穩的排前面）
    results.sort(key=lambda x: x["pullback"])
    return results[:20]  # 最多 20 檔給 AI 挑選


# ---------- AI 策略選擇 ----------

def _ai_pick(capital: float, period: str, risk: str,
             candidates: List[Dict]) -> Optional[Dict]:
    """讓 AI 從候選股中選出最適合的 5 檔並說明理由"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not candidates:
        return None

    try:
        import anthropic

        period_map = {"1": "短期（1～4 週）", "2": "中期（1～3 個月）", "3": "長期 / 定期定額"}
        risk_map = {"1": "保守（最多虧 5%）", "2": "穩健（最多虧 10～15%）", "3": "積極（可接受較大波動）"}

        candidate_lines = ""
        for s in candidates:
            lot_note = "可買整張" if s["can_buy_lot"] else f"零股（整張需 {s['one_lot_cost']//10000} 萬）"
            candidate_lines += (
                f"- {s['stock_name']}（{s['stock_id']}）"
                f" 現價 {s['close']} 元 | MA20 {s['ma20']} 元"
                f" | 偏離 {s['pct_from_ma']:+.1f}% | 回撤 {s['pullback']:.1f}%"
                f" | 量比 {s['vol_ratio']:.1f}x | {lot_note}\n"
            )

        prompt = (
            f"你是台股選股顧問。根據投資人條件從候選股中選出最適合的 5 檔。\n\n"
            f"【投資人條件】\n"
            f"可投入資金：{capital:,.0f} 元\n"
            f"持有期間：{period_map.get(period, period)}\n"
            f"風險承受度：{risk_map.get(risk, risk)}\n\n"
            f"【候選股（技術面已初步篩選）】\n"
            f"{candidate_lines}\n"
            f"請選出最適合這位投資人的 5 檔，考量：\n"
            f"1. 資金夠不夠買整張（不夠的標注需零股）\n"
            f"2. 風險等級是否符合（保守者選 ETF 或大型股）\n"
            f"3. 技術面強弱（偏離 MA20 幅度、回撤幅度）\n"
            f"4. 持有期間適合的流動性\n\n"
            f"同時判斷整體策略名稱（例如：穩健波段型、高息防禦型、動能突破型等）\n\n"
            f"回覆 JSON，不要其他文字：\n"
            f'{{"strategy_name": "策略名稱",'
            f'"strategy_desc": "策略說明（1句）",'
            f'"stocks": ['
            f'{{"stock_id": "代號", "stock_name": "名稱", "close": 現價數字,'
            f'"can_buy_lot": true/false, "one_lot_cost": 整張成本數字,'
            f'"reason": "推薦理由（1句）"}},'
            f'...'
            f']}}'
        )

        client = anthropic.Anthropic(api_key=api_key)
        raw = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        ).content[0].text.strip()

        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])

    except Exception as e:
        print(f"[stock_picker] AI 選股失敗：{e}")
        return None


def _strategy_type_from_inputs(period: str, risk: str) -> str:
    """根據持有期 + 風險偏好決定技術面篩選策略"""
    if risk == "1" and period == "3":
        return "high_yield_stable"   # 保守 + 長期
    elif risk == "1":
        return "defensive_band"      # 保守 + 短中期
    elif risk == "2" and period in ("1", "2"):
        return "momentum_mid"        # 穩健 + 短中期
    elif risk == "3":
        return "aggressive_short"    # 積極
    elif period == "3":
        return "dca_stable"          # 任何 + 長期/定額
    else:
        return "momentum_mid"


# ---------- Service ----------

class StockPickerService(ScriptedService):
    """選股推薦服務 — 三步問答 + AI 策略選股"""

    def __init__(self):
        self.name = "stock_picker"
        self.steps = [
            Step(
                field="capital",
                question=(
                    "💰 選股推薦｜步驟 1／3\n\n"
                    "你目前有多少資金可以投入？（元）\n"
                    "例如：50000\n\n"
                    "（輸入『取消』回到主選單）"
                ),
                validate=self._validate_capital,
                optional=False,
            ),
            Step(
                field="period",
                question=(
                    "📅 選股推薦｜步驟 2／3\n\n"
                    "你希望持有多久？\n\n"
                    "1️⃣ 短期（1～4 週）\n"
                    "2️⃣ 中期（1～3 個月）\n"
                    "3️⃣ 長期 / 定期定額\n\n"
                    "輸入數字選擇"
                ),
                validate=self._validate_period,
                optional=False,
            ),
            Step(
                field="risk",
                question=(
                    "⚖️ 選股推薦｜步驟 3／3\n\n"
                    "你對虧損的接受度？\n\n"
                    "1️⃣ 保守（最多虧 5%）\n"
                    "2️⃣ 穩健（最多虧 10～15%）\n"
                    "3️⃣ 積極（可接受較大波動）\n\n"
                    "輸入數字選擇"
                ),
                validate=self._validate_risk,
                optional=False,
            ),
        ]

    def _validate_capital(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        try:
            val = float(text.replace(",", "").replace("，", ""))
            if val <= 0:
                raise ValueError
            return True, val, ""
        except ValueError:
            return False, None, "請輸入有效金額，例如：50000"

    def _validate_period(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        if text in ("1", "2", "3"):
            return True, text, ""
        return False, None, "請輸入 1、2 或 3"

    def _validate_risk(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        if text in ("1", "2", "3"):
            return True, text, ""
        return False, None, "請輸入 1、2 或 3"

    def on_complete(self, uid, draft, store, line, reply_token=""):
        # type: (str, dict, Any, Any, str) -> None
        """三題收齊後執行選股"""
        capital = float(draft.get("capital", 0))
        period = str(draft.get("period", "2"))
        risk = str(draft.get("risk", "2"))

        store.clear_service_state(uid)

        # 每日查詢上限
        count = _get_query_count(uid)
        if count >= MAX_DAILY_QUERIES:
            line.reply(reply_token,
                f"⚠️ 今日查詢次數已達上限（{MAX_DAILY_QUERIES}/{MAX_DAILY_QUERIES}），"
                f"明日再試。"
            )
            return

        line.reply(reply_token, "⏳ 正在為你篩選股票，請稍候...")

        # 檢查快取
        tier = _capital_tier(capital)
        cache_key = _cache_key(risk, period, tier)
        cached = _load_cache(cache_key)

        if cached:
            count = _increment_query_count(uid)
            _send_result(uid, cached, capital, count, line)
            return

        # 技術面篩選
        strategy_type = _strategy_type_from_inputs(period, risk)
        candidates = _scan_stocks(strategy_type, capital)

        if not candidates:
            line.push(uid, "❌ 目前找不到符合條件的股票，請稍後再試或調整條件。")
            return

        # AI 選出 5 檔
        ai_result = _ai_pick(capital, period, risk, candidates)

        if not ai_result:
            line.push(uid, "❌ AI 選股失敗，請稍後再試。")
            return

        _save_cache(cache_key, ai_result)
        count = _increment_query_count(uid)
        _send_result(uid, ai_result, capital, count, line)


def _send_result(uid: str, ai_result: Dict, capital: float,
                 query_count: int, line) -> None:
    """格式化並推播選股結果"""
    strategy_name = ai_result.get("strategy_name", "個人化選股")
    strategy_desc = ai_result.get("strategy_desc", "")
    stocks = ai_result.get("stocks", [])

    period_map = {"1": "短期", "2": "中期", "3": "長期/定額"}

    msg = f"📊 選股推薦｜{strategy_name}\n"
    msg += f"策略：{strategy_desc}\n"
    msg += f"可投入資金：{capital:,.0f} 元\n\n"

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, stock in enumerate(stocks[:5]):
        stock_id = stock.get("stock_id", "")
        stock_name = stock.get("stock_name", "")
        close = stock.get("close", 0)
        can_buy_lot = stock.get("can_buy_lot", False)
        one_lot_cost = stock.get("one_lot_cost", 0)
        reason = stock.get("reason", "")

        emoji = number_emojis[i] if i < len(number_emojis) else f"{i+1}."

        msg += f"{emoji} {stock_name}（{stock_id}）  {close} 元\n"
        if can_buy_lot:
            msg += f"   ✅ 可買整張（約 {one_lot_cost:,} 元）\n"
        else:
            lot_w = one_lot_cost // 10000
            msg += f"   ⚠️ 零股｜整張需約 {lot_w} 萬元\n"
        msg += f"   {reason}\n\n"

    msg += "─────────────────\n"
    msg += "⚠️ 以上僅供參考，請自行評估是否適合買入\n"
    msg += f"今日剩餘查詢次數：{MAX_DAILY_QUERIES - query_count}/{MAX_DAILY_QUERIES}\n"
    msg += "（重新輸入 4 可調整條件重新選股）"

    line.push(uid, msg)
