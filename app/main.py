import os
import json
import socket
# touch to trigger reload during testing

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from app.ai.agent import ask_atlas, ask_atlas_with_evidence, ask_atlas_with_financial_evidence, extract_user_memory, generate_morning_briefing
from app.finance.research import research_company, analyze_market_movement

from app.database.memory import (
    initialize_database,
    save_message,
    get_recent_messages,
    save_user_memory,
    get_user_memory,
    get_all_users,
)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set")


app = FastAPI(
    title="Atlas AI Financial Assistant"
)


telegram_app = (
    Application
    .builder()
    .token(TELEGRAM_BOT_TOKEN)
    .build()
)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Hey! I'm Atlas. 👋\n\n"
        "I'm your AI financial assistant.\n\n"
        "Ask me anything."
    )


def clean_response(text: str) -> str:
    """
    Clean common AI formatting that doesn't display well in Telegram.
    """

    replacements = {
        "### ": "",
        "## ": "",
        "# ": "",
        "**": "",
        "__": "",
        "`": "",
        "$": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace(r"\text{", "")
    text = text.replace(r"\times", " × ")
    text = text.replace(r"\rightarrow", " → ")

    text = text.replace("}", "")

    return text.strip()


def _looks_like_memory_query(text: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return False
    return any(phrase in lower for phrase in [
        "companies do i follow",
        "who am i following",
        "what is my role",
        "what are my interests",
        "what do you remember about me",
        "what is my investment focus",
        "my coverage list"
    ])

def _looks_like_direct_price_query(text: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return False
    # If it's asking why, happening, news, or about movement, it's NOT a direct price query
    if any(token in lower for token in ["why", "happening", "moving", "news", "wrong", "up", "down", "rise", "fall", "move"]):
        return False
    
    contains_price_signal = any(token in lower for token in ["price", "trading at", "how much is", "quote", "trading"])
    contains_company_hint = any(token in lower for token in ["nvidia", "amd", "tesla", "apple", "microsoft", "google", "amazon", "meta", "nvda", "aapl", "msft", "tsla", "googl", "amzn", "meta"])
    return contains_price_signal and contains_company_hint

def _looks_like_market_query(text: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return False
    contains_market_signal = any(token in lower for token in ["price", "trading", "trade", "quote", "market", "latest", "doing", "moving", "move", "up", "down", "happening", "why"])
    contains_company_hint = any(token in lower for token in ["nvidia", "amd", "tesla", "apple", "microsoft", "google", "amazon", "meta", "nvda", "aapl", "msft", "tsla", "googl", "amzn", "meta"])
    return contains_market_signal and contains_company_hint


def _format_market_evidence(market_data: dict) -> str:
    price = market_data.get("price")
    change = market_data.get("change_percent")
    parts = [
        f"Symbol: {market_data.get('symbol')}",
        f"Latest price: {price if price is not None else 'unavailable'}",
        f"Previous close: {market_data.get('previous_close') if market_data.get('previous_close') is not None else 'unavailable'}",
        f"Change percent: {change if change is not None else 'unavailable'}",
        f"Volume: {market_data.get('volume') if market_data.get('volume') is not None else 'unavailable'}",
        f"Timestamp: {market_data.get('timestamp') if market_data.get('timestamp') is not None else 'unavailable'}",
        f"Source: {market_data.get('source') or 'Finnhub'}",
    ]
    return "\n".join(parts)

def _extract_recent_market_data_from_history(history: list) -> str:
    for role, msg in reversed(history):
        if role == "assistant" and "Latest price:" in msg:
            lines = msg.split('\n')
            block = []
            for line in lines:
                if any(x in line for x in ["Symbol:", "Latest price:", "Previous close:", "Change percent:", "Volume:", "Timestamp:", "Source:"]):
                    block.append(line)
            if block:
                return "\n".join(block)
    return ""

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_message = update.message.text

    telegram_user_id = update.effective_user.id

    try:

        # Get recent conversation
        history = await get_recent_messages(
            telegram_user_id,
            limit=12
        )

        # Load stored user memory
        stored_memory = await get_user_memory(telegram_user_id)

        # Extract durable user memory from latest message (LLM + deterministic fallback)
        extracted = await extract_user_memory(
            user_message,
            history
        )

        # Merge extracted into stored memory (lists merged, role overwritten)
        merged = dict(stored_memory) if stored_memory else {}
        list_keys = {
            "companies_followed",
            "sectors",
            "interests",
            "research_preferences",
            "notification_preferences",
        }

        for k, v in extracted.items():
            if k in list_keys:
                existing = merged.get(k) or []
                if isinstance(existing, str):
                    try:
                        existing = json.loads(existing)
                    except Exception:
                        existing = [existing]

                new_items = v if isinstance(v, list) else [v]
                # merge preserving order
                seen = {it.lower() for it in existing}
                combined = list(existing)
                for it in new_items:
                    if it.lower() not in seen:
                        seen.add(it.lower())
                        combined.append(it)
                merged[k] = combined
            else:
                # role or other single-value keys: overwrite
                merged[k] = v

        # Persist merged memory back to DB
        for k, v in merged.items():
            # store lists as JSON strings
            store_value = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            try:
                await save_user_memory(
                    telegram_user_id,
                    k,
                    store_value,
                )
            except Exception as e:
                # log and continue — memory storage failure must not block convo
                print("MEMORY SAVE ERROR:", e)

        # Ask Atlas using conversation context + user memory
        user_memory = merged
        try:
            is_memory_query = _looks_like_memory_query(user_message)
            is_direct_price = not is_memory_query and _looks_like_direct_price_query(user_message)
            is_market_query = not is_memory_query and not is_direct_price and _looks_like_market_query(user_message)
            
            if is_memory_query:
                if not user_memory:
                    response = "I don't have any preferences saved for you yet."
                else:
                    parts = ["Here is what I remember about you:"]
                    if "role" in user_memory:
                        parts.append(f"Role: {user_memory['role']}")
                    if "companies_followed" in user_memory:
                        parts.append("You currently follow:\n• " + "\n• ".join(user_memory["companies_followed"]))
                    if "sectors" in user_memory:
                        parts.append("Your saved sectors:\n• " + "\n• ".join(user_memory["sectors"]))
                    if "interests" in user_memory:
                        parts.append("Your saved interests:\n• " + "\n• ".join(user_memory["interests"]))
                    response = "\n\n".join(parts)
            elif is_direct_price:
                market_research = await research_company(
                    user_message,
                    include_market=True,
                    include_news=False,
                    include_sec=False,
                )
                market_data = market_research.get("data", {}).get("market")
                if market_data:
                    response = _format_market_evidence(market_data)
                else:
                    response = "I couldn't retrieve the latest market data for that request. Please try again in a moment."
            elif is_market_query:
                market_research = await research_company(
                    user_message,
                    include_market=True,
                    include_news=True,
                    include_sec=False,
                )
                market_data = market_research.get("data", {}).get("market")
                news_data = market_research.get("data", {}).get("news", [])
                if market_data:
                    evidence = analyze_market_movement(user_message, market_data, news_data)
                    response = await ask_atlas_with_financial_evidence(
                        user_message,
                        history,
                        user_memory,
                        evidence=evidence,
                    )
                else:
                    response = (
                        "I couldn't retrieve the latest market data for that request. "
                        "Please try again in a moment."
                    )
            else:
                response = await ask_atlas(
                    user_message,
                    history,
                    user_memory,
                )
        except RuntimeError as e:
            if str(e) == 'RATE_LIMIT':
                print("RATE LIMIT from Gemini")
                if 'market_data' in locals() and market_data and not is_direct_price:
                    fallback_text = _format_market_evidence(market_data)
                    response = (
                        "Atlas AI interpretation is temporarily unavailable due to rate limits.\n\n"
                        "However, here is the live market data for your query:\n\n"
                        f"{fallback_text}"
                    )
                elif extracted:
                    ack_parts = []
                    if "role" in extracted:
                        ack_parts.append(f"role ({extracted['role']})")
                    if "companies_followed" in extracted:
                        comps = ", ".join(extracted["companies_followed"])
                        ack_parts.append(f"coverage list ({comps})")
                    if "sectors" in extracted:
                        secs = ", ".join(extracted["sectors"])
                        ack_parts.append(f"sectors ({secs})")
                    if "interests" in extracted:
                        ints = ", ".join(extracted["interests"])
                        ack_parts.append(f"interest ({ints})")
                    
                    saved_str = ", ".join(ack_parts)
                    response = f"Got it — I've saved your {saved_str}. My AI reasoning service is temporarily rate-limited, but your preferences are saved."
                else:
                    recent_market = _extract_recent_market_data_from_history(history)
                    if recent_market:
                        response = (
                            "I have the relevant context — you're evaluating this based on your interests. "
                            "However, my AI reasoning service is temporarily rate-limited, so I don't want to speculate about whether today's move changes your thesis.\n\n"
                            "The live market data currently available is:\n"
                            f"{recent_market}"
                        )
                    else:
                        response = "Atlas is temporarily rate-limited and cannot generate an AI response. Please try again in a moment."
            else:
                raise

        # Clean AI response
        response = clean_response(response)

        # Save user's message
        await save_message(
            telegram_user_id,
            "user",
            user_message
        )

        # Save Atlas response
        await save_message(
            telegram_user_id,
            "assistant",
            response
        )

        # Send response
        await update.message.reply_text(
            response
        )

    except Exception as e:

        print("AI ERROR:", e)

        await update.message.reply_text(
            "I ran into a problem while processing that. "
            "Please try again."
        )

async def _send_telegram_message(user_id: int, text: str):
    await telegram_app.bot.send_message(chat_id=user_id, text=text)

async def send_morning_briefing(user_id: int):
    try:
        user_memory = await get_user_memory(user_id)
        companies_followed = user_memory.get("companies_followed", [])
        if isinstance(companies_followed, str):
            try:
                companies_followed = json.loads(companies_followed)
            except Exception:
                companies_followed = [companies_followed]
            
        if not companies_followed:
            return
            
        research_data = []
        for company in companies_followed:
            res = await research_company(company, include_market=True, include_news=True, include_sec=False)
            research_data.append(res)
            
        briefing = await generate_morning_briefing(user_memory, research_data)
        
        if briefing and briefing != "NO_IMPORTANT_NEWS":
            await _send_telegram_message(user_id, briefing)
    except Exception as e:
        print(f"Error sending morning briefing to {user_id}: {e}")


async def run_briefings_for_all_users():
    users = await get_all_users()
    for user_id in users:
        await send_morning_briefing(user_id)


async def briefing_loop():
    import asyncio
    from datetime import datetime
    
    brief_time = os.getenv("MORNING_BRIEF_TIME", "08:30")
    last_run_date = None
    
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.date()
        
        if current_time == brief_time and current_date != last_run_date:
            last_run_date = current_date
            await run_briefings_for_all_users()
            
        await asyncio.sleep(60)


telegram_app.add_handler(
    CommandHandler("start", start)
)


telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)


@app.get("/")
async def root():

    return {
        "status": "online",
        "service": "Atlas AI Financial Assistant"
    }


@app.on_event("startup")
async def startup():

    await initialize_database()

    # Decide whether to enable polling via environment variable.
    polling_enabled = os.getenv("TELEGRAM_POLLING_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    if not polling_enabled:
        print("Telegram polling disabled (TELEGRAM_POLLING_ENABLED not set to true).")
        return

    # Use a simple cross-process lock (TCP bind) to ensure only one process starts polling.
    lock_port = int(os.getenv("TELEGRAM_POLLING_LOCK_PORT", "52345"))
    lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Bind to localhost on the lock port. If another process already bound it,
        # this will raise OSError and we will skip starting polling here.
        lock_sock.bind(("127.0.0.1", lock_port))
        lock_sock.listen(1)
    except OSError:
        print(
            "Another process holds the Telegram polling lock; skipping polling in this process."
        )
        lock_sock.close()
        return

    # We acquired the lock; store the socket so we can close it on shutdown.
    app.state._telegram_polling_lock = lock_sock

    try:
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        app.state._telegram_polling_active = True
        print("Telegram polling started (this process holds the polling lock).")
        
        import asyncio
        app.state._briefing_task = asyncio.create_task(briefing_loop())
    except Exception as e:
        # If initialization fails, release the lock and re-raise so the failure is visible.
        print("Telegram initialization failed:", e)
        try:
            app.state._telegram_polling_lock.close()
        except Exception:
            pass
        raise


@app.on_event("shutdown")
async def shutdown():

    # Only attempt to stop polling if this process started it.
    if getattr(app.state, "_telegram_polling_active", False):
        try:
            await telegram_app.updater.stop()
        except Exception as e:
            print("Error stopping Telegram updater:", e)

        try:
            await telegram_app.stop()
        except Exception as e:
            print("Error stopping Telegram app:", e)

        try:
            await telegram_app.shutdown()
        except Exception as e:
            print("Error during Telegram shutdown:", e)

    # Close the lock socket if held by this process
    lock = getattr(app.state, "_telegram_polling_lock", None)
    if lock:
        try:
            lock.close()
            print("Telegram polling lock released.")
        except Exception as e:
            print("Error closing polling lock socket:", e)