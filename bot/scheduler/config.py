"""
config.py — 排程任務配置
定義每日排程的時間和任務
"""

from dataclasses import dataclass, field
from typing import List, Callable, Optional


@dataclass
class ScheduledJob:
    """排程任務定義"""
    name: str              # 任務名稱
    hour: int              # 執行小時 (0-23, UTC+8)
    minute: int            # 執行分鐘 (0-59)
    func: Optional[Callable] = None  # 執行函數
    args: tuple = ()       # 函數參數
    kwargs: Optional[dict] = None    # 函數關鍵字參數
    description: str = ""  # 任務說明

    def __post_init__(self):
        """初始化後處理"""
        if self.kwargs is None:
            self.kwargs = {}


# 排程時間配置（以 UTC+8 時區設定）
# 注意：盤前/盤後分析由 MonitorEngine 負責，不在此排程，避免重複推播。
SCHEDULED_JOBS: List[ScheduledJob] = [
    ScheduledJob(
        name="stock_picker_daily",
        hour=8,
        minute=0,
        func=None,  # 稍後在 jobs.py 中實現
        description="每日 08:00 執行選股掃描並推播推薦股票"
    ),
]

# 功能開關
ENABLE_SCHEDULER: bool = True
ENABLE_STOCK_PICKER: bool = True  # 選股每日任務
