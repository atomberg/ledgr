import datetime as dt

import pytest

from ledgr.xirr import XIRRError, xirr


def test_single_buy_matches_closed_form_reduction():
    # (current_value/cost_basis)^(1/years) - 1, years = 365 days
    flows = [(dt.date(2023, 1, 1), -1000.0), (dt.date(2024, 1, 1), 1100.0)]
    years = (dt.date(2024, 1, 1) - dt.date(2023, 1, 1)).days / 365.0
    expected = (1100.0 / 1000.0) ** (1 / years) - 1
    assert xirr(flows) == pytest.approx(expected, abs=1e-6)


def test_adversarial_multi_buy_sell_deep_drawdown_and_recovery():
    # Verified live against scipy.optimize.brentq during planning: reference
    # rate = 0.004787828794325142 (matches to 2.3e-8 percentage points).
    flows = [
        (dt.date(2021, 1, 10), -1000.0),
        (dt.date(2021, 7, 22), -600.0),
        (dt.date(2022, 3, 4), -750.0),
        (dt.date(2023, 11, 17), 500.0),
        (dt.date(2026, 6, 23), 1900.0),
    ]
    rate = xirr(flows)
    assert rate == pytest.approx(0.004787828794325142, abs=1e-4)


def test_no_sign_change_raises_xirr_error():
    flows = [(dt.date(2023, 1, 1), -1000.0), (dt.date(2024, 1, 1), -10.0)]
    with pytest.raises(XIRRError, match="sign change"):
        xirr(flows)


def test_single_flow_raises_xirr_error():
    with pytest.raises(XIRRError, match="at least two"):
        xirr([(dt.date(2023, 1, 1), -1000.0)])


def test_flows_out_of_order_are_sorted_internally():
    flows = [(dt.date(2024, 1, 1), 1100.0), (dt.date(2023, 1, 1), -1000.0)]
    years = (dt.date(2024, 1, 1) - dt.date(2023, 1, 1)).days / 365.0
    expected = (1100.0 / 1000.0) ** (1 / years) - 1
    assert xirr(flows) == pytest.approx(expected, abs=1e-6)


def test_non_convergence_raises_explicit_error_not_unguarded_result():
    # max_iter=0 forces the root-finder to exhaust its iteration budget before
    # any refinement step runs, deterministically exercising the convergence-
    # failure branch (xirr.py's final `raise XIRRError(...)` after the loop)
    # without relying on a pathological cash-flow series to fail to converge.
    flows = [(dt.date(2023, 1, 1), -1000.0), (dt.date(2024, 1, 1), 1100.0)]
    with pytest.raises(XIRRError, match="did not converge"):
        xirr(flows, max_iter=0)


def test_short_holding_period_large_gain_is_computed_not_rejected():
    # A position bought 14 days ago, up 22.6%. Annualized this is a legitimate but
    # extreme rate (~20000%) that lands between the old hi=100.0 ceiling and the
    # widened hi=1000.0 -- must return a real number, not
    # XIRRError("no sign change"), which the old bracket was too narrow to reach.
    flows = [(dt.date(2026, 6, 9), -1000.0), (dt.date(2026, 6, 23), 1226.0)]
    years = (dt.date(2026, 6, 23) - dt.date(2026, 6, 9)).days / 365.0
    expected = (1226.0 / 1000.0) ** (1 / years) - 1
    assert 100.0 < expected < 1000.0  # confirms this case needed the widened bracket
    assert xirr(flows) == pytest.approx(expected, rel=1e-3)
