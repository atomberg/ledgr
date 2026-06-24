from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from ledgr.holdings import LedgerOversellError, build_holdings
from ledgr.ledger import LedgerParseError, parse_ledger
from ledgr.report import LedgerPriceError, build_reports
from ledgr.table import format_table


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledgr",
        description="Report current value and yield (XIRR) for a plain-text investment ledger.",
        epilog="Example ledger line:\n  buy XEQT.TO 10 @ 28.40 on 2023-03-01",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("ledger_path", help="Path to the ledger file")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    today = dt.date.today()
    try:
        text = Path(args.ledger_path).read_text()
        transactions = parse_ledger(text, today)
        holdings = build_holdings(transactions)
        reports, total = build_reports(holdings, today)
    except (LedgerParseError, LedgerOversellError, LedgerPriceError, ValueError, OSError) as exc:
        print(f"Error:\n{exc}", file=sys.stderr)
        sys.exit(1)
    print(format_table(reports, total))
