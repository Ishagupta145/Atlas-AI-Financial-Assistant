import pytest
import httpx

from app.finance.news import FinnhubMarketClient
from app.finance.research import research_company


class FakeResp:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("HTTP error", request=None, response=None)


@pytest.mark.asyncio
async def test_finnhub_quote_success(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")
    sample = {"c": 100.0, "d": 1.5, "dp": 1.5, "h": 101.0, "l": 99.0, "o": 98.0, "pc": 98.5, "t": 1723305600}
    seen = {}

    async def fake_get(self, url, params=None, **kwargs):
        seen["url"] = url
        seen["params"] = params
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.get_quote("NVDA")
    assert seen["url"] == "https://finnhub.test/api/v1/quote"
    assert seen["params"] == {"symbol": "NVDA", "token": "test-key"}
    assert res["symbol"] == "NVDA"
    assert res["price"] == 100.0
    assert res["previous_close"] == 98.5
    assert res["change"] == pytest.approx(1.5)
    assert res["change_percent"] == pytest.approx(1.5)
    assert res["open"] == 98.0
    assert res["high"] == 101.0
    assert res["low"] == 99.0
    assert res["volume"] is None
    assert res["source"] == "Finnhub"


@pytest.mark.asyncio
async def test_finnhub_quote_missing_fields(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(200, {"c": 55.0})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.get_quote("AAPL")
    assert res["symbol"] == "AAPL"
    assert res["price"] == 55.0
    assert res["previous_close"] is None
    assert res["change"] is None
    assert res["change_percent"] is None
    assert res["volume"] is None


@pytest.mark.asyncio
async def test_finnhub_quote_401(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(401, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError, match="401|Unauthorized"):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_finnhub_quote_403(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(403, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError, match="403|Forbidden"):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_finnhub_quote_429(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(429, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError, match="429|Rate"):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_finnhub_quote_timeout(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(httpx.ReadTimeout):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_finnhub_quote_malformed_response(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(200, "bad")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError, match="malformed|invalid"):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_finnhub_quote_network_failure(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")

    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.NetworkError("network down")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError, match="network|failed"):
        await client.get_quote("NVDA")


@pytest.mark.asyncio
async def test_research_company_uses_finnhub_market(monkeypatch):
    client = FinnhubMarketClient(api_key="test-key", base="https://finnhub.test/api/v1")
    sample = {"c": 10.0, "d": 0.5, "dp": 5.0, "h": 10.5, "l": 9.5, "o": 9.8, "pc": 9.5, "t": 1723305600}

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
    monkeypatch.setattr("app.finance.research.FinnhubMarketClient", lambda *args, **kwargs: client)

    result = await research_company("Nvidia", include_market=True, include_news=False, include_sec=False)
    market = result["data"]["market"]
    assert result["symbol"] == "NVDA"
    assert market["source"] == "Finnhub"
    assert market["price"] == 10.0
