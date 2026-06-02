"""Test del modulo geocoding (offline con mock requests)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.geocoding import _query_nominatim, geocode_address, geocode_listing_inplace
from src.models import Listing


@pytest.fixture(autouse=True)
def clear_cache():
    _query_nominatim.cache_clear()
    yield
    _query_nominatim.cache_clear()


def _mock_response(payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


def test_query_in_milano_bbox_succeeds():
    with patch("src.geocoding.requests.get") as g, patch("src.geocoding.time.sleep"):
        g.return_value = _mock_response([{"lat": "45.4642", "lon": "9.1900"}])
        assert _query_nominatim("Piazza Duomo, Milano, Italia") == (45.4642, 9.19)


def test_query_outside_milano_returns_none():
    with patch("src.geocoding.requests.get") as g, patch("src.geocoding.time.sleep"):
        # Roma è fuori bbox Milano
        g.return_value = _mock_response([{"lat": "41.9028", "lon": "12.4964"}])
        assert _query_nominatim("Colosseo, Roma, Italia") is None


def test_query_empty_response_returns_none():
    with patch("src.geocoding.requests.get") as g, patch("src.geocoding.time.sleep"):
        g.return_value = _mock_response([])
        assert _query_nominatim("Foo Bar 999") is None


def test_geocode_address_with_zone_first():
    """Prima query con zone deve essere chiamata se address E zone presenti."""
    calls = []
    def fake_get(url, **kw):
        calls.append(kw["params"]["q"])
        return _mock_response([{"lat": "45.4642", "lon": "9.1900"}])
    with patch("src.geocoding.requests.get", side_effect=fake_get), \
         patch("src.geocoding.time.sleep"):
        geocode_address("Via Roma", "Centro", "Milano")
    # Prima query deve includere zone
    assert "Via Roma" in calls[0] and "Centro" in calls[0]


def test_geocode_address_falls_back_to_zone_only():
    """Se address+zone falliscono, prova solo address poi solo zone."""
    responses = [
        _mock_response([]),  # address+zone
        _mock_response([]),  # address only
        _mock_response([{"lat": "45.5", "lon": "9.2"}]),  # zone only
    ]
    iter_resp = iter(responses)
    with patch("src.geocoding.requests.get", side_effect=lambda *a, **kw: next(iter_resp)), \
         patch("src.geocoding.time.sleep"):
        result = geocode_address("Inesistente", "Sempione", "Milano")
    assert result == (45.5, 9.2)


def test_geocode_address_returns_none_when_no_input():
    assert geocode_address(None, None) is None


def test_listing_inplace_no_op_if_already_geo():
    sb = MagicMock()
    l = Listing(portal="x", external_id="1", url="", latitude=45.5, longitude=9.2)
    assert geocode_listing_inplace(sb, l) is True
    sb.table.assert_not_called()  # niente chiamate DB


def test_listing_inplace_writes_to_db_on_success():
    sb = MagicMock()
    l = Listing(
        portal="idealista", external_id="999", url="",
        address="Via Test 1", microzone="Sempione", city="Milano",
    )
    with patch("src.geocoding.geocode_address", return_value=(45.5, 9.2)):
        ok = geocode_listing_inplace(sb, l)
    assert ok is True
    assert l.latitude == 45.5
    assert l.longitude == 9.2
    sb.table.assert_called_with("listings")


def test_listing_inplace_skips_without_address_or_zone():
    sb = MagicMock()
    l = Listing(portal="x", external_id="1", url="")
    assert geocode_listing_inplace(sb, l) is False
