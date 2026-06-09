"""
etf_picker.py — ETF 推薦服務
兩步問答：資金 → 目標 → 從固定清單篩選 → AI 推薦 3 檔
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from bot.services.base import ScriptedService, Step


MAX_DAILY_QUERIES = 10
CACHE_DIR = Path("cache/etf_picker")

# ETF 清單（按目標分類）
_ETF_UNIVERSE = {
    "index": [
        ("0050", "元大台灣50"),
        ("006208", "富邦台50"),
        ("00631L", "元大台灣50正2"),
    ],
    "dividend": [
        ("0056", "元大高股息"),
        ("00878", "國泰永續高息"),
        ("00919", "群益台灣精選高息"),
        ("00940", "元大台灣價值高息"),
        ("00929", "復華台灣科技優息"),
    ],
    "theme": [
        ("00881", "國泰台灣5G+"),
        ("00830", "國泰費城半導體"),
        ("00646", "元大S&P500"),
        ("00657", "國泰標普低波動"),
        ("00885", "富邦越南"),
    ],
}


# ---------- 查詢次數 ----------

def _query_count_path(uid: str) -> Path:
    return Path(f"users/{uid}/etf_picker_queries.json")


def _get_query_count(uid: str) -> int:
    path = _query_count_path(uid)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("date") != date.today().isoformat():
            return 0
        return data.get("count", 0)
    except Exception:
        return 0


def _increment_query_count(uid: str) -> int:
    path = _query_count_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = _get_query_count(uid) + 1
    path.write_text(
        json.dumps({"date": date.today().isoformat(), "count": count}, ensure_ascii=False),
        encoding="utf-8",
    )
    return count


# ---------- 快取 ----------

def _cache_key(goal: str) -> str:
    return f"{date.today().isoformat()}_{goal}"


def _load_cache(key: str) -> Optional[Dict]:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(key: str, data: Dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[etf_picker] 快取儲存失敗：{e}")


# ---------- 技術面初篩 ----------

def _fetch_etf_data(stock_id: str) -> Optional[Dict]:
    """用 yfinance 抓 ETF 日 K，計算初篩指標。"""
    try:
        import yfinance as yf
        import pandas as pd

        ticker = yf.Ticker(f"{stock_id}.TW")
        df = ticker.history(period="3mo")
        if df is None or df.empty:
            return None

        df = df.dropna(subset=["Close"])
        if len(df) < 20:
            return None

        closes = df["Close"].values
        volumes = df["Volume"].values / 1000  # 股 → 張

        close = float(closes[-1])
        ma20 = float(closes[-20:].mean())
        avg_vol_20 = float(volumes[-20:].mean())

        # 近 30 日報酬
        ret_30 = (close - float(closes[max(0, len(closes) - 30)])) / float(closes[max(0, len(closes) - 30)]) * 100

        # 乖離率
        bias = (close - ma20) / ma20 * 100

        # 近一年配息率（yfinance dividends）
        divs = ticker.dividends
        annual_div = 0.0
        if divs is not None and len(divs) > 0:
            one_year_ago = pd.Timestamp.now(tz=divs.index.tz) - pd.DateOffset(years=1)
            recent_divs = divs[divs.index >= one_year_ago]
            annual_div = float(recent_divs.sum())
        div_yield = annual_div / close * 100 if close > 0 else 0.0

        return {
            "close": close,
            "ma20": round(ma20, 2),
            "avg_vol_20": round(avg_vol_20, 0),
            "ret_30": round(ret_30, 2),
            "bias": round(bias, 2),
            "div_yield": round(div_yield, 2),
        }
    except Exception as e:
        print(f"[etf_picker] {stock_id} 資料抓取失敗：{e}")
        return None


def _scan_etfs(goal: str, capital: float) -> List[Dict]:
    """依目標篩選 ETF，回傳通過初篩的清單（含技術指標）。"""
    universe = _ETF_UNIVERSE.get(goal, [])
    # 三種目標都掃，但排序不同
    if goal == "index":
        targets = _ETF_UNIVERSE["index"]
    elif goal == "dividend":
        targets = _ETF_UNIVERSE["dividend"]
    else:
        targets = _ETF_UNIVERSE["theme"]

    results = []
    for stock_id, stock_name in targets:
        data = _fetch_etf_data(stock_id)
        if data is None:
            continue

        # 基本流動性過濾
        if data["avg_vol_20"] < 100:
            continue

        # 不追高：乖離率不超過 8%
        if data["bias"] > 8:
            continue

        # 不買下跌趨勢：近 30 日報酬不低於 -10%
        if data["ret_30"] < -10:
            continue

        # 高股息目標：至少 3% 殖利率
        if goal == "dividend" and data["div_yield"] < 3:
            continue

        # 資金夠買至少 1 張
        one_lot = data["close"] * 1000
        can_buy_lot = capital >= one_lot

        results.append({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "close": data["close"],
            "ma20": data["ma20"],
            "avg_vol_20": data["avg_vol_20"],
            "ret_30": data["ret_30"],
            "bias": data["bias"],
            "div_yield": data["div_yield"],
            "can_buy_lot": can_buy_lot,
            "one_lot_cost": int(one_lot),
        })

    return results


def _ai_pick(goal: str, capital: float, candidates: List[Dict]) -> Dict:
    """Claude 從候選 ETF 中選出最適合的 3 檔並說明。"""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {}

    goal_labels = {
        "index": "長期持有 / 追蹤大盤",
        "dividend": "高股息收益（季配 / 月配）",
        "theme": "特定主題（AI / 半導體 / 全球）",
    }
    goal_label = goal_labels.get(goal, goal)

    cand_lines = ""
    for c in candidates:
        cand_lines += (
            f"- {c['stock_id']} {c['stock_name']}：收盤 {c['close']} 元，"
            f"MA20={c['ma20']}，乖離率={c['bias']:+.1f}%，"
            f"近30日報酬={c['ret_30']:+.1f}%，"
            f"殖利率={c['div_yield']:.1f}%，均量={c['avg_vol_20']:.0f}張\n"
        )

    prompt = (
        f"你是台股 ETF 投資顧問。投資人目標是「{goal_label}」，可用資金 {capital:,.0f} 元。\n\n"
        f"候選 ETF 清單：\n{cand_lines}\n"
        f"請從以上候選中選出最適合的 3 檔（若不足 3 檔則全選），說明理由。\n\n"
        f"回覆 JSON，格式如下（不要有其他文字）：\n"
        f'{{"picks": ['
        f'{{"stock_id": "代號", "stock_name": "名稱", "reason": "推薦理由（1-2句白話）", "strategy": "建議操作方式（一次進場/定期定額/分批買進）"}}'
        f'], "summary": "整體市場情境與注意事項（2-3句）"}}'
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print(f"[etf_picker] AI 選股失敗：{e}")
        return {}


def _send_result(uid: str, ai_result: Dict, capital: float,
                 candidates: List[Dict], count: int, line) -> None:
    """格式化推播 ETF 推薦結果。"""
    picks = ai_result.get("picks", [])
    summary = ai_result.get("summary", "")

    if not picks:
        line.push(uid, "❌ 目前無符合條件的 ETF，請稍後再試。")
        return

    # 候選清單 lookup
    cand_map = {c["stock_id"]: c for c in candidates}

    msg = f"📊 ETF 推薦結果｜已查詢 {count}/{MAX_DAILY_QUERIES}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    for i, p in enumerate(picks, 1):
        sid = p.get("stock_id", "")
        sname = p.get("stock_name", "")
        reason = p.get("reason", "")
        strategy = p.get("strategy", "")
        c = cand_map.get(sid, {})

        one_lot_cost = c.get("one_lot_cost", 0)
        can_buy_lot = c.get("can_buy_lot", False)
        close = c.get("close", 0)
        div_yield = c.get("div_yield", 0)
        ret_30 = c.get("ret_30", 0)

        lot_hint = f"✅ 可買整張（{one_lot_cost:,} 元）" if can_buy_lot else f"⚠️ 資金不足買整張（需 {one_lot_cost:,} 元），建議零股"

        msg += f"{'①②③'[i-1]} {sname}（{sid}）\n"
        msg += f"   收盤：{close} 元｜殖利率：{div_yield:.1f}%\n"
        msg += f"   近30日：{ret_30:+.1f}%\n"
        msg += f"   {lot_hint}\n"
        msg += f"   📌 操作：{strategy}\n"
        msg += f"   💬 {reason}\n\n"

    if summary:
        msg += f"📝 市場備注\n{summary}\n\n"

    msg += "⚠️ 以上為系統分析參考，非投資建議，請自行評估風險。"

    line.push(uid, msg)


# ---------- 服務主體 ----------

class ETFPickerService(ScriptedService):
    """ETF 推薦服務（2 題問答）"""

    name = "etf_picker"

    def __init__(self):
        self.steps = [
            Step(
                field="capital",
                question=(
                    "💰 ETF 推薦服務\n\n"
                    "請問你有多少資金可以投入？（元）\n"
                    "例如：50000"
                ),
                validate=self._validate_capital,
            ),
            Step(
                field="goal",
                question=(
                    "你的投資目標是？\n\n"
                    "1️⃣ 長期持有 / 追蹤大盤\n"
                    "2️⃣ 高股息收益（季配 / 月配）\n"
                    "3️⃣ 特定主題（AI / 半導體 / 全球）\n\n"
                    "輸入 1、2 或 3"
                ),
                validate=self._validate_goal,
            ),
        ]

    def _validate_capital(self, text: str) -> Tuple[bool, float, str]:
        try:
            val = float(text.replace(",", "").replace("，", ""))
            if val <= 0:
                raise ValueError
            return True, val, ""
        except ValueError:
            return False, 0, "請輸入有效的正數金額，例如：50000"

    def _validate_goal(self, text: str) -> Tuple[bool, str, str]:
        mapping = {"1": "index", "2": "dividend", "3": "theme"}
        if text not in mapping:
            return False, "", "請輸入 1、2 或 3"
        return True, mapping[text], ""

    def on_complete(self, uid: str, draft: Dict, store, line, reply_token: str = "") -> None:
        capital = draft["capital"]
        goal = draft["goal"]

        store.clear_service_state(uid)

        # 查詢次數檢查
        count = _get_query_count(uid)
        if count >= MAX_DAILY_QUERIES:
            line.reply(reply_token,
                f"⚠️ 今日查詢次數已達上限（{MAX_DAILY_QUERIES} 次），明日再試。"
            )
            return

        line.reply(reply_token, "⏳ 正在掃描 ETF，請稍候...")

        # 快取命中
        cache_key = _cache_key(goal)
        cached = _load_cache(cache_key)
        count = _increment_query_count(uid)

        if cached:
            _send_result(uid, cached["ai_result"], capital,
                         cached["candidates"], count, line)
            return

        # 掃描 + AI 選股
        candidates = _scan_etfs(goal, capital)
        if not candidates:
            line.push(uid, "❌ 目前無符合條件的 ETF，請稍後再試。")
            return

        ai_result = _ai_pick(goal, capital, candidates)
        if not ai_result:
            line.push(uid, "❌ AI 分析暫時無法使用，請稍後再試。")
            return

        _save_cache(cache_key, {"ai_result": ai_result, "candidates": candidates})
        _send_result(uid, ai_result, capital, candidates, count, line)
