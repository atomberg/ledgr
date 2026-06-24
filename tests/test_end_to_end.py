# tests/test_end_to_end.py
from unittest.mock import patch

import pytest

from ledgr.cli import main
from ledgr.prices import PriceQuote, UnresolvableTickerError


LEDGER = """
# my taxable account
buy XEQT.TO 10 @ 28.40 on 2023-03-01
buy XEQT.TO 5 @ 31.10 on 2024-01-15
sell XEQT.TO 6 @ 33.00 on 2024-09-01
buy VAB.TO 20 @ 25.75 on 2023-06-10
buy ZSP.TO 8 @ 60.00 on 2022-01-01
sell ZSP.TO 8 @ 65.00 on 2023-01-01
"""


def _fake_fetch(ticker, session=None):
    quotes = {
        "XEQT.TO": PriceQuote(ticker="XEQT.TO", price=33.0, currency="CAD"),
        "VAB.TO": PriceQuote(ticker="VAB.TO", price=24.0, currency="CAD"),
    }
    if ticker in quotes:
        return quotes[ticker]
    raise UnresolvableTickerError(ticker)


def test_full_pipeline_reports_held_and_fully_sold_tickers(tmp_path, capsys):
    ledger_file = tmp_path / "ledger.txt"
    ledger_file.write_text(LEDGER)
    with patch("ledgr.report.fetch_price", side_effect=_fake_fetch):
        main([str(ledger_file)])
    output = capsys.readouterr().out
    assert "XEQT.TO" in output
    assert "VAB.TO" in output
    assert "ZSP.TO" in output  # fully sold, must still appear
    assert "TOTAL" in output
    assert "appreciation" in output.lower()


def test_full_pipeline_blocks_on_oversell(tmp_path, capsys):
    bad_ledger = "buy XEQT.TO 10 @ 28.40 on 2023-03-01\nsell XEQT.TO 15 @ 33.00 on 2024-09-01\n"
    ledger_file = tmp_path / "ledger.txt"
    ledger_file.write_text(bad_ledger)
    with pytest.raises(SystemExit) as exc_info:
        main([str(ledger_file)])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "XEQT.TO" in err
    assert "5" in err  # oversell amount


def test_full_pipeline_blocks_on_empty_ledger(tmp_path):
    ledger_file = tmp_path / "ledger.txt"
    ledger_file.write_text("# nothing here\n")
    with pytest.raises(SystemExit) as exc_info:
        main([str(ledger_file)])
    assert exc_info.value.code != 0
