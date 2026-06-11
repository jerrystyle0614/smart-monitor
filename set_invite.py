"""
set_invite.py — 產生邀請碼 CLI
用法：python set_invite.py --plan pro --count 3
"""
import argparse
from bot.telegram.invite import generate_code, _load, _save


def main():
    parser = argparse.ArgumentParser(description="產生 Smart Monitor 邀請碼")
    parser.add_argument("--plan", choices=["free", "basic", "pro"], default="pro")
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    data = _load()
    codes = []
    for _ in range(args.count):
        code = generate_code()
        data[code] = {"plan": args.plan, "used": False, "chat_id": None}
        codes.append(code)

    _save(data)
    print(", ".join(codes))


if __name__ == "__main__":
    main()
