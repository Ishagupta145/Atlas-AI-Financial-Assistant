import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path so `app` is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import memory as db
from app.ai import agent

async def main():
    await db.initialize_database()
    uid = 999999
    history = []

    msgs = [
        "I'm an investment analyst.",
        "I mainly follow Nvidia, AMD and TSMC.",
        "I'm particularly interested in AI infrastructure.",
    ]

    for m in msgs:
        extracted = await agent.extract_user_memory(m, history)
        print("MSG:", m, "EXTRACTED:", extracted)
        for k, v in extracted.items():
            await db.save_user_memory(uid, k, v)
        history.append(("user", m))

    mem = await db.get_user_memory(uid)
    print("STORED MEMORY:", mem)

    # Ask Atlas using stored memory
    try:
        response = await agent.ask_atlas("What companies am I following?", history, mem)
        print("Atlas response:\n", response)
    except RuntimeError as e:
        if str(e) == 'RATE_LIMIT':
            print("Atlas rate-limited; skipping response in test.")
        else:
            raise

    # Test a non-memory message
    extracted = await agent.extract_user_memory("What is EBITDA?", history)
    print("EBITDA extracted:", extracted)

if __name__ == '__main__':
    asyncio.run(main())
