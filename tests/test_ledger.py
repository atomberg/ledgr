import datetime as dt

import pytest

from ledgr.ledger import LedgerParseError, Transaction, parse_ledger

TODAY = dt.date(2026, 6, 23)


def test_parses_buy_and_sell_lines_in_chronological_order():
    text = """
# my taxable account
buy XEQT.TO 10 @ 28.40 on 2023-03-01
sell XEQT.TO 6 @ 33.00 on 2024-09-01
buy XEQT.TO 5 @ 31.10 on 2024-01-15
"""
    txns = parse_ledger(text, TODAY)
    assert [t.date for t in txns] == [
        dt.date(2023, 3, 1),
        dt.date(2024, 1, 15),
        dt.date(2024, 9, 1),
    ]
    assert txns[0] == Transaction(
        line_no=3, verb="buy", ticker="XEQT.TO", quantity=10.0, price=28.40, date=dt.date(2023, 3, 1)
    )


def test_blank_and_comment_lines_are_ignored():
    text = "\n# comment\n\nbuy VAB.TO 20 @ 25.75 on 2023-06-10\n"
    txns = parse_ledger(text, TODAY)
    assert len(txns) == 1


def test_fractional_quantity_is_allowed():
    txns = parse_ledger("buy XEQT.TO 12.5 @ 28.40 on 2023-03-01\n", TODAY)
    assert txns[0].quantity == 12.5


def test_malformed_lines_are_batched_into_one_error():
    text = "\n".join(
        [
            "buy XEQT.TO 10 @ 28.40 on 2023-03-01",
            "buy XEQT.TO ten @ 28.40 on 2023-03-01",
            "buy XEQT.TO 10 28.40 on 2023-03-01",
            "buy XEQT.TO -5 @ 28.40 on 2023-03-01",
            "buy XEQT.TO 10 @ 28.40 on 2099-01-01",
            "fly XEQT.TO 10 @ 28.40 on 2023-03-01",
        ]
    )
    with pytest.raises(LedgerParseError) as exc_info:
        parse_ledger(text, TODAY)
    errors = exc_info.value.errors
    assert len(errors) == 5
    assert any("line 2" in e for e in errors)
    assert any("line 3" in e for e in errors)
    assert any("line 4" in e for e in errors)
    assert any("line 5" in e for e in errors)
    assert any("line 6" in e for e in errors)


def test_empty_ledger_raises_value_error():
    with pytest.raises(ValueError, match="no transactions found"):
        parse_ledger("# only a comment\n", TODAY)
