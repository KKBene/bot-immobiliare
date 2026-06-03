"""Test del modulo proxy (offline, mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.anti_detect import TransientError
from src.proxy import brightdata_get, is_brightdata_enabled, smart_get


# ---------- is_brightdata_enabled ----------

def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    assert is_brightdata_enabled() is False


def test_disabled_with_only_key(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    assert is_brightdata_enabled() is False


def test_enabled_with_both(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    assert is_brightdata_enabled() is True


# ---------- brightdata_get ----------

def test_brightdata_get_passes_payload(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "MYKEY")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "myzone")
    with patch("src.proxy.requests.post") as p:
        p.return_value.status_code = 200
        p.return_value.text = "<html>OK</html>"
        brightdata_get("https://www.immobiliare.it/annunci/1/")
        kwargs = p.call_args.kwargs
        body = kwargs["json"]
        assert body["zone"] == "myzone"
        assert body["url"] == "https://www.immobiliare.it/annunci/1/"
        assert body["country"] == "it"
        assert "Bearer MYKEY" in kwargs["headers"]["Authorization"]


def test_brightdata_get_raises_on_429(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.requests.post") as p:
        p.return_value.status_code = 429
        p.return_value.text = ""
        with pytest.raises(TransientError):
            brightdata_get("https://example.com")


def test_brightdata_get_raises_on_5xx(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.requests.post") as p:
        p.return_value.status_code = 503
        p.return_value.text = ""
        with pytest.raises(TransientError):
            brightdata_get("https://example.com")


def test_brightdata_get_raises_runtime_on_auth_fail(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.requests.post") as p:
        p.return_value.status_code = 401
        p.return_value.text = ""
        with pytest.raises(RuntimeError):
            brightdata_get("https://example.com")


# ---------- smart_get ----------

def test_smart_get_uses_brightdata_when_enabled(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.brightdata_get") as bd, \
         patch("src.proxy.creq.get") as direct:
        bd.return_value = MagicMock(status_code=200, text="ok")
        smart_get("https://example.com")
        bd.assert_called_once()
        direct.assert_not_called()


def test_smart_get_falls_back_to_direct_when_brightdata_fails(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.brightdata_get", side_effect=TransientError("rate-limit")), \
         patch("src.proxy.creq.get") as direct:
        direct.return_value = MagicMock(status_code=200, text="fallback")
        result = smart_get("https://example.com")
        direct.assert_called_once()


def test_smart_get_skips_brightdata_when_prefer_false(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.brightdata_get") as bd, \
         patch("src.proxy.creq.get") as direct:
        direct.return_value = MagicMock(status_code=200, text="direct")
        smart_get("https://example.com", prefer_brightdata=False)
        bd.assert_not_called()
        direct.assert_called_once()


def test_smart_get_direct_when_not_configured(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    with patch("src.proxy.creq.get") as direct:
        direct.return_value = MagicMock(status_code=200, text="direct")
        smart_get("https://example.com")
        direct.assert_called_once()
