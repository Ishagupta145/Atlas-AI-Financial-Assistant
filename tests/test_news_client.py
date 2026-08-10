import pytest
import httpx

from app.finance.news import NewsClient


class FakeResp:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or []

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("HTTP error", request=None, response=None)


@pytest.mark.asyncio
async def test_finnhub_success(monkeypatch):
    client = NewsClient(api_key="test-key", base="https://finnhub.test")

    sample = [
        {"headline": "Title A", "source": "SourceX", "datetime": 1690000000, "url": "https://a", "summary": "sum"}
    ]

    async def fake_get(self, url, params=None):
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.company_news("TST", "2026-01-01", "2026-01-07")
    assert isinstance(res, list) and len(res) == 1
    n = res[0]
    assert n["title"] == "Title A"
    assert n["source"] == "SourceX"
    assert n["published_at"] == 1690000000
    assert n["url"] == "https://a"
    assert n["summary"] == "sum"


@pytest.mark.asyncio
async def test_finnhub_empty(monkeypatch):
    client = NewsClient(api_key="test-key", base="https://finnhub.test")

    async def fake_get(self, url, params=None):
        return FakeResp(200, [])

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.company_news("TST", "2026-01-01", "2026-01-07")
    assert res == []


@pytest.mark.asyncio
async def test_finnhub_429(monkeypatch):
    client = NewsClient(api_key="test-key", base="https://finnhub.test")

    async def fake_get(self, url, params=None):
        return FakeResp(429, [])

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(RuntimeError):
        await client.company_news("TST", "2026-01-01", "2026-01-07")


@pytest.mark.asyncio
async def test_finnhub_network_failure(monkeypatch):
    client = NewsClient(api_key="test-key", base="https://finnhub.test")

    async def fake_get(self, url, params=None):
        raise Exception("network down")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(Exception):
        await client.company_news("TST", "2026-01-01", "2026-01-07")
