#!/usr/bin/env python3
"""
快速設置用戶方案的工具
用法: python3 set_user_plan.py <user_id> <plan>
例如: python3 set_user_plan.py U123abc456 pro
"""

import sys
from bot.user_store import UserStore

if len(sys.argv) < 3:
    print("用法: python3 set_user_plan.py <user_id> <plan>")
    print("方案選擇: free, basic, pro")
    sys.exit(1)

user_id = sys.argv[1]
plan = sys.argv[2]

if plan not in ["free", "basic", "pro"]:
    print("❌ 無效的方案。選擇：free, basic, pro")
    sys.exit(1)

store = UserStore()
store.set_plan(user_id, plan)

print(f"✅ 已設置用戶 {user_id} 的方案為: {plan}")
