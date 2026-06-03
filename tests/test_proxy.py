"""Test del modulo proxy (offline, mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.anti_detect import TransientError
from src.proxy import (
    brightdata_get,
    is_brightdata_enabled,
    is_scrapfly_enabled,
    scrapfly_get,
    smart_get,
)


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


def test_smart_get_skips_proxies_when_prefer_false(monkeypatch):
    """prefer_proxy=False salta sia Scrapfly che Bright Data."""
    monkeypatch.setenv("SCRAPFLY_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.scrapfly_get") as sf, \
         patch("src.proxy.brightdata_get") as bd, \
         patch("src.proxy.creq.get") as direct:
        direct.return_value = MagicMock(status_code=200, text="direct")
        smart_get("https://example.com", prefer_proxy=False)
        sf.assert_not_called()
        bd.assert_not_called()
        direct.assert_called_once()


def test_smart_get_direct_when_not_configured(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.delenv("SCRAPFLY_API_KEY", raising=False)
    with patch("src.proxy.creq.get") as direct:
        direct.return_value = MagicMock(status_code=200, text="direct")
        smart_get("https://example.com")
        direct.assert_called_once()


# ---------- Scrapfly ----------

def test_scrapfly_disabled_without_env(monkeypatch):
    monkeypatch.delenv("SCRAPFLY_API_KEY", raising=False)
    assert is_scrapfly_enabled() is False


def test_scrapfly_enabled_with_key(monkeypatch):
    monkeypatch.setenv("SCRAPFLY_API_KEY", "k")
    assert is_scrapfly_enabled() is True


def test_scrapfly_get_passes_params(monkeypatch):
    monkeypatch.setenv("SCRAPFLY_API_KEY", "MYKEY")
    with patch("src.proxy.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = {
            "result": {"status_code": 200, "content": "<html>OK</html>"}
        }
        result = scrapfly_get("https://www.immobiliare.it/x/")
        params = g.call_args.kwargs["params"]
        assert params["key"] == "MYKEY"
        assert params["url"] == "https://www.immobiliare.it/x/"
        assert params["country"] == "it"
        assert params["asp"] == "true"
        assert result.text == "<html>OK</html>"
        assert result.status_code == 200


def test_scrapfly_get_raises_on_429(monkeypatch):
    monkeypatch.setenv("SCRAPFLY_API_KEY", "k")
    with patch("src.proxy.requests.get") as g:
        g.return_value.status_code = 429
        g.return_value.text = ""
        with pytest.raises(TransientError):
            scrapfly_get("https://example.com")


def test_scrapfly_get_raises_runtime_on_auth_fail(monkeypatch):
    monkeypatch.setenv("SCRAPFLY_API_KEY", "k")
    with patch("src.proxy.requests.get") as g:
        g.return_value.status_code = 401
        g.return_value.text = ""
        with pytest.raises(RuntimeError):
            scrapfly_get("https://example.com")


def test_smart_get_prefers_scrapfly_over_brightdata(monkeypatch):
    """Se entrambi configurati, Scrapfly viene chiamato per primo."""
    monkeypatch.setenv("SCRAPFLY_API_KEY", "scrkey")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "bdkey")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.scrapfly_get") as sf, \
         patch("src.proxy.brightdata_get") as bd:
        sf.return_value = MagicMock(status_code=200, text="ok")
        smart_get("https://example.com")
        sf.assert_called_once()
        bd.assert_not_called()


def test_smart_get_falls_back_scrapfly_to_brightdata(monkeypatch):
    """Se Scrapfly fail, prova Bright Data, poi direct."""
    monkeypatch.setenv("SCRAPFLY_API_KEY", "scrkey")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "bdkey")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "z")
    with patch("src.proxy.scrapfly_get", side_effect=TransientError("scr down")), \
         patch("src.proxy.brightdata_get") as bd:
        bd.return_value = MagicMock(status_code=200, text="ok")
        smart_get("https://example.com")
        bd.assert_called_once()
