"""
migrate_users.py — 將 users/{uid}/ 遷移至 users/line/{uid}/
執行前請先備份 users/ 目錄
"""
import shutil
from pathlib import Path

SRC = Path("users")
DST = Path("users/line")


def migrate():
    if not SRC.exists():
        print("users/ 不存在，略過")
        return

    DST.mkdir(parents=True, exist_ok=True)

    moved = 0
    skipped = 0
    for user_dir in SRC.iterdir():
        if not user_dir.is_dir():
            continue
        name = user_dir.name
        # 跳過已遷移的 line/ telegram/ 子目錄
        if name in ("line", "telegram"):
            continue

        dst_user = DST / name
        if dst_user.exists():
            print("  [skip] {} 已存在於 users/line/".format(name))
            skipped += 1
            continue

        shutil.copytree(str(user_dir), str(dst_user))
        print("  [copy] {} → users/line/{}".format(name, name))
        moved += 1

    print("\n完成：搬移 {} 個，略過 {} 個".format(moved, skipped))
    print("確認正確後，手動刪除 users/ 下的舊目錄：")
    for user_dir in SRC.iterdir():
        if user_dir.is_dir() and user_dir.name not in ("line", "telegram"):
            print("  rm -rf {}".format(user_dir))


if __name__ == "__main__":
    migrate()
