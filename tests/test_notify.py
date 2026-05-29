"""Test del modulo notify (Telegram). No-op se TOKEN non configurato."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models import Listing
from src.notify import _escape_md, notify_new_private_listing, send_telegram


@pytest.fixture
def listing_priv() -> Listing:
    return Listing(
        portal="idealista",
        external_id="7103669",
        url="https://www.idealista.it/immobile/7103669/",
        title="Monolocale in Via Test",
        advertiser_type="private",
        advertiser_name="Marino",
        microzone="Sempione",
        city="Milano",
        price_eur=950,
        surface_m2=35,
        rooms="1",
        phones=["+393357420063"],
    )


# ---------- senza configurazione ----------

def test_send_telegram_noop_when_not_configured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_telegram("hello") is False


def test_notify_does_not_raise_on_missing_config(monkeypatch, listing_priv):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    # non deve crashare
    assert notify_new_private_listing(listing_priv) is False


def test_notify_skips_non_private(monkeypatch, listing_priv):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    listing_priv.advertiser_type = "agency"
    with patch("src.notify.requests.post") as mock_post:
        result = notify_new_private_listing(listing_priv)
        mock_post.assert_not_called()
    assert result is False


# ---------- con config valida (mock requests) ----------

def test_send_telegram_calls_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE_TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    with patch("src.notify.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        assert send_telegram("hi") is True
        args, kwargs = mock_post.call_args
        assert "FAKE_TOKEN" in args[0]
        body = kwargs["json"]
        assert body["chat_id"] == "12345"
        assert body["text"] == "hi"
        assert body["parse_mode"] == "Markdown"


def test_notify_format_includes_key_fields(monkeypatch, listing_priv):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    with patch("src.notify.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        notify_new_private_listing(listing_priv)
        text = mock_post.call_args.kwargs["json"]["text"]
        assert "Marino" in text
        assert "+393357420063" in text
        assert "Sempione" in text
        assert "950" in text
        assert "35 m²" in text
        assert "1 locali" in text
        assert listing_priv.url in text
        assert "Idealista" in text


def test_telegram_failure_does_not_raise(monkeypatch, listing_priv):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    with patch("src.notify.requests.post") as mock_post:
        mock_post.side_effect = Exception("network down")
        # non deve sollevare
        assert send_telegram("hi") is False


# ---------- escape markdown ----------

@pytest.mark.parametrize("inp,expected", [
    ("normal text", "normal text"),
    ("test_with_underscore", r"test\_with\_underscore"),
    ("*bold*", r"\*bold\*"),
    ("`code`", r"\`code\`"),
    ("[link]", r"\[link]"),
    ("", ""),
    (None, ""),
])
def test_escape_md(inp, expected):
    assert _escape_md(inp) == expected
