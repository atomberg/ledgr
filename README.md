# ledgr

CLI that reads a plain-text ledger of buy/sell transactions for CAD-listed
securities and reports current value and annualized yield (XIRR) per holding,
plus a portfolio-wide TOTAL row.

## Usage

```
uv sync
uv run ledgr <path-to-ledger-file>
```

## Ledger format

One transaction per line:

```
buy <TICKER> <QUANTITY> @ <PRICE> on <YYYY-MM-DD>
sell <TICKER> <QUANTITY> @ <PRICE> on <YYYY-MM-DD>
```

- `TICKER` must be a Yahoo Finance-resolvable, CAD-listed symbol (e.g. `XEQT.TO`).
- Blank lines and lines starting with `#` are ignored.
- Cost basis uses average cost basis (ACB) — matches the Canadian adjusted-cost-base
  convention. There is no per-lot (FIFO) tracking.
- Yield reflects price appreciation only; it excludes dividends and coupon payments.

Example:

```
# my taxable account
buy XEQT.TO 10 @ 28.40 on 2023-03-01
buy XEQT.TO 5 @ 31.10 on 2024-01-15
sell XEQT.TO 6 @ 33.00 on 2024-09-01
buy VAB.TO 20 @ 25.75 on 2023-06-10
```

## Development

```
uv run pytest                       # unit + integration tests (mocked HTTP only)
uv run pytest -m live               # also hits the real Yahoo endpoint -- run before a release
uv run ruff check src tests
uv run mypy src
```
