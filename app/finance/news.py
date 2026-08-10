from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

FINNHUB_BASE = os.getenv("FINNHUB_BASE", "https://finnhub.io/api/v1")


class FinnhubMarketClient:
    """Client for fetching market quotes from Finnhub."""

    def __init__(self, api_key: Optional[str] = None, base: Optional[str] = None):
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self.base = base or FINNHUB_BASE
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is not configured")

        sym = (symbol or "").strip().upper()
        if not sym:
            raise RuntimeError("Symbol is required")

        url = f"{self.base}/quote"
        params = {"symbol": sym, "token": self.api_key}

        try:
            resp = await self._client.get(url, params=params)
        except httpx.TimeoutException:
            raise
        except httpx.NetworkError as exc:
            raise RuntimeError("Finnhub network request failed") from exc
        except Exception as exc:
            raise RuntimeError("Finnhub request failed") from exc

        if resp.status_code == 401:
            raise RuntimeError("Finnhub authentication failed (401)")
        if resp.status_code == 403:
            raise RuntimeError("Finnhub permission denied (403)")
        if resp.status_code == 429:
            raise RuntimeError("Finnhub rate limited (429)")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Finnhub request failed: {exc}") from exc

        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError("Finnhub response was malformed") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Finnhub response was malformed")

        price = payload.get("c")
        prev_close = payload.get("pc")
        change = payload.get("d")
        change_pct = payload.get("dp")
        open_price = payload.get("o")
        high = payload.get("h")
        low = payload.get("l")
        volume = payload.get("v")
        timestamp = payload.get("t")

        if price is None and prev_close is None and change is None and change_pct is None and open_price is None and high is None and low is None:
            raise RuntimeError("Finnhub quote contained no usable data")

        return {
            "symbol": sym,
            "company": None,
            "price": price,
            "previous_close": prev_close,
            "change": change,
            "change_percent": change_pct,
            "open": open_price,
            "high": high,
            "low": low,
            "volume": volume,
            "timestamp": timestamp,
            "source": "Finnhub",
            "retrieved_at": int(time.time()),
        }


class NewsClient:
    """Client for fetching company news from Finnhub."""

    def __init__(self, api_key: Optional[str] = None, base: Optional[str] = None):
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self.base = base or FINNHUB_BASE
        self._client = httpx.AsyncClient(timeout=10.0)

    async def company_news(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is not configured")

        url = f"{self.base}/company-news"
        params = {"symbol": symbol, "from": start_date, "to": end_date, "token": self.api_key}

        try:
            resp = await self._client.get(url, params=params)
        except httpx.TimeoutException:
            raise RuntimeError("Finnhub network request failed (timeout)")
        except httpx.NetworkError as exc:
            raise RuntimeError("Finnhub network request failed") from exc
        except Exception as exc:
            raise RuntimeError("Finnhub request failed") from exc

        if resp.status_code == 401:
            raise RuntimeError("Finnhub authentication failed (401)")
        if resp.status_code == 403:
            raise RuntimeError("Finnhub permission denied (403)")
        if resp.status_code == 429:
            raise RuntimeError("Finnhub rate limited (429)")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Finnhub request failed: {exc}") from exc

        try:
            items = resp.json()
        except Exception as exc:
            raise RuntimeError("Finnhub response was malformed") from exc

        if not isinstance(items, list):
            raise RuntimeError("Finnhub response was malformed")

        return [self._normalize(i) for i in items]

    def _normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": raw.get("headline") or raw.get("title"),
            "source": raw.get("source"),
            "published_at": raw.get("datetime") or raw.get("published_at"),
            "url": raw.get("url"),
            "summary": raw.get("summary") or raw.get("description"),
            "retrieved_at": int(time.time()),
        }
