import pytest
from unittest.mock import patch, AsyncMock
from app.ai.agent import ask_atlas_with_financial_evidence, ask_atlas

@pytest.mark.asyncio
async def test_financial_reasoning_guardrails():
    # Test that ask_atlas_with_financial_evidence passes the correct prompt to ask_atlas
    # which includes the strict financial language rules.
    with patch("app.ai.agent.ask_atlas", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = "Response"
        
        evidence = "NVDA price: 100. News: Nvidia releases new chip."
        await ask_atlas_with_financial_evidence(
            user_message="Why is Nvidia moving?",
            conversation_history=[],
            user_memory={"role": "Analyst"},
            evidence=evidence
        )
        
        mock_ask.assert_called_once()
        args, _ = mock_ask.call_args
        prompt = args[0]
        
        assert "STRICT FINANCIAL LANGUAGE RULES" in prompt
        assert "A. VERIFIED FACT" in prompt
        assert "B. REASONABLE INTERPRETATION" in prompt
        assert "NEVER present External Knowledge or Speculation as a Verified Fact" in prompt
        assert "NEVER say 'This caused the stock to rise' or 'This proves'" in prompt

@pytest.mark.asyncio
async def test_ask_atlas_system_prompt_guardrails():
    # Test that the SYSTEM_PROMPT contains the required guardrails
    from app.ai.agent import SYSTEM_PROMPT
    
    assert "A. VERIFIED FACT" in SYSTEM_PROMPT
    assert "B. REASONABLE INTERPRETATION" in SYSTEM_PROMPT
    assert "C. EXTERNAL/GENERAL KNOWLEDGE" in SYSTEM_PROMPT
    assert "D. SPECULATION" in SYSTEM_PROMPT
    assert "FINANCIAL SAFETY RULE: Never present C or D as A" in SYSTEM_PROMPT
    assert "Avoid phrases like \"This proves...\"" in SYSTEM_PROMPT

