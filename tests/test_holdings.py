import datetime as dt

import pytest

from ledgr.holdings import LedgerOversellError, build_holdings
from ledgr.ledger import Transaction


def _txn(line_no, verb, ticker, qty, price, date):
    return Transaction(line_no=line_no, verb=verb, ticker=ticker, quantity=qty, price=price, date=dt.date.fromisoformat(date))


def test_average_cost_basis_reduces_proportionally_on_sell():
    txns = [
        _txn(1, "buy", "XEQT.TO", 10, 28.40, "2023-03-01"),
        _txn(2, "buy", "XEQT.TO", 5, 31.10, "2024-01-15"),
        _txn(3, "sell", "XEQT.TO", 6, 33.00, "2024-09-01"),
    ]
    holdings = build_holdings(txns)
    h = holdings["XEQT.TO"]
    # pooled cost = 10*28.40 + 5*31.10 = 439.50 over 15 units -> 29.30/unit
    # sell 6 units removes 6*29.30 = 175.80 of cost
    assert h.quantity == pytest.approx(9.0)
    assert h.cost_basis == pytest.approx(439.50 - 175.80)
    assert h.cash_flows == [
        (dt.date(2023, 3, 1), -284.0),
        (dt.date(2024, 1, 15), -155.5),
        (dt.date(2024, 9, 1), 198.0),
    ]


def test_fully_sold_ticker_has_zero_quantity_and_cost_basis():
    txns = [
        _txn(1, "buy", "VAB.TO", 20, 25.75, "2023-06-10"),
        _txn(2, "sell", "VAB.TO", 20, 27.00, "2024-01-01"),
    ]
    holdings = build_holdings(txns)
    h = holdings["VAB.TO"]
    assert h.quantity == 0.0
    assert h.cost_basis == pytest.approx(0.0)


def test_multiple_tickers_tracked_independently():
    txns = [
        _txn(1, "buy", "XEQT.TO", 10, 28.40, "2023-03-01"),
        _txn(2, "buy", "VAB.TO", 20, 25.75, "2023-06-10"),
    ]
    holdings = build_holdings(txns)
    assert set(holdings) == {"XEQT.TO", "VAB.TO"}


def test_oversell_is_a_fatal_batched_error():
    txns = [
        _txn(1, "buy", "XEQT.TO", 10, 28.40, "2023-03-01"),
        _txn(2, "sell", "XEQT.TO", 15, 33.00, "2024-09-01"),
        _txn(3, "buy", "VAB.TO", 5, 25.75, "2023-06-10"),
        _txn(4, "sell", "VAB.TO", 8, 27.00, "2024-01-01"),
    ]
    with pytest.raises(LedgerOversellError) as exc_info:
        build_holdings(txns)
    errors = exc_info.value.errors
    assert len(errors) == 2
    assert errors[0].ticker == "XEQT.TO"
    assert errors[0].line_no == 2
    assert errors[0].oversell_amount == pytest.approx(5.0)
    assert errors[1].ticker == "VAB.TO"
    assert errors[1].oversell_amount == pytest.approx(3.0)


def test_full_sell_within_quantity_epsilon_of_held_amount_succeeds():
    # Simulates realistic brokerage-statement transcription drift (~5e-7) on a
    # full-sell, well inside QUANTITY_EPSILON but far outside a numerical-precision
    # tolerance. Must NOT raise OversellError.
    txns = [
        _txn(1, "buy", "VAB.TO", 20.8472909, 25.75, "2023-06-10"),
        _txn(2, "sell", "VAB.TO", 20.8472914, 27.00, "2026-06-20"),  # off by 5e-7
    ]
    holdings = build_holdings(txns)
    assert holdings["VAB.TO"].quantity == 0.0
