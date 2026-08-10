import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_late_binding_finnhub_api_key():
    # 1. Ensure FINNHUB_API_KEY is not set initially
    if "FINNHUB_API_KEY" in os.environ:
        del os.environ["FINNHUB_API_KEY"]

    # Import modules (importing should not fail or cache the empty key)
    import app.finance.research as research
    import app.finance.news as news

    # Verify that without key, calling research_company handles the missing key error gracefully
    res = await research.research_company("Nvidia", include_market=True, include_news=False, include_sec=False)
    assert res["errors"]["market"] == "FINNHUB_API_KEY is not configured"

    # 2. Set the environment variable AFTER import
    os.environ["FINNHUB_API_KEY"] = "late-bound-key"

    try:
        # Mock the HTTPX async client to avoid real network calls
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "c": 150.0, "pc": 145.0, "d": 5.0, "dp": 3.4,
                "o": 146.0, "h": 155.0, "l": 140.0, "v": 1000000, "t": 1600000000
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # 3. Call research_company()
            res = await research.research_company("Nvidia", include_market=True, include_news=False, include_sec=False)

            # 4. The client successfully receives the newly available key
            assert res["errors"]["market"] is None
            assert res["data"]["market"]["price"] == 150.0
            
            # Verify the mock was called with the correct late-bound key
            mock_get.assert_called_once()
            call_args, call_kwargs = mock_get.call_args
            assert call_kwargs["params"]["token"] == "late-bound-key"
    finally:
        if "FINNHUB_API_KEY" in os.environ:
            del os.environ["FINNHUB_API_KEY"]


@pytest.mark.asyncio
async def test_explicit_api_key_override():
    if "FINNHUB_API_KEY" in os.environ:
        del os.environ["FINNHUB_API_KEY"]
    
    os.environ["FINNHUB_API_KEY"] = "env-key"
    
    try:
        from app.finance.news import FinnhubMarketClient
        
        client = FinnhubMarketClient(api_key="explicit-key")
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "c": 150.0, "pc": 145.0, "d": 5.0, "dp": 3.4,
                "o": 146.0, "h": 155.0, "l": 140.0, "v": 1000000, "t": 1600000000
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            await client.get_quote("NVDA")
            
            mock_get.assert_called_once()
            call_args, call_kwargs = mock_get.call_args
            assert call_kwargs["params"]["token"] == "explicit-key"
    finally:
        if "FINNHUB_API_KEY" in os.environ:
            del os.environ["FINNHUB_API_KEY"]

@pytest.mark.asyncio
async def test_missing_key_controlled_error():
    if "FINNHUB_API_KEY" in os.environ:
        del os.environ["FINNHUB_API_KEY"]
    
    from app.finance.news import FinnhubMarketClient
    client = FinnhubMarketClient()
    
    with pytest.raises(RuntimeError, match="FINNHUB_API_KEY is not configured"):
        await client.get_quote("NVDA")
