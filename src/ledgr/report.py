from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ledgr.holdings import Holding
from ledgr.prices import (
    PriceFetchError,
    PriceQuote,
    UnresolvableTickerError,
    fetch_price,
)
from ledgr.xirr import XIRRError, xirr

CAD = "CAD"


@dataclass(frozen=True)
class TickerReport:
    ticker: str
    quantity: float
    cost_basis: float
    current_price: float | None
    current_value: float
    yield_pct: float | None
    yield_error: str | None


class CurrencyMismatchError(Exception):
    def __init__(self, ticker: str, currency: str) -> None:
        self.ticker = ticker
        self.currency = currency
        super().__init__(
            f"ticker {ticker!r} resolved to currency {currency!r}, expected CAD"
        )


class LedgerPriceError(Exception):
    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


def build_reports(
    holdings: dict[str, Holding], today: dt.date
) -> tuple[list[TickerReport], TickerReport]:
    quotes: dict[str, PriceQuote] = {}
    errors: list[Exception] = []
    for ticker, holding in holdings.items():
        if holding.quantity <= 0:
            continue
        try:
            quote = fetch_price(ticker)
        except (UnresolvableTickerError, PriceFetchError) as exc:
            errors.append(exc)
            continue
        if quote.currency != CAD:
            errors.append(CurrencyMismatchError(ticker, quote.currency))
            continue
        quotes[ticker] = quote

    if errors:
        raise LedgerPriceError(errors)

    reports: list[TickerReport] = []
    all_flows: list[tuple[dt.date, float]] = []
    total_current_value = 0.0
    for ticker in sorted(holdings):
        holding = holdings[ticker]
        flows = list(holding.cash_flows)
        current_price = None
        current_value = 0.0
        if holding.quantity > 0:
            quote = quotes[ticker]
            current_price = quote.price
            current_value = holding.quantity * quote.price
            flows.append((today, current_value))
            total_current_value += current_value
        all_flows.extend(holding.cash_flows)

        yield_pct: float | None = None
        yield_error: str | None = None
        try:
            yield_pct = xirr(flows) * 100
        except XIRRError as exc:
            yield_error = str(exc)

        reports.append(
            TickerReport(
                ticker=ticker,
                quantity=holding.quantity,
                cost_basis=holding.cost_basis,
                current_price=current_price,
                current_value=current_value,
                yield_pct=yield_pct,
                yield_error=yield_error,
            )
        )

    if total_current_value > 0:
        all_flows.append((today, total_current_value))
    total_yield: float | None = None
    total_yield_error: str | None = None
    try:
        total_yield = xirr(all_flows) * 100
    except XIRRError as exc:
        total_yield_error = str(exc)

    total = TickerReport(
        ticker="TOTAL",
        quantity=sum(r.quantity for r in reports),
        cost_basis=sum(r.cost_basis for r in reports),
        current_price=None,
        current_value=total_current_value,
        yield_pct=total_yield,
        yield_error=total_yield_error,
    )
    return reports, total
