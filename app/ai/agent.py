import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
import json
import re
from typing import List, Dict, Any
from google.genai import errors as genai_errors


load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


SYSTEM_PROMPT = """
You are Atlas, an AI Financial Chief of Staff.

Your job is to help finance professionals research companies,
understand financial information, and stay informed.

PERSONALITY:
- Professional
- Concise
- Conversational
- Analytical
- Evidence-driven
- Helpful without being verbose

CORE RESPONSE RULES:

1. BE VERY CONCISE

Telegram is the primary interface.

Default response limits:

Simple question:
2-4 sentences.

Concept explanation:
3-6 short paragraphs or bullets.

Company overview:
5-8 bullets maximum.

Company development/news:
3-6 key developments maximum.

Comparison:
Use a compact comparison with only the most important factors.

Never produce a long research report unless the user explicitly asks
for a detailed analysis, deep dive, report, or comprehensive research.

Put the most important conclusion first.

Do not repeat information already established in the conversation.

Do not end every response with "Would you like me to..." unless
there is a genuinely useful next step.

2. TELEGRAM-FRIENDLY FORMATTING

Your responses will be displayed directly inside Telegram.

DO NOT use:
- Markdown headings such as ###
- Markdown tables
- LaTeX
- $...$
- \(...\)
- Long mathematical formulas
- Excessive emojis

Use simple text instead.

For example:

REVENUE
Money a company earns from selling products or services.

PROFIT
Money remaining after expenses.

Example:
Revenue: ₹100 Cr
Expenses: ₹70 Cr
Profit: ₹30 Cr

WHY IT MATTERS
Revenue shows sales growth, while profit shows how efficiently
the company converts sales into earnings.

3. ANSWER THE USER'S ACTUAL QUESTION

Do not add unnecessary background information.

If the user asks a simple question, give a simple answer.

4. HANDLE AMBIGUOUS COMPANY QUESTIONS

If the user asks something broad such as:

"Tell me about Apple"
"Tell me about Microsoft"
"What about Tesla?"

and there is no clear context about what they want,
DO NOT generate a generic company report.

Ask a short clarification question.

Example:

"Apple can be looked at from a few angles. What are you interested in:
latest developments, financial performance, valuation, filings,
or an overall company analysis?"

However, if the user's request is already specific,
answer it directly.

For example:

"Why did Apple fall today?"
"Summarize Apple's latest earnings."
"Compare Apple and Microsoft."
"What are Apple's biggest risks?"

These should be answered directly.

5. FINANCIAL ACCURACY

Never fabricate:
- Stock prices
- Financial results
- Earnings
- SEC filings
- News
- Market movements
- Analyst ratings
- Company announcements

You currently do NOT have live financial data tools.

If a user asks for "latest", "today", "now", or other live developments,
do NOT invent events or provide speculative "recent developments".
Respond concisely that you do not have live data access and that
confirming recent developments requires retrieving live sources.
Offer to run a live research job only if the user connects the
required sources or explicitly permits background research; otherwise
decline to fabricate and suggest reliable alternatives (news sites,
company filings, or an option to connect live feeds).

6. DISTINGUISH FACT FROM INTERPRETATION

When discussing financial topics, clearly distinguish:
A. VERIFIED FACT (Directly supported by retrieved evidence)
B. REASONABLE INTERPRETATION (Conclusion reasonably drawn from evidence, but not directly established)
C. EXTERNAL/GENERAL KNOWLEDGE (Fact not present in retrieved evidence)
D. SPECULATION (Hypothesis requiring additional evidence)

FINANCIAL SAFETY RULE: Never present C or D as A.
Use phrases like:
- "Based on the evidence available..."
- "This is relevant to your thesis because..."
- "This may indicate..."
- "The evidence does not establish..."
- "One risk to monitor is..."

Avoid phrases like "This proves...", "This caused...", or "This guarantees..." unless the retrieved evidence explicitly supports that statement.

7. FINANCIAL ADVICE

You are a financial research assistant, not a financial advisor.

Do not give personalized buy/sell instructions.

You may explain financial information, risks, scenarios,
and factors investors commonly consider.

8. CONVERSATION

Remember that Atlas will eventually have access to user memory,
watchlists, documents, and financial tools.

Use available context when provided.

Do not ask users to repeat information that is already available.

9. RESPONSE LENGTH

Default:

Simple question → 2-5 sentences.

Concept explanation → short explanation + example.

Company research → concise structured summary.

Complex analysis → structured answer with the most important
points first.

Only provide long reports when explicitly requested.
"""


async def ask_atlas(
    user_message: str,
    conversation_history: list,
    user_memory: dict | None = None
) -> str:
    # Build conversation text
    conversation = []
    for role, message in conversation_history:
        if role == "user":
            conversation.append(f"USER: {message}")
        elif role == "assistant":
            conversation.append(f"ATLAS: {message}")

    conversation.append(f"USER: {user_message}")
    conversation_text = "\n".join(conversation)

    # Inject a short user memory summary if available
    memory_text = ""
    if user_memory:
        pairs = [f"{k}: {v}" for k, v in user_memory.items()]
        memory_text = "USER MEMORY:\n" + "\n".join(pairs) + "\n\n"

    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=memory_text + conversation_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )

        return response.text

    except genai_errors.ClientError as e:
        if getattr(e, 'status_code', None) == 429 or 'RESOURCE_EXHAUSTED' in str(e):
            raise RuntimeError('RATE_LIMIT') from e
        raise


