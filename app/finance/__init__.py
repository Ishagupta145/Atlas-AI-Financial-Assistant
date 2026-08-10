"""Finance package: market data, news, SEC clients, and research orchestrator.

This package provides async clients and normalization utilities used by
the research layer. Clients are designed to be testable and fail-safe.
"""

from .market_data import MarketDataClient
from .news import NewsClient
from .sec import SECClient
from .research import research_company

__all__ = [
    "MarketDataClient",
    "NewsClient",
    "SECClient",
    "research_company",
]
