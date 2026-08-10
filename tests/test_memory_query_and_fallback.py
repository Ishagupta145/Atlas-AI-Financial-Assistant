import pytest
from unittest.mock import patch, AsyncMock
from app.main import handle_message

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
async def test_memory_query_companies():
    update = MockUpdate("What companies do I follow?")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {"companies_followed": ["Nvidia", "AMD"]}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={}):
                        with patch("app.main.ask_atlas", side_effect=RuntimeError('RATE_LIMIT')):
                            # Gemini is rate limited, but since it's a memory query, we shouldn't even call ask_atlas
                            await handle_message(update, None)
                            
                            reply_args = update.message.reply_text.call_args[0][0]
                            assert "You currently follow:" in reply_args
                            assert "Nvidia" in reply_args
                            assert "AMD" in reply_args
                            assert "saved" not in reply_args  # Should not use the 'saved' response

@pytest.mark.asyncio
async def test_memory_query_all():
    update = MockUpdate("What do you remember about me?")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {"role": "analyst", "interests": ["AI"]}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={}):
                        await handle_message(update, None)
                        
                        reply_args = update.message.reply_text.call_args[0][0]
                        assert "Role: analyst" in reply_args
                        assert "AI" in reply_args

@pytest.mark.asyncio
async def test_follow_up_reasoning_rate_limit():
    update = MockUpdate("Does this matter for my AI infrastructure thesis?")
    
    # Simulate recent history containing market data from the assistant
    history = [
        ("user", "Why is Nvidia moving today?"),
        ("assistant", "Symbol: NVDA\nLatest price: 100\nChange percent: 2\nSource: Finnhub\n\nAI Analysis here")
    ]
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = history
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {"interests": ["AI infrastructure"]}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={}):
                        with patch("app.main.ask_atlas", side_effect=RuntimeError('RATE_LIMIT')):
                            await handle_message(update, None)
                            
                            reply_args = update.message.reply_text.call_args[0][0]
                            assert "I have the relevant context" in reply_args
                            assert "temporarily rate-limited" in reply_args
                            assert "don't want to speculate" in reply_args
                            assert "Symbol: NVDA" in reply_args
                            assert "Latest price: 100" in reply_args

@pytest.mark.asyncio
async def test_movement_query_rate_limit_returns_live_data():
    update = MockUpdate("Why is Nvidia moving today?")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={}):
                        with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
                            mock_research.return_value = {
                                "symbol": "NVDA",
                                "data": {
                                    "market": {"symbol": "NVDA", "price": 100, "change_percent": 1.5},
                                    "news": []
                                }
                            }
                            with patch("app.main.ask_atlas_with_financial_evidence", side_effect=RuntimeError('RATE_LIMIT')):
                                await handle_message(update, None)
                                
                                reply_args = update.message.reply_text.call_args[0][0]
                                assert "temporarily unavailable due to rate limits" in reply_args
                                assert "Latest price: 100" in reply_args

@pytest.mark.asyncio
async def test_normal_gemini_operation_unchanged():
    update = MockUpdate("Hello")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={}):
                        with patch("app.main.ask_atlas", new_callable=AsyncMock) as mock_ask:
                            mock_ask.return_value = "Normal response"
                            await handle_message(update, None)
                            
                            reply_args = update.message.reply_text.call_args[0][0]
                            assert reply_args == "Normal response"
