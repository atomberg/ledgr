from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

VALID_VERBS = {"buy", "sell"}


@dataclass(frozen=True)
class Transaction:
    line_no: int
    verb: str
    ticker: str
    quantity: float
    price: float
    date: dt.date


class LedgerParseError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def parse_line(line_no: int, raw: str, today: dt.date) -> Transaction:
    parts = raw.split()
    if len(parts) != 7 or parts[3] != "@" or parts[5] != "on":
        raise ValueError(f"line {line_no}: malformed line: {raw!r}")
    verb, ticker, quantity_str, _, price_str, _, date_str = parts
    if verb not in VALID_VERBS:
        raise ValueError(f"line {line_no}: unrecognized verb {verb!r}")
    try:
        quantity = float(quantity_str)
    except ValueError:
        raise ValueError(f"line {line_no}: invalid quantity {quantity_str!r}") from None
    if quantity <= 0:
        raise ValueError(f"line {line_no}: quantity must be positive, got {quantity}")
    try:
        price = float(price_str)
    except ValueError:
        raise ValueError(f"line {line_no}: invalid price {price_str!r}") from None
    if price <= 0:
        raise ValueError(f"line {line_no}: price must be positive, got {price}")
    try:
        date = dt.date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"line {line_no}: invalid date {date_str!r}, expected YYYY-MM-DD") from None
    if date > today:
        raise ValueError(f"line {line_no}: date {date} is in the future")
    return Transaction(line_no=line_no, verb=verb, ticker=ticker, quantity=quantity, price=price, date=date)


def parse_ledger(text: str, today: dt.date) -> list[Transaction]:
    transactions: list[Transaction] = []
    errors: list[str] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            transactions.append(parse_line(line_no, stripped, today))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise LedgerParseError(errors)
    if not transactions:
        raise ValueError("no transactions found in ledger")
    transactions.sort(key=lambda t: t.date)
    return transactions
