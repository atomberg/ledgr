from __future__ import annotations

from ledgr.report import TickerReport

YIELD_FOOTNOTE = "Yield reflects price appreciation only; excludes dividends and coupon payments."
HEADERS = ["Ticker", "Quantity", "Cost Basis", "Current Price", "Current Value", "Yield (XIRR %)"]


def format_table(reports: list[TickerReport], total: TickerReport) -> str:
    rows = [_format_row(r) for r in reports] + [_format_row(total)]
    widths = [len(h) for h in HEADERS]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(HEADERS), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(r) for r in rows[:-1])
    lines.append(fmt_row(["-" * w for w in widths]))
    lines.append(fmt_row(rows[-1]))
    lines.append("")
    lines.append(YIELD_FOOTNOTE)
    return "\n".join(lines)


def _format_row(r: TickerReport) -> list[str]:
    price = f"{r.current_price:.2f}" if r.current_price is not None else "-"
    yield_str = f"{r.yield_pct:.2f}%" if r.yield_pct is not None else f"ERROR: {r.yield_error}"
    return [r.ticker, f"{r.quantity:g}", f"{r.cost_basis:.2f}", price, f"{r.current_value:.2f}", yield_str]
