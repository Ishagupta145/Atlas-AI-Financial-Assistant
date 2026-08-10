import asyncio
from app.finance.research import research_company, analyze_market_movement
from app.ai.agent import ask_atlas_with_financial_evidence
from app.finance.news import NewsClient
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    # Run the query
    res = await research_company("Nvidia", include_market=True, include_news=True, include_sec=False)
    
    # We need to know the raw count. Since research_company doesn't return raw count, 
    # we'll fetch it manually just for this logging requirement if needed.
    # Actually, the user asked for `raw_news_count`. `research_company` returns `result["sources"][...]["count"]` but this is the filtered count now.
    # I can just quickly fetch the raw count to print it, or infer it if possible. Let's just do a manual fetch to get raw_count.
    from datetime import date, timedelta
    nc = NewsClient()
    to_date = date.today()
    from_date = to_date - timedelta(days=2)
    raw_news = await nc.company_news("NVDA", from_date.isoformat(), to_date.isoformat())
    raw_count = len(raw_news)
    
    symbol = res.get("symbol")
    market_data = res.get("data", {}).get("market") or {}
    news_data = res.get("data", {}).get("news") or []
    
    price = market_data.get("price")
    change_percent = market_data.get("change_percent")
    
    relevant_count = len(news_data)
    
    print(f"symbol: {symbol}")
    print(f"price: {price}")
    print(f"change_percent: {change_percent}")
    print(f"raw_news_count: {raw_count}")
    print(f"relevant_news_count: {relevant_count}")
    
    for article in news_data:
        print(f"relevance_type: {article.get('relevance_type')}")
        print(f"relevance_score: {article.get('relevance_score')}")
        print(f"title: {article.get('title')}")
        print(f"source: {article.get('source')}")
        print("---")
        
    evidence = analyze_market_movement("Why is Nvidia moving?", market_data, news_data)
    
    # Generate Atlas explanation
    explanation = await ask_atlas_with_financial_evidence("Why is Nvidia moving?", [], {}, evidence=evidence)
    
    print("\nATLAS EXPLANATION:\n")
    print(explanation)

if __name__ == "__main__":
    asyncio.run(main())
