from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

SEC_BASE = "https://data.sec.gov"
# Require SEC_USER_AGENT to be provided via environment variable for production contact info.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")

# In-memory cache for ticker -> CIK mapping for the lifetime of the process
_TICKER_TO_CIK: dict = {}


class SECError(Exception):
    pass


class SECConfigError(SECError):
    pass


class SECNotFoundError(SECError):
    pass


class SECRateLimitError(SECError):
    pass


class SECRequestError(SECError):
    pass


class SECClient:
    """Client for querying SEC EDGAR public endpoints.

    The client requires `SEC_USER_AGENT` to be set in the environment and
    will use that value as the HTTP `User-Agent` header for all requests.
    """

    def __init__(self, base: Optional[str] = None, user_agent: Optional[str] = None):
        self.base = base or SEC_BASE
        self.user_agent = user_agent or SEC_USER_AGENT
        if not self.user_agent:
            # Do not allow silent default; require explicit SEC_USER_AGENT
            raise SECConfigError("SEC_USER_AGENT is not configured. Set SEC_USER_AGENT in environment.")
        self._client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": self.user_agent})

    async def _ensure_ticker_map(self) -> None:
        """Populate the in-memory ticker->CIK mapping if not already present."""
        global _TICKER_TO_CIK
        if _TICKER_TO_CIK:
            return

        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 429:
                raise SECRateLimitError("SEC rate limited while fetching ticker map")
            resp.raise_for_status()
            data = resp.json()
            # Data historically is a dict mapping numeric keys to entries with
            # 'cik_str', 'ticker', 'title'. Normalize to ticker->cik(10-digit)
            mapping = {}
            if isinstance(data, dict):
                for _, entry in data.items():
                    ticker = entry.get("ticker")
                    cik = entry.get("cik_str")
                    if ticker and cik:
                        mapping[ticker.upper()] = cik.zfill(10)
            _TICKER_TO_CIK = mapping
        except SECRateLimitError:
            raise
        except Exception as e:
            raise SECRequestError(f"Failed to fetch SEC ticker map: {e}") from e

    async def resolve_ticker_to_cik(self, token: str) -> str:
        """Resolve a given ticker symbol or CIK-like token to a 10-digit CIK string.

        If `token` already appears to be a 10-digit CIK (all digits), it is
        returned as-is (zero-padded). Otherwise perform a ticker lookup.
        """
        # If looks like a 10-digit CIK already, accept it
        if token.isdigit() and len(token) == 10:
            return token

        await self._ensure_ticker_map()
        ticker = token.strip().upper()
        cik = _TICKER_TO_CIK.get(ticker)
        if cik:
            return cik
        raise SECNotFoundError(f"Ticker or company not found: {token}")

    async def recent_filings(self, cik_or_ticker: str, count: int = 5) -> List[Dict[str, Any]]:
        """Return recent filings for a ticker or CIK.

        On success returns a list of normalized filing dicts. On known failure
        raises SEC* exceptions (SECNotFoundError, SECRateLimitError, SECRequestError).
        """
        try:
            if cik_or_ticker.isdigit() and len(cik_or_ticker) == 10:
                cik = cik_or_ticker
            else:
                cik = await self.resolve_ticker_to_cik(cik_or_ticker)

            url = f"{self.base}/submissions/CIK{cik}.json"
            resp = await self._client.get(url)
            if resp.status_code == 404:
                raise SECNotFoundError(f"No submissions found for CIK {cik}")
            if resp.status_code == 429:
                raise SECRateLimitError("SEC rate limited when fetching submissions")
            resp.raise_for_status()
            data = resp.json()
            filings = data.get("filings", {}).get("recent", {})
            results = []
            accession_list = filings.get("accessionNumber", []) or []
            forms = filings.get("form", []) or []
            filing_dates = filings.get("filingDate", []) or []
            report_types = filings.get("reportType", []) or []
            for i in range(min(count, len(accession_list))):
                results.append({
                    "company": data.get("name"),
                    "form": forms[i] if i < len(forms) else None,
                    "filing_date": filing_dates[i] if i < len(filing_dates) else None,
                    "accession_number": accession_list[i],
                    "description": report_types[i] if i < len(report_types) else None,
                    "url": f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{int(cik)}/{accession_list[i].replace('-', '')}/{accession_list[i]}.txt",
                    "source": "SEC EDGAR",
                    "retrieved_at": int(time.time()),
                })

            return results
        except SECError:
            raise
        except Exception as e:
            raise SECRequestError(f"Unexpected SEC error: {e}") from e