async def ask_atlas_with_evidence(
    user_message: str,
    conversation_history: list,
    user_memory: dict | None = None,
    evidence: str | None = None,
) -> str:
    """Ask Atlas with optional verified market evidence attached."""
    if evidence:
        user_message = (
            f"{user_message}\n\n"
            f"Verified market evidence:\n{evidence}\n\n"
            "Use the evidence only; do not invent prices or values. Keep the answer concise and Telegram-friendly."
        )
    return await ask_atlas(user_message, conversation_history, user_memory)


async def ask_atlas_with_financial_evidence(
    user_message: str,
    conversation_history: list,
    user_memory: dict | None = None,
    evidence: str | None = None,
) -> str:
    """Ask Atlas to analyze a market movement using explicit financial evidence."""
    prompt = (
        "You are acting as a concise financial analyst.\n"
        "Analyze the market movement for the user's query based ONLY on the provided evidence.\n"
        "STRICT FINANCIAL LANGUAGE RULES:\n"
        "- A. VERIFIED FACT: State numbers and cited news directly (e.g., 'NVDA is up 2.27%').\n"
        "- B. REASONABLE INTERPRETATION: Use careful language (e.g., 'This may be contributing...', 'This provides context...').\n"
        "- NEVER present External Knowledge or Speculation as a Verified Fact.\n"
        "- UNSUPPORTED: NEVER say 'This caused the stock to rise' or 'This proves' unless the evidence explicitly establishes it.\n"
        "- If the Evidence confidence is 'low', you MUST say something similar to: 'NVDA is up [X]% today, but I couldn't find sufficiently strong company-specific news to confidently attribute the move to a particular event.' Do not invent an explanation.\n"
        "Keep responses concise and Telegram-friendly. Avoid long essays.\n"
        "Format with clear structure (e.g. price line, why it matters, sources).\n\n"
        f"USER REQUEST: {user_message}\n\n"
        f"FINANCIAL EVIDENCE:\n{evidence}\n"
    )
    return await ask_atlas(prompt, conversation_history, user_memory)


async def extract_user_memory(
    user_message: str,
    conversation_history: list
) -> dict:
    """Use Gemini to extract durable user memory from the latest
    user message and context. Returns a dict of memory_key -> value.
    """

    prompt = (
        "Extract any durable personal preferences or profile details from the "
        "latest message and the recent conversation. Return a JSON object "
        "mapping memory keys to values. Allowed keys: role, companies_followed, "
        "sectors, interests, research_preferences, notification_preferences. "
        "If nothing durable is present, return an empty JSON object {}. "
        "Keep values short. Only return a JSON object and nothing else.\n\n"
        "Examples:\n"
        "1) Message: \"I'm an investment analyst.\" -> {\"role\": \"investment analyst\"}\n"
        "2) Message: \"I mainly follow Nvidia, AMD and TSMC.\" -> {\"companies_followed\": \"Nvidia, AMD, TSMC\"}\n"
        "3) Message: \"I'm particularly interested in AI infrastructure.\" -> {\"interests\": \"AI infrastructure\"}\n"
    )

    convo = []
    for role, message in conversation_history:
        convo.append(f"{role.upper()}: {message}")
    convo.append(f"USER: {user_message}")

    contents = prompt + "\n\nCONVERSATION:\n" + "\n".join(convo)

    try:
        resp = await client.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.0,
            ),
        )

        text = resp.text.strip()

        # Try to locate a JSON object in the response
        m = re.search(r"\{[\s\S]*\}", text)
        json_text = m.group(0) if m else text

        data = json.loads(json_text)

    except genai_errors.ClientError:
        # If rate-limited or other client errors, degrade gracefully
        # but continue to deterministic fallback parsing
        data = {}
    except Exception:
        # On failure return empty dict — do not break conversation
        data = {}

    # Filter to allowed keys and normalize into structured types
    allowed = {
        "role",
        "companies_followed",
        "sectors",
        "interests",
        "research_preferences",
        "notification_preferences",
    }

    result: Dict[str, Any] = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        if k not in allowed:
            continue

        # Normalize lists and strings
        if isinstance(v, list):
            items = [str(x).strip() for x in v if str(x).strip()]
            if items:
                result[k] = items
        elif isinstance(v, str):
            s = v.strip()
            # If comma-separated, split
            if "," in s or " and " in s:
                parts = re.split(r",| and |;|\n", s)
                items = [p.strip() for p in parts if p.strip()]
                if items:
                    result[k] = items
            else:
                # single value
                if s:
                    if k == "role":
                        result[k] = s
                    else:
                        result[k] = [s]
        else:
            # Other types — coerce to string
            result[k] = [str(v)]

    # Deterministic fallback parsing for obvious patterns
    # companies
    if "companies_followed" not in result:
        companies = parse_companies_from_text(user_message)
        if not companies:
            # Also scan conversation history for explicit follow patterns
            for _, msg in reversed(conversation_history[-3:]):
                companies = parse_companies_from_text(msg)
                if companies:
                    break
        if companies:
            result["companies_followed"] = companies

    # interests
    if "interests" not in result:
        interests = parse_interests_from_text(user_message)
        if not interests:
            for _, msg in reversed(conversation_history[-3:]):
                interests = parse_interests_from_text(msg)
                if interests:
                    break
        if interests:
            result["interests"] = interests

    # role fallback
    if "role" not in result:
        role = parse_role_from_text(user_message)
        if role:
            result["role"] = role

    # Final filter: remove empty entries
    final = {k: v for k, v in result.items() if v}
    return final


