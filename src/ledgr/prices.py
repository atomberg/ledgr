from __future__ import annotations

import time
from dataclasses import dataclass

import requests

YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
RETRY_COUNT = 1
RETRY_BACKOFF_SECONDS = 0.5


@dataclass(frozen=True)
class PriceQuote:
    ticker: str
    price: float
    currency: str


class UnresolvableTickerError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"ticker {ticker!r} could not be resolved")


class PriceFetchError(Exception):
    def __init__(self, ticker: str, detail: str) -> None:
        self.ticker = ticker
        super().__init__(f"no data returned after retry for {ticker!r}: {detail}")


def fetch_price(ticker: str, session: requests.Session | None = None) -> PriceQuote:
    sess = session or requests.Session()
    last_detail = ""
    for attempt in range(RETRY_COUNT + 1):
        try:
            resp = sess.get(
                YAHOO_CHART_URL.format(ticker=ticker),
                headers={"User-Agent": "Mozilla/5.0"},
                params={"range": "5d", "interval": "1d"},
                timeout=10,
            )
        except requests.RequestException as exc:
            last_detail = f"request failed: {exc}"
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise PriceFetchError(ticker, last_detail) from exc

        if resp.status_code == 404:
            raise UnresolvableTickerError(ticker)

        if resp.status_code != 200:
            # 429 (rate-limited) and 5xx responses can carry an error-shaped JSON
            # body identical to a genuine "ticker not found" response. Status code
            # is the only reliable signal that this is transient, not permanent --
            # a non-200, non-404 status is always retry-eligible.
            last_detail = f"unexpected status {resp.status_code}"
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise PriceFetchError(ticker, last_detail)

        try:
            data = resp.json()
            chart = data["chart"]
            if chart.get("error"):
                raise UnresolvableTickerError(ticker)
            meta = chart["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            currency = meta["currency"]
            if price is None or currency is None:
                raise KeyError("missing price or currency in response")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            last_detail = f"malformed response: {exc}"
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise PriceFetchError(ticker, last_detail) from exc

        return PriceQuote(ticker=ticker, price=float(price), currency=currency)

    raise PriceFetchError(ticker, last_detail)
