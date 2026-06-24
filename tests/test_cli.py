from unittest.mock import patch

import pytest

from ledgr.cli import build_parser, main
from ledgr.prices import PriceQuote


def test_help_mentions_invocation_and_example(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    output = capsys.readouterr().out
    assert "ledgr" in output
    assert "buy XEQT.TO" in output


def test_main_prints_table_for_valid_ledger(tmp_path, capsys):
    ledger_file = tmp_path / "ledger.txt"
    ledger_file.write_text("buy XEQT.TO 10 @ 28.40 on 2023-03-01\n")
    with patch("ledgr.report.fetch_price", return_value=PriceQuote(ticker="XEQT.TO", price=33.0, currency="CAD")):
        main([str(ledger_file)])
    output = capsys.readouterr().out
    assert "XEQT.TO" in output
    assert "TOTAL" in output


def test_main_exits_nonzero_on_malformed_ledger(tmp_path, capsys):
    ledger_file = tmp_path / "ledger.txt"
    ledger_file.write_text("buy XEQT.TO ten @ 28.40 on 2023-03-01\n")
    with pytest.raises(SystemExit) as exc_info:
        main([str(ledger_file)])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "line 1" in err


def test_main_exits_nonzero_on_missing_ledger_file(tmp_path, capsys):
    missing_path = tmp_path / "does-not-exist.txt"
    with pytest.raises(SystemExit) as exc_info:
        main([str(missing_path)])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "does-not-exist.txt" in err
    assert "Traceback" not in err
