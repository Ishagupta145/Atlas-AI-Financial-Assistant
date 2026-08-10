from __future__ import annotations

from typing import Any, Dict, Optional

from .market_data import MarketDataClient
from .news import NewsClient, FinnhubMarketClient
from .sec import SECClient
from .metadata import COMPANY_METADATA


def resolve_symbol(query: str) -> Optional[str]:
    """Resolve a company name or ticker to a ticker symbol.

    This is intentionally simple and modular so it can be replaced by a
    proper reference-data service later.
    """
    token = (query or "").strip()
    if not token:
        return None

    if token.isalpha() and len(token) <= 5:
        if token.upper() == token:
            return token.upper()
        return None

    lowered = token.lower()
    local_map = {
        "nvidia": "NVDA",
        "amd": "AMD",
        "microsoft": "MSFT",
        "tesla": "TSLA",
        "apple": "AAPL",
        "google": "GOOGL",
        "amazon": "AMZN",
        "meta": "META",
        "alphabet": "GOOGL",
        "facebook": "META",
    }

    if lowered in local_map:
        return local_map[lowered]

    for name, ticker in local_map.items():
        if name in lowered:
            return ticker

    return None


async def research_company(query: str, *, include_market: bool = True, include_news: bool = True, include_sec: bool = False) -> Dict[str, Any]:
    """Orchestrate research for a company with market data as the first real capability."""
    symbol = resolve_symbol(query)

    result = {"query": query, "symbol": symbol, "data": {}, "errors": {"market": None, "news": None, "sec": None}, "sources": []}

    md = MarketDataClient()
    fh = FinnhubMarketClient()
    nc = NewsClient()

    if include_market and symbol:
        try:
            market = await fh.get_quote(symbol)
            result["data"]["market"] = market
            result["sources"].append({"name": "Finnhub", "retrieved_at": market.get("retrieved_at")})
        except Exception as e:
            result["errors"]["market"] = str(e)

    if include_news and symbol:
        try:
            from datetime import date, timedelta

            to_date = date.today()
            from_date = to_date - timedelta(days=2)
            news_items = await nc.company_news(symbol, from_date.isoformat(), to_date.isoformat())
            
            relevant_news = []
            for item in news_items:
                rel_type, rel_score = score_article_relevance(item, symbol)
                if rel_type != "irrelevant":
                    item["relevance_type"] = rel_type
                    item["relevance_score"] = rel_score
                    relevant_news.append(item)
            
            relevant_news.sort(key=lambda x: (x.get("relevance_score") or 0, x.get("published_at") or 0), reverse=True)
            top_news = relevant_news[:5]
            
            result["data"]["news"] = top_news
            result["sources"].append({"name": "Finnhub", "count": len(top_news)})
        except Exception as e:
            result["errors"]["news"] = str(e)

    if include_sec and symbol:
        try:
            sc = SECClient()
            sec_items = await sc.recent_filings(symbol)
            result["data"]["sec"] = sec_items
            result["sources"].append({"name": "SEC EDGAR", "count": len(sec_items)})
        except Exception as e:
            result["errors"]["sec"] = str(e)

    return result


def score_article_relevance(article: Dict[str, Any], symbol: str) -> tuple[str, int]:
    """Score article relevance deterministically."""
    symbol = (symbol or "").upper()
    meta = COMPANY_METADATA.get(symbol, {})
    aliases = meta.get("aliases", [symbol.lower()])
    industry_terms = meta.get("industry_terms", [])
    
    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()
    content = f"{title} {summary}"
    
    for alias in aliases:
        if alias in content:
            return "direct", 10
            
    for term in industry_terms:
        if term in content:
            return "industry", 5
            
    return "irrelevant", 0


def determine_evidence_confidence(news_data: list) -> str:
    direct_count = sum(1 for item in news_data if item.get("relevance_type") == "direct")
    industry_count = sum(1 for item in news_data if item.get("relevance_type") == "industry")
    
    if direct_count > 1:
        return "high"
    elif direct_count == 1 or industry_count > 0:
        return "medium"
    return "low"


def analyze_market_movement(query: str, market_data: dict, news_data: list) -> str:
    """Format market and news data into structured evidence for the AI."""
    parts = []
    
    parts.append("MARKET:")
    parts.append(f"Symbol: {market_data.get('symbol')}")
    parts.append(f"Price: {market_data.get('price')}")
    parts.append(f"Change: {market_data.get('change')}")
    parts.append(f"Change %: {market_data.get('change_percent')}")
    parts.append(f"Timestamp: {market_data.get('timestamp')}")
    parts.append(f"Source: {market_data.get('source')}")
    parts.append("")
    
    parts.append("RECENT NEWS:")
    if not news_data:
        parts.append("No recent news available.")
    else:
        for i, item in enumerate(news_data, 1):
            parts.append(f"{i}. {item.get('title')}")
            parts.append(f"   Source: {item.get('source')}")
            parts.append(f"   Published time: {item.get('published_at')}")
            parts.append(f"   URL: {item.get('url')}")
            if item.get("summary"):
                parts.append(f"   Summary: {item.get('summary')}")
            parts.append("")

    direct_count = sum(1 for item in news_data if item.get("relevance_type") == "direct")
    industry_count = sum(1 for item in news_data if item.get("relevance_type") == "industry")
    confidence = determine_evidence_confidence(news_data)
    
    parts.append("NEWS EVIDENCE QUALITY:")
    parts.append(f"Direct company articles: {direct_count}")
    parts.append(f"Industry-context articles: {industry_count}")
    parts.append(f"Evidence confidence: {confidence}")
    parts.append("")

    return "\n".join(parts)
