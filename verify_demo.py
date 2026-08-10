import asyncio
import sys
import io
from unittest.mock import patch, AsyncMock
from dotenv import load_dotenv

async def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    load_dotenv()
    
    # We need to test the logic of send_morning_briefing but redirect its telegram message output
    # to print() instead of actually sending a message, to verify it works safely.
    # Alternatively, we can just patch telegram_app.bot.send_message
    
    from app.main import send_morning_briefing
    from app.database.memory import save_user_memory
    import json
    
    test_user_id = 999999
    
    print("Setting up user memory...")
    await save_user_memory(test_user_id, "role", "Investment Analyst")
    await save_user_memory(test_user_id, "companies_followed", json.dumps(["Nvidia", "AMD", "TSMC"]))
    await save_user_memory(test_user_id, "sectors", json.dumps(["Semiconductors"]))
    await save_user_memory(test_user_id, "interests", json.dumps(["AI Infrastructure"]))
    
    print("Triggering send_morning_briefing for demo user...")
    
    with patch("app.main._send_telegram_message", new_callable=AsyncMock) as mock_send:
        await send_morning_briefing(test_user_id)
        
        if mock_send.called:
            print("\n--- GENERATED BRIEFING (Captured before Telegram send) ---\n")
            print(mock_send.call_args[0][1])
            print("\n-------------------------------------------------------\n")
        else:
            print("\nNo briefing generated (NO_IMPORTANT_NEWS).\n")

if __name__ == "__main__":
    asyncio.run(main())
