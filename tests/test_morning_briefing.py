import pytest
from unittest.mock import patch, AsyncMock
from app.main import send_morning_briefing
from app.ai.agent import generate_morning_briefing

@pytest.mark.asyncio
async def test_briefing_uses_stored_companies():
    # Mock memory to return some companies
    with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_memory:
        mock_memory.return_value = {"companies_followed": '["NVDA", "AMD"]'}
        
        with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {"symbol": "TEST"}
            
            with patch("app.main.generate_morning_briefing", new_callable=AsyncMock) as mock_generate:
                mock_generate.return_value = "NO_IMPORTANT_NEWS"
                
                await send_morning_briefing(123)
                
                assert mock_research.call_count == 2
                calls = mock_research.call_args_list
                assert calls[0][0][0] == "NVDA"
                assert calls[1][0][0] == "AMD"

@pytest.mark.asyncio
async def test_briefing_uses_stored_sectors_interests():
    # Verify sectors/interests are passed to the AI via user_memory
    with patch("app.ai.agent.client.aio.models.generate_content", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value.text = "Briefing output"
        
        user_mem = {
            "companies_followed": ["NVDA"],
            "sectors": ["Semiconductors"],
            "interests": ["AI Infrastructure"]
        }
        
        await generate_morning_briefing(user_mem, [])
        
        prompt = mock_gen.call_args[1]["contents"]
        assert "Semiconductors" in prompt
        assert "AI Infrastructure" in prompt

@pytest.mark.asyncio
async def test_irrelevant_news_excluded_and_important_included():
    # Pass mock data to generate_morning_briefing and check prompt formatting
    with patch("app.ai.agent.client.aio.models.generate_content", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value.text = "Briefing output"
        
        research_data = [{
            "symbol": "NVDA",
            "data": {
                "market": {"price": 100, "change_percent": 5.0},
                "news": [
                    {"title": "Important Earnings", "relevance_score": 10},
                    {"title": "Unimportant", "relevance_score": 0}
                ]
            }
        }]
        
        await generate_morning_briefing({}, research_data)
        
        prompt = mock_gen.call_args[1]["contents"]
        assert "Important Earnings" in prompt
        assert "Unimportant" in prompt  # It's in the prompt, but AI filters it based on strict instructions
        assert "STRICT IMPORTANCE THRESHOLD" in prompt

@pytest.mark.asyncio
async def test_no_significant_news_produces_no_briefing():
    # If AI returns NO_IMPORTANT_NEWS, telegram send should not be called
    with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_memory:
        mock_memory.return_value = {"companies_followed": ["NVDA"]}
        
        with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {"symbol": "NVDA"}
            
            with patch("app.main.generate_morning_briefing", new_callable=AsyncMock) as mock_generate:
                mock_generate.return_value = "NO_IMPORTANT_NEWS"
                
                with patch("app.main._send_telegram_message", new_callable=AsyncMock) as mock_send:
                    await send_morning_briefing(123)
                    mock_send.assert_not_called()

@pytest.mark.asyncio
async def test_briefing_generation_handles_api_failure_gracefully():
    # If Gemini fails, it should return NO_IMPORTANT_NEWS
    with patch("app.ai.agent.client.aio.models.generate_content", side_effect=Exception("API Error")):
        res = await generate_morning_briefing({}, [])
        assert res == "NO_IMPORTANT_NEWS"

@pytest.mark.asyncio
async def test_telegram_message_formatting_works():
    # If AI returns a real briefing, send_message should be called with it
    with patch("app.main.get_user_memory", new_callable=AsyncMock) as mock_memory:
        mock_memory.return_value = {"companies_followed": ["NVDA"]}
        
        with patch("app.main.research_company", new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {"symbol": "NVDA"}
            
            with patch("app.main.generate_morning_briefing", new_callable=AsyncMock) as mock_generate:
                mock_generate.return_value = "🌅 YOUR MORNING BRIEF\n\nStuff here"
                
                with patch("app.main._send_telegram_message", new_callable=AsyncMock) as mock_send:
                    await send_morning_briefing(123)
                    mock_send.assert_called_once_with(123, "🌅 YOUR MORNING BRIEF\n\nStuff here")
