from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ledgr.ledger import Transaction

# Realistic brokerage-statement transcription drift on fractional-share quantities
# (4-6 decimal places is typical) is several orders of magnitude looser than a
# numerical root-finder's convergence tolerance — these are different domains and
# must not share a constant.
QUANTITY_EPSILON = 1e-6


@dataclass
class Holding:
    ticker: str
    quantity: float
    cost_basis: float
    cash_flows: list[tuple[dt.date, float]] = field(default_factory=list)


class OversellError(Exception):
    def __init__(self, ticker: str, line_no: int, oversell_amount: float) -> None:
        self.ticker = ticker
        self.line_no = line_no
        self.oversell_amount = oversell_amount
        super().__init__(f"line {line_no}: sell of {ticker} exceeds quantity held by {oversell_amount}")


class LedgerOversellError(Exception):
    def __init__(self, errors: list[OversellError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


def build_holdings(transactions: list[Transaction]) -> dict[str, Holding]:
    by_ticker: dict[str, list[Transaction]] = {}
    for t in transactions:
        by_ticker.setdefault(t.ticker, []).append(t)

    holdings: dict[str, Holding] = {}
    errors: list[OversellError] = []
    for ticker, txns in by_ticker.items():
        quantity = 0.0
        cost_basis = 0.0
        cash_flows: list[tuple[dt.date, float]] = []
        for t in txns:
            if t.verb == "buy":
                quantity += t.quantity
                cost_basis += t.quantity * t.price
                cash_flows.append((t.date, -t.quantity * t.price))
            else:
                if t.quantity > quantity + QUANTITY_EPSILON:
                    errors.append(OversellError(ticker, t.line_no, t.quantity - quantity))
                    continue
                avg_cost = cost_basis / quantity if quantity > QUANTITY_EPSILON else 0.0
                cost_basis -= avg_cost * t.quantity
                quantity -= t.quantity
                cash_flows.append((t.date, t.quantity * t.price))
        if quantity < QUANTITY_EPSILON:
            quantity = 0.0
            cost_basis = 0.0
        holdings[ticker] = Holding(ticker=ticker, quantity=quantity, cost_basis=cost_basis, cash_flows=cash_flows)

    if errors:
        raise LedgerOversellError(errors)
    return holdings
