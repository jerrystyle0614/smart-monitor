"""
scheduler.py — 每日排程任務
08:00 自動掃描、生成說明、推播
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from bot.stock_picker.engine import StockPickerEngine
from bot.stock_picker.fundamental_strategy import FundamentalStrategy
from bot.stock_picker.technical_strategy import TechnicalStrategy


def save_picker_cache(cache_data: Dict) -> None:
    """儲存選股推薦快取"""
    cache_path = Path("data") / "stock_picker_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[scheduler] 快取已儲存：{len(cache_data.get('stocks', []))} 支股票")
    except Exception as e:
        print(f"[scheduler] 快取儲存失敗：{e}")


def load_picker_cache() -> Dict:
    """讀取選股推薦快取"""
    cache_path = Path("data") / "stock_picker_cache.json"
    if not cache_path.exists():
        return {"stocks": []}
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[scheduler] 快取讀取失敗：{e}")
        return {"stocks": []}


def generate_stock_summary(stock_id: str, reasons: Dict) -> str:
    """使用 Claude API 生成股票說明"""
    try:
        import anthropic
        
        client = anthropic.Anthropic()
        
        prompt = f"""你是台股分析師。用白話、簡潔的方式（2-3 句）解釋為什麼這支股票值得注意。

股票代號：{stock_id}
籌碼面理由：{reasons.get('fundamental', '')}
技術面理由：{reasons.get('technical', '')}

對象是不懂技術面的一般投資人，請用日常用語解釋。"""
        
        message = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return message.content[0].text
    except Exception as e:
        print(f"[scheduler] Claude 生成說明失敗：{e}")
        return "暫無說明"


async def daily_stock_picker_task(finmind_client, fugle_client, claude_client=None, line_client=None):
    """
    每日 08:00 執行的排程任務。
    掃描 + 說明生成 + 推播
    """
    print("[scheduler] 開始選股掃描...")
    
    try:
        # 建立策略
        fundamental = FundamentalStrategy(finmind_client, consecutive_days=3, margin_increase_threshold=5.0)
        technical = TechnicalStrategy(fugle_client, ma_period=20, pullback_threshold=8.0)
        
        # 執行掃描
        engine = StockPickerEngine([fundamental, technical])
        picked_stocks = engine.scan()
        
        print(f"[scheduler] 掃描完成，發現 {len(picked_stocks)} 支股票")
        
        # 準備快取資料
        cache_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().timestamp(),
            "stocks": []
        }
        
        # 為每支股票生成說明
        for stock in picked_stocks:
            reasons = {
                "fundamental": "三大法人買超條件符合",
                "technical": "技術面條件符合"
            }
            
            claude_summary = generate_stock_summary(stock.stock_id, reasons)
            
            stock_dict = {
                "stock_id": stock.stock_id,
                "stock_name": stock.stock_name,
                "reasons": reasons,
                "risks": "若跌破 MA20 應設停損",
                "claude_summary": claude_summary
            }
            cache_data["stocks"].append(stock_dict)
        
        # 儲存快取
        save_picker_cache(cache_data)
        
        print("[scheduler] 選股推薦完成")
    
    except Exception as e:
        print(f"[scheduler] 執行失敗：{e}")
