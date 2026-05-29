"""Test offline del composer SMS: deve produrre testo ASCII-safe entro budget."""

from __future__ import annotations

import pytest

from src.models import Listing
from src.outreach import _asciify, compose_sms


def _make_listing(**overrides) -> Listing:
    base = dict(
        portal="idealista",
        external_id="123",
        url="https://x.it/123",
        title="Bilocale in Via Test, 10, Sempione, Milano",
        advertiser_type="private",
        advertiser_name="Marino Rossi",
        address="Via Test",
        microzone="Sempione",
        city="Milano",
    )
    base.update(overrides)
    return Listing(**base)


def test_sms_contains_first_name():
    msg = compose_sms(_make_listing())
    assert "Marino" in msg
    assert "Rossi" not in msg  # solo primo nome


def test_sms_contains_zone():
    msg = compose_sms(_make_listing(microzone="Navigli"))
    assert "Navigli" in msg


def test_sms_contains_optout():
    msg = compose_sms(_make_listing())
    assert "STOP" in msg


def test_sms_is_ascii():
    """Niente caratteri non-ASCII per rimanere in GSM-7 → SMS più corti."""
    msg = compose_sms(_make_listing())
    assert msg.isascii(), f"Caratteri non-ASCII in: {msg!r}"


def test_sms_length_at_most_2_segments():
    """Idealmente 1 SMS (160 char), accettabile 2 SMS concat (305 char).
    Più di 2 SMS = costo proibitivo a 50/giorno.
    """
    msg = compose_sms(_make_listing())
    assert len(msg) <= 305, f"SMS troppo lungo: {len(msg)} char"


def test_sms_portal_friendly_names():
    msg_idea = compose_sms(_make_listing(portal="idealista"))
    msg_immo = compose_sms(_make_listing(portal="immobiliare"))
    assert "Idealista" in msg_idea
    assert "Immobiliare.it" in msg_immo


def test_sms_uses_contact_name_if_provided():
    """Quando passo il contact con display_name, prevale su advertiser_name."""
    msg = compose_sms(_make_listing(), contact={"display_name": "Anna Bianchi"})
    assert "Anna" in msg
    assert "Marino" not in msg


def test_sms_handles_missing_name_gracefully():
    msg = compose_sms(_make_listing(advertiser_name=None))
    # Non deve crashare e non deve avere "Ciao ," doppia virgola/spazio
    assert "Ciao," in msg
    assert "Ciao ," not in msg


@pytest.mark.parametrize("inp,expected", [
    ("ciao è andato", "ciao e andato"),
    ("Più di così", "Piu di cosi"),
    ("perché no", "perche no"),
    ("plain", "plain"),
])
def test_asciify(inp, expected):
    assert _asciify(inp) == expected
