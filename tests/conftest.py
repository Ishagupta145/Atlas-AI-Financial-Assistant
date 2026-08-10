import pytest
import httpx


@pytest.fixture(autouse=True)
def block_external_requests(monkeypatch):
    """Prevent accidental real HTTP requests during tests.

    Tests should replace client._client with a fake object; any remaining
    calls to httpx.AsyncClient.get will raise an error.
    """

    async def _blocked(self, *args, **kwargs):
        raise RuntimeError("Real network access is disabled during tests")

    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked)
    yield