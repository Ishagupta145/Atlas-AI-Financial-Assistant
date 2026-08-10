import asyncio
from app.finance.market_data import MarketDataClient
from app.finance.news import NewsClient
from app.finance.sec import SECClient


def run_sync(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def main():
    # market normalize
    md = MarketDataClient(api_key="test", base_url="https://example.com")
    raw = {
        "price": 100.0,
        "previous_close": 90.0,
        "company": "NVIDIA",
        "open": 95.0,
        "high": 101.0,
        "low": 94.0,
        "volume": 123456,
        "timestamp": 1690000000,
    }
    normalized = md._normalize_quote("NVDA", raw)
    assert normalized["symbol"] == "NVDA"
    assert normalized["company"] == "NVIDIA"

    # news normalize
    nc = NewsClient(api_key="test")
    rawn = {"headline": "Big news", "source": "NewsOrg", "datetime": 1690000000, "url": "https://x"}
    norm = nc._normalize(rawn)
    assert norm["title"] == "Big news"

    # sec empty
    sc = SECClient()
    res = run_sync(sc.recent_filings("000000"))
    assert isinstance(res, list)

    print("All lightweight finance checks passed")


if __name__ == '__main__':
    main()
