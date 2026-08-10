import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.finance.news import NewsClient
from app.finance.research import (
    research_company, 
    analyze_market_movement, 
    score_article_relevance, 
    determine_evidence_confidence
)
from app.main import _looks_like_market_query
from app.ai.agent import ask_atlas_with_financial_evidence
import httpx
import os

@pytest.fixture
def news_client():
    os.environ["FINNHUB_API_KEY"] = "test-key"
    return NewsClient()

# -- Basic Client Tests --

@pytest.mark.asyncio
async def test_news_success(news_client):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"headline": "Test", "datetime": 123}]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        news = await news_client.company_news("NVDA", "2024-01-01", "2024-01-02")
        assert len(news) == 1
        assert news[0]["title"] == "Test"

@pytest.mark.asyncio
async def test_news_empty(news_client):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        news = await news_client.company_news("NVDA", "2024-01-01", "2024-01-02")
        assert len(news) == 0

@pytest.mark.asyncio
async def test_news_429(news_client):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="Finnhub rate limited"):
            await news_client.company_news("NVDA", "2024-01-01", "2024-01-02")

@pytest.mark.asyncio
async def test_news_network_failure(news_client):
    with patch("httpx.AsyncClient.get", side_effect=httpx.NetworkError("NetError")):
        with pytest.raises(RuntimeError, match="network request failed"):
            await news_client.company_news("NVDA", "2024-01-01", "2024-01-02")

@pytest.mark.asyncio
async def test_news_normalization(news_client):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            "headline": "Title",
            "source": "Yahoo",
            "datetime": 12345,
            "url": "http://example.com",
            "summary": "Sum"
        }]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        news = await news_client.company_news("NVDA", "2024-01-01", "2024-01-02")
        assert news[0]["title"] == "Title"

# -- Orchestration Tests --

@pytest.mark.asyncio
async def test_research_company_both():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.return_value = {"price": 100, "symbol": "NVDA"}
            mock_news.return_value = [{"title": "Nvidia launches new chip", "published_at": 1}]
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            assert res["data"]["market"]["price"] == 100
            assert res["data"]["news"][0]["title"] == "Nvidia launches new chip"

@pytest.mark.asyncio
async def test_market_succeeds_news_fails():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.return_value = {"price": 100, "symbol": "NVDA"}
            mock_news.side_effect = Exception("News Error")
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            assert res["data"]["market"]["price"] == 100
            assert "News Error" in res["errors"]["news"]

@pytest.mark.asyncio
async def test_news_succeeds_market_fails():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.side_effect = Exception("Market Error")
            mock_news.return_value = [{"title": "Nvidia rocks", "published_at": 1}]
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            assert "Market Error" in res["errors"]["market"]
            assert res["data"]["news"][0]["title"] == "Nvidia rocks"


# -- Relevance and Filtering Tests --

def test_relevance_direct():
    t, s = score_article_relevance({"title": "Nvidia announces new AI chip"}, "NVDA")
    assert t == "direct"
    assert s == 10
    
    t, s = score_article_relevance({"title": "NVDA surges today"}, "NVDA")
    assert t == "direct"
    assert s == 10

def test_relevance_industry():
    t, s = score_article_relevance({"title": "New AI chips shake up data center market"}, "NVDA")
    assert t == "industry"
    assert s == 5

def test_relevance_irrelevant():
    t, s = score_article_relevance({"title": "Disney releases new movie"}, "NVDA")
    assert t == "irrelevant"
    assert s == 0
    
    t, s = score_article_relevance({"title": "P&G reports strong earnings"}, "NVDA")
    assert t == "irrelevant"
    assert s == 0

def test_cross_contamination():
    t, s = score_article_relevance({"title": "Apple releases new iPhone"}, "NVDA")
    assert t == "irrelevant"
    
    t, s = score_article_relevance({"title": "Nvidia announces new AI chip"}, "TSLA")
    assert t == "irrelevant"

@pytest.mark.asyncio
async def test_irrelevant_articles_removed():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.return_value = {"price": 100, "symbol": "NVDA"}
            mock_news.return_value = [
                {"title": "Nvidia announces AI chips", "published_at": 1},
                {"title": "Disney releases new movie", "published_at": 2}
            ]
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            news = res["data"]["news"]
            assert len(news) == 1
            assert news[0]["title"] == "Nvidia announces AI chips"

@pytest.mark.asyncio
async def test_sorting_direct_before_industry():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.return_value = {"price": 100, "symbol": "NVDA"}
            mock_news.return_value = [
                {"title": "Data center demand increases", "published_at": 2}, # industry
                {"title": "Nvidia announces earnings", "published_at": 1} # direct
            ]
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            news = res["data"]["news"]
            assert len(news) == 2
            assert news[0]["title"] == "Nvidia announces earnings" # Higher score wins despite older date
            assert news[1]["title"] == "Data center demand increases"

@pytest.mark.asyncio
async def test_fewer_than_5_does_not_fill():
    with patch("app.finance.news.FinnhubMarketClient.get_quote", new_callable=AsyncMock) as mock_market:
        with patch("app.finance.news.NewsClient.company_news", new_callable=AsyncMock) as mock_news:
            mock_market.return_value = {"price": 100, "symbol": "NVDA"}
            mock_news.return_value = [
                {"title": "Nvidia announces AI chips", "published_at": 1},
                {"title": "Disney releases new movie", "published_at": 2},
                {"title": "P&G earnings", "published_at": 3},
                {"title": "Irrelevant stuff", "published_at": 4},
                {"title": "More irrelevant stuff", "published_at": 5},
                {"title": "Even more irrelevant stuff", "published_at": 6}
            ]
            
            res = await research_company("Nvidia", include_market=True, include_news=True)
            news = res["data"]["news"]
            assert len(news) == 1 # Did not fill with irrelevant articles
            assert news[0]["title"] == "Nvidia announces AI chips"

# -- Confidence Tests --

def test_confidence_levels():
    assert determine_evidence_confidence([]) == "low"
    
    assert determine_evidence_confidence([
        {"relevance_type": "direct"}
    ]) == "medium"
    
    assert determine_evidence_confidence([
        {"relevance_type": "direct"},
        {"relevance_type": "direct"}
    ]) == "high"
    
    assert determine_evidence_confidence([
        {"relevance_type": "industry"}
    ]) == "medium"
    
    assert determine_evidence_confidence([
        {"relevance_type": "industry"},
        {"relevance_type": "industry"}
    ]) == "medium"

# -- AI Prompt Tests --

@pytest.mark.asyncio
async def test_ai_receives_evidence_and_prohibits_claims():
    with patch("app.ai.agent.ask_atlas", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = "Response"
        await ask_atlas_with_financial_evidence("test", [], {}, "EV")
        mock_ask.assert_called_once()
        args, _ = mock_ask.call_args
        prompt = args[0]
        assert "EV" in prompt
        assert "FINANCIAL EVIDENCE" in prompt
        assert "NEVER say 'This caused the stock to rise'" in prompt
        assert "Evidence confidence is 'low'" in prompt

# -- Intent Detection --

def test_intent_detection():
    assert _looks_like_market_query("Why is Nvidia moving?")
    assert _looks_like_market_query("Why is Nvidia up today?")
    assert _looks_like_market_query("What's happening with Tesla?")
    assert _looks_like_market_query("Why did Apple stock move?")
    
    assert not _looks_like_market_query("How do you make a cake?")
    assert not _looks_like_market_query("What is the capital of France?")
