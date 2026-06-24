from __future__ import annotations

import datetime as dt
from math import isfinite

CashFlow = tuple[dt.date, float]


class XIRRError(Exception):
    pass


def _npv(rate: float, flows: list[CashFlow]) -> float:
    t0 = flows[0][0]
    return sum(amount / (1 + rate) ** ((date - t0).days / 365.0) for date, amount in flows)


def xirr(
    flows: list[CashFlow],
    lo: float = -0.999999,
    hi: float = 1000.0,
    tol: float = 1e-9,
    max_iter: int = 100,
) -> float:
    if len(flows) < 2:
        raise XIRRError("XIRR requires at least two cash flows")
    sorted_flows = sorted(flows, key=lambda f: f[0])
    f_lo, f_hi = _npv(lo, sorted_flows), _npv(hi, sorted_flows)
    if f_lo * f_hi > 0:
        raise XIRRError("no sign change in cash flows; cannot bracket a root")

    x = 0.1
    fx = _npv(x, sorted_flows)
    h = 1e-6
    for _ in range(max_iter):
        if f_lo * fx < 0:
            hi, f_hi = x, fx
        else:
            lo, f_lo = x, fx
        if abs(fx) < tol:
            return x
        deriv = (_npv(x + h, sorted_flows) - _npv(x - h, sorted_flows)) / (2 * h)
        x_next = x - fx / deriv if deriv != 0 and isfinite(deriv) else (lo + hi) / 2
        if not (lo < x_next < hi) or not isfinite(x_next):
            x_next = (lo + hi) / 2
        x = x_next
        fx = _npv(x, sorted_flows)
        if (hi - lo) < tol:
            return x
    raise XIRRError(f"root-finder did not converge after {max_iter} iterations")
