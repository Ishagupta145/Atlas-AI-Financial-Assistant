import pytest
import httpx
import time

from app.finance.market_data import MarketDataClient


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
async def test_massive_success(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    sample = {
        "status": "OK",
        "ticker": {
            "ticker": "NVDA",
            "day": {"c": 100.25, "h": 101.5, "l": 99.2, "o": 99.8, "v": 12345678},
            "prevDay": {"c": 97.5, "h": 98.1, "l": 96.4, "o": 96.9, "v": 12000000},
            "todaysChange": 2.75,
            "todaysChangePerc": 2.82,
            "updated": 1723305600,
            "lastTrade": {"price": 103.0, "timestamp": 1723305660},
        },
    }

    seen = {}

    async def fake_get(self, url, params=None, **kwargs):
        seen["url"] = url
        seen["params"] = params
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
    async def _no_sleep(s):
        return None

    monkeypatch.setattr(client, "_sleep", _no_sleep)

    res = await client.get_quote("NVDA")
    assert seen["url"] == "https://api.massive.test/v2/snapshot/locale/us/markets/stocks/tickers/NVDA"
    assert seen["params"] == {"apiKey": "test-key"}
    assert res["symbol"] == "NVDA"
    assert res["price"] == 103.0
    assert res["previous_close"] == 97.5
    assert res["change"] == pytest.approx(2.75)
    assert res["change_percent"] == pytest.approx(2.82)
    assert res["open"] == 99.8
    assert res["high"] == 101.5
    assert res["low"] == 99.2
    assert res["volume"] == 12345678
    assert res["timestamp"] == 1723305660
    assert res["source"] == "Massive"


@pytest.mark.asyncio
async def test_massive_retry_then_success(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    sample = {
        "status": "OK",
        "ticker": {
            "ticker": "TST",
            "day": {"c": 10.0, "h": 10.5, "l": 9.5, "o": 9.8, "v": 100},
            "prevDay": {"c": 9.0},
            "todaysChange": 1.0,
            "todaysChangePerc": 11.11,
            "updated": 1690000000,
        },
    }
    calls = {"n": 0}

    async def fake_get(self, url, params=None, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResp(429, {})
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
    async def _no_sleep(s):
        return None

    monkeypatch.setattr(client, "_sleep", _no_sleep)

    res = await client.get_quote("TST")
    assert res["price"] == 10.0
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_massive_rate_limited_final(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(429, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
    async def _no_sleep(s):
        return None

    monkeypatch.setattr(client, "_sleep", _no_sleep)

    with pytest.raises(RuntimeError) as ei:
        await client.get_quote("TST")
    assert "429" in str(ei.value) or "Rate limited" in str(ei.value)


@pytest.mark.asyncio
async def test_massive_timeout(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(httpx.ReadTimeout):
        await client.get_quote("TST")


@pytest.mark.asyncio
async def test_massive_missing_fields(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    sample = {"status": "OK", "ticker": {"ticker": "TST"}}

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.get_quote("TST")
    assert res["price"] is None
    assert res["previous_close"] is None
    assert res["change"] is None
    assert res["change_percent"] is None


@pytest.mark.asyncio
async def test_massive_missing_api_key():
    client = MarketDataClient(api_key=None, base_url="https://api.massive.test")
    with pytest.raises(RuntimeError, match="MASSIVE_API_KEY"):
        await client.get_quote("TST")


@pytest.mark.asyncio
async def test_massive_auth_errors(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    for status in (401, 403):
        async def fake_get(self, url, params=None, **kwargs):
            return FakeResp(status, {})

        monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
        with pytest.raises(RuntimeError, match="401|403|Unauthorized|Forbidden"):
            await client.get_quote("TST")


@pytest.mark.asyncio
async def test_massive_unknown_symbol(monkeypatch):
    client = MarketDataClient(api_key="test-key", base_url="https://api.massive.test")

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp(404, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())
    with pytest.raises(RuntimeError, match="404|not found|unknown"):
        await client.get_quote("UNKNOWN")
