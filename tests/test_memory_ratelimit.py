import pytest
import json
from unittest.mock import patch, AsyncMock
from app.main import handle_message
from app.ai.agent import extract_user_memory
from google.genai import errors as genai_errors

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
async def test_deterministic_extraction_without_gemini():
    # Simulate Gemini failing with ClientError inside extract_user_memory
    with patch("app.ai.agent.client.aio.models.generate_content", side_effect=Exception("Rate Limit")):
        mem = await extract_user_memory("I'm an investment analyst. I follow Nvidia, AMD and TSMC, and I'm interested in AI infrastructure.", [])
        
        assert mem.get("role") == "an investment analyst"
        
        companies = mem.get("companies_followed", [])
        assert "Nvidia" in companies
        assert "AMD" in companies
        assert "TSMC" in companies
        
        interests = mem.get("interests", [])
        assert "AI infrastructure" in interests

@pytest.mark.asyncio
async def test_memory_persists_when_gemini_rate_limited():
    update = MockUpdate("I'm an investment analyst. I follow Nvidia, AMD and TSMC, and I'm interested in AI infrastructure.")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {}
            with patch("app.main.save_user_memory", new_callable=AsyncMock) as mock_save_mem:
                with patch("app.main.save_message", new_callable=AsyncMock) as mock_save_msg:
                    # Make Gemini fail inside handle_message (during ask_atlas)
                    with patch("app.main.ask_atlas", side_effect=RuntimeError('RATE_LIMIT')):
                        
                        # We also mock the Gemini call inside extract_user_memory to simulate it being fully down
                        with patch("app.main.extract_user_memory", return_value={"role": "investment analyst", "companies_followed": ["Nvidia", "AMD", "TSMC"], "interests": ["AI infrastructure"]}):
                            await handle_message(update, None)
                            
                            # Memory should be saved!
                            assert mock_save_mem.call_count == 3
                            
                            # The reply should acknowledge the saved memory
                            reply_args = update.message.reply_text.call_args[0][0]
                            assert "Got it — I've saved your" in reply_args
                            assert "role (investment analyst)" in reply_args
                            assert "coverage list (Nvidia, AMD, TSMC)" in reply_args
                            assert "interest (AI infrastructure)" in reply_args
                            assert "temporarily rate-limited" in reply_args

@pytest.mark.asyncio
async def test_normal_gemini_flow_unchanged():
    update = MockUpdate("I'm an investment analyst.")
    
    with patch("app.main.get_recent_messages", new_callable=AsyncMock) as mock_history:
        mock_history.return_value = []
        with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_get_mem:
            mock_get_mem.return_value = {}
            with patch("app.main.save_user_memory", new_callable=AsyncMock):
                with patch("app.main.save_message", new_callable=AsyncMock):
                    with patch("app.main.extract_user_memory", return_value={"role": "investment analyst"}):
                        with patch("app.main.ask_atlas", new_callable=AsyncMock) as mock_ask:
                            mock_ask.return_value = "Normal AI Response"
                            await handle_message(update, None)
                            
                            reply_args = update.message.reply_text.call_args[0][0]
                            assert reply_args == "Normal AI Response"
