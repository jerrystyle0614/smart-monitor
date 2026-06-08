"""
cache.py — 分析結果快取管理
避免 30 秒內的重複 Claude API 呼叫
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any


class AnalysisCache:
    """分析結果快取（JSON 檔案）"""

    def __init__(self, cache_dir: str = "cache/analysis"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = 3600  # 1 小時過期

    def _get_cache_key(self, stock_id: str, analysis_type: str) -> str:
        """生成快取鍵"""
        return f"{stock_id}_{analysis_type}"

    def _get_cache_path(self, key: str) -> Path:
        """取得快取檔案路徑"""
        return self.cache_dir / f"{key}.json"

    def get(self, stock_id: str, analysis_type: str) -> Optional[Dict[str, Any]]:
        """
        取得快取結果。
        回傳 None 若不存在或已過期
        """
        key = self._get_cache_key(stock_id, analysis_type)
        path = self._get_cache_path(key)

        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 檢查是否過期
            if time.time() - data.get("timestamp", 0) > self.ttl:
                path.unlink()
                return None

            return data.get("result")
        except Exception as e:
            print(f"[cache] 讀取失敗：{e}")
            return None

    def set(self, stock_id: str, analysis_type: str, result: Dict[str, Any]) -> None:
        """儲存快取結果"""
        key = self._get_cache_key(stock_id, analysis_type)
        path = self._get_cache_path(key)

        try:
            data = {
                "timestamp": time.time(),
                "stock_id": stock_id,
                "analysis_type": analysis_type,
                "result": result,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[cache] 儲存失敗：{e}")

    def delete(self, stock_id: str, analysis_type: str) -> None:
        """刪除快取結果"""
        key = self._get_cache_key(stock_id, analysis_type)
        path = self._get_cache_path(key)

        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            print(f"[cache] 刪除失敗：{e}")
