import pytest

from app.finance.research import research_company


@pytest.mark.asyncio
async def test_research_company_basic(monkeypatch):
    class FakeFH:
        async def get_quote(self, symbol):
            return {"symbol": symbol, "price": 123.45, "retrieved_at": 1, "source": "Finnhub"}

    class FakeNC:
        async def company_news(self, symbol, start, end):
            return [{"headline": "news", "datetime": start}]

    monkeypatch.setattr("app.finance.research.FinnhubMarketClient", lambda: FakeFH())
    monkeypatch.setattr("app.finance.research.NewsClient", lambda: FakeNC())

    res = await research_company("NVDA", include_market=True, include_news=True, include_sec=False)
    assert res["symbol"] == "NVDA"
    assert "market" in res["data"]
    assert "news" in res["data"]
    assert res["errors"]["market"] is None
    assert res["errors"]["news"] is None


@pytest.mark.asyncio
async def test_research_company_resolves_company_name(monkeypatch):
    class FakeFH:
        async def get_quote(self, symbol):
            return {"symbol": symbol, "price": 100.0, "retrieved_at": 1, "source": "Finnhub"}

    monkeypatch.setattr("app.finance.research.FinnhubMarketClient", lambda: FakeFH())
    monkeypatch.setattr("app.finance.research.NewsClient", lambda: type("NC", (), {"company_news": lambda *args, **kwargs: []})())

    res = await research_company("Nvidia", include_market=True, include_news=False, include_sec=False)
    assert res["symbol"] == "NVDA"
    assert res["data"]["market"]["symbol"] == "NVDA"
