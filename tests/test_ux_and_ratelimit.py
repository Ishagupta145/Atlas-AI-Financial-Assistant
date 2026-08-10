import pytest
from unittest.mock import patch, AsyncMock
from app.main import handle_message, _looks_like_direct_price_query, _looks_like_market_query
import types

class MockMessage:
    def __init__(self, text):
        self.text = text
        self.reply_text = AsyncMock()

class MockUser:
    def __init__(self, id):
        self.id = id

class MockUpdate:
    def __init__(self, text, user_id=123):
        self.message = MockMessage(text)
        self.effective_user = MockUser(user_id)

@pytest.mark.asyncio
async def test_direct_price_query_routing():
    assert _looks_like_direct_price_query("What is Nvidia trading at today?")
    assert _looks_like_direct_price_query("price of NVDA")
    assert _looks_like_direct_price_query("How much is AMD?")
    
    # Movement queries should not be direct price queries
    assert not _looks_like_direct_price_query("Why is Nvidia moving?")
    assert not _looks_like_direct_price_query("What's happening with TSLA?")
    assert not _looks_like_direct_price_query("Why did NVDA rise today?")

@pytest.mark.asyncio
async def test_movement_query_routing():
    assert _looks_like_market_query("Why is Nvidia moving?")
    assert _looks_like_market_query("What's happening with TSLA?")

@pytest.mark.asyncio
async def test_direct_price_query_executes_without_news():
    update = MockUpdate("What is Nvidia trading at today?")
    
    with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
        mock_research.return_value = {
            "symbol": "NVDA",
            "data": {
                "market": {"symbol": "NVDA", "price": 100, "change_percent": 1.5, "source": "Finnhub"}
            }
        }
        
        with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = []
            
            with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_mem:
                mock_mem.return_value = {}
                
                with patch("app.main.extract_user_memory", new_callable=AsyncMock) as mock_extract:
                    mock_extract.return_value = {}
                    
                    with patch("app.main.ask_atlas_with_financial_evidence", new_callable=AsyncMock) as mock_ask:
                        await handle_message(update, None)
                        
                        mock_research.assert_called_once_with(
                            "What is Nvidia trading at today?",
                            include_market=True,
                            include_news=False,
                            include_sec=False
                        )
                        
                        # AI should not be called
                        mock_ask.assert_not_called()
                        
                        # The reply should just be the market evidence
                        reply_args = update.message.reply_text.call_args[0][0]
                        assert "Latest price: 100" in reply_args

@pytest.mark.asyncio
async def test_movement_query_executes_with_news_and_ai():
    update = MockUpdate("Why is Nvidia moving?")
    
    with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
        mock_research.return_value = {
            "symbol": "NVDA",
            "data": {
                "market": {"symbol": "NVDA", "price": 100, "change_percent": 1.5},
                "news": [{"title": "News!", "relevance_score": 10}]
            }
        }
        
        with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = []
            with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_mem:
                mock_mem.return_value = {}
                with patch("app.main.extract_user_memory", new_callable=AsyncMock) as mock_extract:
                    mock_extract.return_value = {}
                    with patch("app.main.ask_atlas_with_financial_evidence", new_callable=AsyncMock) as mock_ask:
                        mock_ask.return_value = "AI Analysis"
                        
                        await handle_message(update, None)
                        
                        mock_research.assert_called_once_with(
                            "Why is Nvidia moving?",
                            include_market=True,
                            include_news=True,
                            include_sec=False
                        )
                        mock_ask.assert_called_once()
                        
                        reply_args = update.message.reply_text.call_args[0][0]
                        assert "AI Analysis" in reply_args

@pytest.mark.asyncio
async def test_gemini_rate_limit_with_live_market_data():
    update = MockUpdate("Why is Nvidia moving?")
    
    with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
        mock_research.return_value = {
            "symbol": "NVDA",
            "data": {
                "market": {"symbol": "NVDA", "price": 100, "change_percent": 1.5},
                "news": []
            }
        }
        
        with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = []
            with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_mem:
                mock_mem.return_value = {}
                with patch("app.main.extract_user_memory", new_callable=AsyncMock) as mock_extract:
                    mock_extract.return_value = {}
                    with patch("app.main.ask_atlas_with_financial_evidence", side_effect=RuntimeError('RATE_LIMIT')):
                        await handle_message(update, None)
                        
                        reply_args = update.message.reply_text.call_args[0][0]
                        assert "Atlas AI interpretation is temporarily unavailable" in reply_args
                        assert "Latest price: 100" in reply_args

@pytest.mark.asyncio
async def test_gemini_rate_limit_no_market_data():
    update = MockUpdate("What is your name?")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = {}
            with patch("app.main.extract_user_memory", new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = {}
                with patch("app.main.ask_atlas", side_effect=RuntimeError('RATE_LIMIT')):
                    await handle_message(update, None)
                    
                    reply_args = update.message.reply_text.call_args[0][0]
                    assert "Atlas is temporarily rate-limited and cannot generate an AI response" in reply_args
