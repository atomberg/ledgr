import datetime as dt
from unittest.mock import patch

import pytest

from ledgr.holdings import Holding
from ledgr.prices import PriceQuote, UnresolvableTickerError
from ledgr.report import LedgerPriceError, build_reports

TODAY = dt.date(2026, 6, 23)


def _quote_map(quotes):
    def fake_fetch(ticker, session=None):
        return quotes[ticker]

    return fake_fetch


def test_build_reports_for_two_holdings_plus_total():
    holdings = {
        "XEQT.TO": Holding(
            ticker="XEQT.TO",
            quantity=9.0,
            cost_basis=263.70,
            cash_flows=[
                (dt.date(2023, 3, 1), -284.0),
                (dt.date(2024, 1, 15), -155.5),
                (dt.date(2024, 9, 1), 198.0),
            ],
        ),
        "VAB.TO": Holding(
            ticker="VAB.TO",
            quantity=20.0,
            cost_basis=515.0,
            cash_flows=[(dt.date(2023, 6, 10), -515.0)],
        ),
    }
    quotes = {
        "XEQT.TO": PriceQuote(ticker="XEQT.TO", price=33.0, currency="CAD"),
        "VAB.TO": PriceQuote(ticker="VAB.TO", price=24.0, currency="CAD"),
    }
    with patch("ledgr.report.fetch_price", side_effect=_quote_map(quotes)):
        reports, total = build_reports(holdings, TODAY)

    by_ticker = {r.ticker: r for r in reports}
    assert by_ticker["XEQT.TO"].current_value == pytest.approx(9.0 * 33.0)
    assert by_ticker["VAB.TO"].current_value == pytest.approx(20.0 * 24.0)
    assert total.ticker == "TOTAL"
    assert total.cost_basis == pytest.approx(263.70 + 515.0)
    assert total.current_value == pytest.approx(9.0 * 33.0 + 20.0 * 24.0)
    assert total.yield_pct is not None


def test_fully_sold_ticker_skips_price_fetch_and_keeps_realized_yield():
    holdings = {
        "VAB.TO": Holding(
            ticker="VAB.TO",
            quantity=0.0,
            cost_basis=0.0,
            cash_flows=[(dt.date(2023, 6, 10), -515.0), (dt.date(2024, 6, 10), 600.0)],
        )
    }
    with patch("ledgr.report.fetch_price") as mock_fetch:
        reports, total = build_reports(holdings, TODAY)
    mock_fetch.assert_not_called()
    r = reports[0]
    assert r.quantity == 0.0
    assert r.current_value == 0.0
    assert r.yield_pct is not None


def test_currency_mismatch_and_unresolvable_ticker_errors_are_batched():
    holdings = {
        "VOO": Holding(
            ticker="VOO",
            quantity=15.0,
            cost_basis=6000.0,
            cash_flows=[(dt.date(2024, 11, 3), -6000.0)],
        ),
        "ZZZZ": Holding(
            ticker="ZZZZ",
            quantity=5.0,
            cost_basis=100.0,
            cash_flows=[(dt.date(2024, 1, 1), -100.0)],
        ),
    }

    def fake_fetch(ticker, session=None):
        if ticker == "VOO":
            return PriceQuote(ticker="VOO", price=676.34, currency="USD")
        raise UnresolvableTickerError(ticker)

    with patch("ledgr.report.fetch_price", side_effect=fake_fetch):
        with pytest.raises(LedgerPriceError) as exc_info:
            build_reports(holdings, TODAY)
    messages = [str(e) for e in exc_info.value.errors]
    assert any("VOO" in m and "USD" in m for m in messages)
    assert any("ZZZZ" in m for m in messages)
