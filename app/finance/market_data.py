from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY")
# Use real Massive base by default but allow override via env
MASSIVE_BASE_URL = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com")

_UNSET = object()


class MarketDataClient:
    """Client for fetching market data from MASSIVE.

    The client reads its configuration from the environment and keeps the
    normalization logic strict: if a field is absent in the API payload it is
    returned as None rather than fabricated.
    """

    def __init__(self, api_key: Any = _UNSET, base_url: Optional[str] = None):
        self.api_key = api_key if api_key is not _UNSET else (os.getenv("MASSIVE_API_KEY") or MASSIVE_API_KEY)
        self.base_url = base_url or os.getenv("MASSIVE_BASE_URL") or MASSIVE_BASE_URL
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch the latest quote for a symbol and return a normalized structure."""
        if not self.api_key:
            raise RuntimeError("MASSIVE_API_KEY is not configured")

        sym = (symbol or "").strip().upper()
        if not sym:
            raise RuntimeError("Symbol is required")

        base = (self.base_url or "https://api.massive.com").rstrip("/")
        path = f"{base}/v2/snapshot/locale/us/markets/stocks/tickers/{sym}"
        params = {"apiKey": self.api_key}

        backoff = 1.0
        last_error: Optional[Exception] = None
        rate_limited = False

        for attempt in range(3):
            try:
                resp = await self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

            if resp.status_code == 401:
                raise RuntimeError("Massive authentication/configuration problem (401)")
            if resp.status_code == 403:
                raise RuntimeError("Massive permission/plan problem (403)")
            if resp.status_code == 404:
                raise RuntimeError(f"Massive endpoint or symbol problem (404) for {sym}")
            if resp.status_code == 429:
                rate_limited = True
                await self._sleep(backoff)
                backoff *= 2
                continue

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                continue

            try:
                data = resp.json()
            except Exception as exc:
                raise RuntimeError("Massive response was not valid JSON") from exc

            payload = self._extract_payload(data)
            return self._normalize_quote(sym, payload)

        if rate_limited:
            raise RuntimeError("Massive rate limited (429)")

        if last_error is not None:
            if isinstance(last_error, httpx.TimeoutException):
                raise last_error
            raise RuntimeError(f"Massive request failed: {last_error}") from last_error

        raise RuntimeError(f"Massive endpoint or symbol problem (404) for {sym}")

    def _extract_payload(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            ticker = raw.get("ticker")
            if isinstance(ticker, dict):
                return ticker
            for key in ("data", "result", "results", "quote", "stock", "payload", "market"):
                value = raw.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
            return raw
        return {}

    def _normalize_quote(self, symbol: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        raw = raw or {}
        day = raw.get("day") if isinstance(raw.get("day"), dict) else {}
        prev_day = raw.get("prevDay") if isinstance(raw.get("prevDay"), dict) else {}
        last_trade = raw.get("lastTrade") if isinstance(raw.get("lastTrade"), dict) else {}
        last_quote = raw.get("lastQuote") if isinstance(raw.get("lastQuote"), dict) else {}

        price = None
        timestamp = raw.get("updated")
        if last_trade.get("price") is not None:
            price = last_trade.get("price")
            timestamp = last_trade.get("timestamp") if last_trade.get("timestamp") is not None else timestamp
        elif last_quote.get("price") is not None:
            price = last_quote.get("price")
            timestamp = last_quote.get("timestamp") if last_quote.get("timestamp") is not None else timestamp
        elif day.get("c") is not None:
            price = day.get("c")
        elif raw.get("price") is not None:
            price = raw.get("price")
        elif raw.get("last") is not None:
            price = raw.get("last")

        if timestamp is None and last_quote.get("timestamp") is not None:
            timestamp = last_quote.get("timestamp")
        if timestamp is None and last_trade.get("timestamp") is not None:
            timestamp = last_trade.get("timestamp")

        prev = prev_day.get("c") if prev_day.get("c") is not None else raw.get("previous_close")
        change = raw.get("todaysChange")
        pct = raw.get("todaysChangePerc")
        open_price = day.get("o") if day.get("o") is not None else raw.get("open")
        high = day.get("h") if day.get("h") is not None else raw.get("high")
        low = day.get("l") if day.get("l") is not None else raw.get("low")
        volume = day.get("v") if day.get("v") is not None else raw.get("volume")

        normalized = {
            "symbol": (raw.get("ticker") or symbol).upper() if isinstance(raw.get("ticker"), str) else symbol.upper(),
            "company": raw.get("company") or raw.get("name"),
            "price": price,
            "previous_close": prev,
            "change": change,
            "change_percent": pct,
            "open": open_price,
            "high": high,
            "low": low,
            "volume": volume,
            "timestamp": timestamp,
            "source": "Massive",
            "retrieved_at": int(time.time()),
        }

        return normalized

    async def _sleep(self, s: float):
        import asyncio

        await asyncio.sleep(s)