def parse_companies_from_text(text: str) -> List[str]:
    t = text
    # Common phrases
    m = re.search(r"(?:follow|following)\s+(.*)", t, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"I mainly follow\s+(.*)", t, flags=re.IGNORECASE)
    if m:
        tail = m.group(1)
        # stop at punctuation
        tail = re.split(r"[\.\?!]", tail)[0]
        parts = re.split(r",| and |;|/", tail)
        items = []
        for p in parts:
            p = p.strip()
            # heuristic: companies usually capitalized words or contain known chars
            if not p:
                continue
            # remove leading words like 'the' or 'also'
            p = re.sub(r"^(the|also)\s+", "", p, flags=re.IGNORECASE)
            # discard obvious non-company fragments
            if re.search(r"\b(interest|interested|but|however|also|i'm|i am)\b", p, flags=re.IGNORECASE):
                continue
            items.append(p)
        # dedupe preserving order
        seen = set()
        out = []
        for it in items:
            if it.lower() not in seen:
                seen.add(it.lower())
                out.append(it)
        return out
    return []


def parse_interests_from_text(text: str) -> List[str]:
    # look for 'interested in' patterns
    m = re.search(r"interested in\s+(.*)", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"interests? are\s+(.*)", text, flags=re.IGNORECASE)
    if m:
        tail = m.group(1)
        tail = re.split(r"[\.\?!]", tail)[0]
        parts = re.split(r",| and |;|/", tail)
        items = [p.strip() for p in parts if p.strip()]
        # dedupe
        seen = set()
        out = []
        for it in items:
            if it.lower() not in seen:
                seen.add(it.lower())
                out.append(it)
        return out
    return []


def parse_role_from_text(text: str) -> str:
    # simple patterns: I'm an X / I am a X
    m = re.search(r"I(?:'| a)m\s+(an?\s+[^\.]+)", text, flags=re.IGNORECASE)
    if m:
        role = m.group(1).strip()
        # stop at comma
        return role
    return ""


async def generate_morning_briefing(
    user_memory: dict,
    research_data: list[dict],
) -> str:
    """Generate a personalized morning briefing based on watched companies.
    Returns NO_IMPORTANT_NEWS if nothing passes the threshold.
    """
    
    evidence_parts = []
    for item in research_data:
        sym = item.get("symbol")
        evidence_parts.append(f"COMPANY: {sym}")
        
        market = item.get("data", {}).get("market")
        if market:
            evidence_parts.append(f"Price: {market.get('price')} | Change: {market.get('change_percent')}%")
            
        news = item.get("data", {}).get("news", [])
        if news:
            evidence_parts.append("News:")
            for n in news:
                evidence_parts.append(f"- {n.get('title')} (Score: {n.get('relevance_score')})")
        evidence_parts.append("")
        
    evidence_text = "\n".join(evidence_parts)
    
    memory_text = "\n".join([f"{k}: {v}" for k, v in user_memory.items()])
    
    prompt = (
        "You are Atlas, a concise financial analyst generating a morning brief.\n"
        "You must evaluate the provided recent developments for the user's watched companies.\n"
        "STRICT IMPORTANCE THRESHOLD:\n"
        "Only include developments that are significant (major announcements, earnings, M&A, regulatory, large price moves).\n"
        "If NOTHING passes this threshold across all companies, you MUST output exactly: NO_IMPORTANT_NEWS\n\n"
        "If there are important developments, generate a brief in this exact format:\n"
        "🌅 YOUR MORNING BRIEF\n\n"
        "Good morning. [X] things worth your attention:\n\n"
        "🔴 [COMPANY NAME]\n"
        "[Price move if notable, e.g. +4.2%]\n"
        "[1-sentence summary of the verified development]\n"
        "Why it matters: [1-sentence concise interpretation]\n\n"
        "...repeat for other significant companies...\n\n"
        "Nothing else on your watchlist appears significant this morning.\n\n"
        "RULES:\n"
        "- Do not invent facts or numbers.\n"
        "- Never claim causation without explicit evidence.\n"
        "- Keep it extremely concise.\n\n"
        f"USER PROFILE:\n{memory_text}\n\n"
        f"DEVELOPMENTS:\n{evidence_text}\n"
    )
    
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return response.text.strip()
    except Exception:
        return "NO_IMPORTANT_NEWS"