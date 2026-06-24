from ledgr.report import TickerReport
from ledgr.table import format_table


def test_table_has_one_row_per_ticker_plus_total_and_required_columns():
    reports = [
        TickerReport("XEQT.TO", 9.0, 263.70, 33.0, 297.0, 12.34, None),
        TickerReport("VAB.TO", 20.0, 515.0, 24.0, 480.0, -1.5, None),
    ]
    total = TickerReport("TOTAL", 29.0, 778.70, None, 777.0, 8.0, None)
    output = format_table(reports, total)
    for header in ["Ticker", "Quantity", "Cost Basis", "Current Price", "Current Value", "Yield"]:
        assert header in output
    assert "XEQT.TO" in output
    assert "VAB.TO" in output
    assert "TOTAL" in output


def test_table_includes_dividend_exclusion_footnote():
    reports = [TickerReport("XEQT.TO", 9.0, 263.70, 33.0, 297.0, 12.34, None)]
    total = TickerReport("TOTAL", 9.0, 263.70, None, 297.0, 12.34, None)
    output = format_table(reports, total)
    assert "dividend" in output.lower()
    assert "appreciation" in output.lower()


def test_table_shows_yield_error_instead_of_crashing():
    reports = [TickerReport("XEQT.TO", 9.0, 263.70, 33.0, 297.0, None, "did not converge")]
    total = TickerReport("TOTAL", 9.0, 263.70, None, 297.0, None, "did not converge")
    output = format_table(reports, total)
    assert "did not converge" in output
