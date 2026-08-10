import pytest
import httpx

from app.finance.sec import SECClient, SECNotFoundError, SECRateLimitError, SECRequestError
from app.finance import sec as secmod


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
async def test_resolve_ticker_to_cik_success(monkeypatch):
    client = SECClient(user_agent="test-agent")

    # ensure in-memory map is clear and mock fetching company_tickers.json
    secmod._TICKER_TO_CIK = {}
    sample = {
        "0": {"cik_str": "12345", "ticker": "NVDA", "title": "NVIDIA CORP"}
    }

    async def fake_get(self, url):
        return FakeResp(200, sample)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    cik = await client.resolve_ticker_to_cik("NVDA")
    assert cik == "0000012345"


@pytest.mark.asyncio
async def test_recent_filings_success(monkeypatch):
    client = SECClient(user_agent="test-agent")
    secmod._TICKER_TO_CIK = {}

    # monkeypatch resolve_ticker_to_cik to avoid fetching the big map
    async def fake_resolve(token):
        return "0000012345"

    client.resolve_ticker_to_cik = fake_resolve

    # craft submissions JSON
    submissions = {"name": "NVIDIA CORP", "filings": {"recent": {"accessionNumber": ["000-1"], "form": ["10-Q"], "filingDate": ["2026-08-01"], "reportType": ["Quarterly"]}}}

    async def fake_get(self, url):
        return FakeResp(200, submissions)

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    res = await client.recent_filings("NVDA", count=1)
    assert isinstance(res, list) and len(res) == 1
    f = res[0]
    assert f["company"] == "NVIDIA CORP"
    assert f["form"] == "10-Q"


@pytest.mark.asyncio
async def test_invalid_ticker(monkeypatch):
    client = SECClient(user_agent="test-agent")
    # return empty mapping
    secmod._TICKER_TO_CIK = {}
    async def fake_get_map(self, url):
        return FakeResp(200, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get_map})())

    with pytest.raises(SECNotFoundError):
        await client.resolve_ticker_to_cik("UNKNOWN")


@pytest.mark.asyncio
async def test_sec_429(monkeypatch):
    client = SECClient(user_agent="test-agent")
    secmod._TICKER_TO_CIK = {}

    async def fake_get(self, url):
        return FakeResp(429, {})

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(SECRateLimitError):
        await client._ensure_ticker_map()


@pytest.mark.asyncio
async def test_sec_network_failure(monkeypatch):
    client = SECClient(user_agent="test-agent")
    secmod._TICKER_TO_CIK = {}

    async def fake_get(self, url):
        raise Exception("network down")

    monkeypatch.setattr(client, "_client", type("C", (), {"get": fake_get})())

    with pytest.raises(SECRequestError):
        await client._ensure_ticker_map()
