"""Interactive terminal chat with the agent.

Usage: python scripts/chat_cli.py [--user u001] [--session my-session]
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laptop_agent.agent.runtime import open_runtime  # noqa: E402


async def main(user: str, session: str) -> None:
    print(f"LaptopHub assistant (user={user}, session={session}). Ctrl+C to quit.\n")
    async with open_runtime() as rt:
        while True:
            msg = input("you> ").strip()
            if not msg:
                continue
            r = await rt.chat(user, session, msg)
            while r.pending_confirmation:
                p = r.pending_confirmation
                print(f"\n[CONFIRM ORDER] cart: {json.dumps(p['cart'], indent=1)}\nshipping: {p['shipping_option']}")
                r = await rt.resume(user, session, input("confirm (yes/no)> "))
            tools = ", ".join(t["name"] for t in r.tool_calls) or "-"
            print(f"\nbot> {r.answer}\n   [{r.latency_s}s | tools: {tools} | tokens {r.input_tokens}/{r.output_tokens}"
                  f" | guard: {r.guard}]\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="u001")
    ap.add_argument("--session", default=f"cli-{uuid.uuid4().hex[:6]}")
    a = ap.parse_args()
    try:
        asyncio.run(main(a.user, a.session))
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
