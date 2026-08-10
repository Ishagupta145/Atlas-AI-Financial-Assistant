import asyncio
from app.finance.research import research_company
from dotenv import load_dotenv

async def main():
    load_dotenv()
    res = await research_company("Nvidia", include_market=True, include_news=False, include_sec=False)
    
    symbol = res.get("symbol")
    market_data = res.get("data", {}).get("market") or {}
    market_error = res.get("errors", {}).get("market")
    
    market_ok = "True" if not market_error and market_data else "False"
    price = market_data.get("price")
    change = market_data.get("change")
    change_percent = market_data.get("change_percent")
    source = market_data.get("source")
    timestamp = market_data.get("timestamp")
    
    print(f"symbol: {symbol}")
    print(f"market_ok: {market_ok}")
    print(f"price: {price}")
    print(f"change: {change}")
    print(f"change_percent: {change_percent}")
    print(f"source: {source}")
    print(f"timestamp: {timestamp}")
    print(f"error: {market_error}")

if __name__ == "__main__":
    asyncio.run(main())
