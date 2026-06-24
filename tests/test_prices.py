from unittest.mock import MagicMock

import pytest
import requests

from ledgr.prices import PriceFetchError, PriceQuote, UnresolvableTickerError, fetch_price


def _response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def test_fetch_price_returns_quote_for_resolvable_ticker():
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _response(
        200, {"chart": {"result": [{"meta": {"currency": "CAD", "regularMarketPrice": 44.94}}]}}
    )
    quote = fetch_price("XEQT.TO", session=session)
    assert quote == PriceQuote(ticker="XEQT.TO", price=44.94, currency="CAD")
    assert session.get.call_count == 1


def test_fetch_price_raises_unresolvable_on_404_without_retry():
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _response(404, {"chart": {"error": {"code": "Not Found"}}})
    with pytest.raises(UnresolvableTickerError) as exc_info:
        fetch_price("ZZZZNOTREAL", session=session)
    assert exc_info.value.ticker == "ZZZZNOTREAL"
    assert session.get.call_count == 1


def test_fetch_price_retries_once_then_raises_on_persistent_malformed_response(monkeypatch):
    monkeypatch.setattr("ledgr.prices.time.sleep", lambda _seconds: None)
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _response(200, {"chart": {"result": [{}]}})
    with pytest.raises(PriceFetchError) as exc_info:
        fetch_price("XEQT.TO", session=session)
    assert exc_info.value.ticker == "XEQT.TO"
    assert "malformed response" in str(exc_info.value)
    assert session.get.call_count == 2


def test_fetch_price_retries_once_then_raises_on_persistent_network_error(monkeypatch):
    monkeypatch.setattr("ledgr.prices.time.sleep", lambda _seconds: None)
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("boom")
    with pytest.raises(PriceFetchError) as exc_info:
        fetch_price("XEQT.TO", session=session)
    assert "request failed" in str(exc_info.value)
    assert session.get.call_count == 2


def test_fetch_price_succeeds_on_retry_after_one_transient_failure(monkeypatch):
    monkeypatch.setattr("ledgr.prices.time.sleep", lambda _seconds: None)
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [
        requests.ConnectionError("boom"),
        _response(200, {"chart": {"result": [{"meta": {"currency": "CAD", "regularMarketPrice": 44.94}}]}}),
    ]
    quote = fetch_price("XEQT.TO", session=session)
    assert quote.price == 44.94
    assert session.get.call_count == 2


def test_fetch_price_retries_on_429_then_succeeds(monkeypatch):
    # A 429 (rate-limited) response can carry an error-shaped JSON body identical
    # to a genuine "ticker not found" response. Status code, not body shape, must
    # gate the permanent-vs-transient decision -- a 429 is never "unresolvable".
    monkeypatch.setattr("ledgr.prices.time.sleep", lambda _seconds: None)
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [
        _response(429, {"chart": {"error": {"code": "Too Many Requests"}}}),
        _response(200, {"chart": {"result": [{"meta": {"currency": "CAD", "regularMarketPrice": 44.94}}]}}),
    ]
    quote = fetch_price("XEQT.TO", session=session)
    assert quote.price == 44.94
    assert session.get.call_count == 2


def test_fetch_price_raises_price_fetch_error_on_persistent_429(monkeypatch):
    monkeypatch.setattr("ledgr.prices.time.sleep", lambda _seconds: None)
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _response(429, {"chart": {"error": {"code": "Too Many Requests"}}})
    with pytest.raises(PriceFetchError) as exc_info:
        fetch_price("XEQT.TO", session=session)
    assert exc_info.value.ticker == "XEQT.TO"
    assert "429" in str(exc_info.value)
    assert session.get.call_count == 2


@pytest.mark.live
def test_fetch_price_against_real_yahoo_endpoint_for_known_good_ticker():
    quote = fetch_price("XEQT.TO")
    assert quote.currency == "CAD"
    assert quote.price > 0


@pytest.mark.live
def test_fetch_price_against_real_yahoo_endpoint_for_unresolvable_ticker():
    with pytest.raises(UnresolvableTickerError):
        fetch_price("ZZZZNOTREAL")
