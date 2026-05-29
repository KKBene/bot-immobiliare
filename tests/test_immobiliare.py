"""Test parsing Immobiliare basati su fixture HTML salvato.

Il test è offline e riproducibile: non dipende dalla rete né dallo stato del
sito. Per rigenerare il fixture: `python scripts/run_step1.py --save-fixture`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.scrapers.immobiliare import ImmobiliareScraper

FIXTURE = Path(__file__).parent / "fixtures" / "immobiliare_milano_p1.html"

REQUIRED_FIELDS = ["portal", "external_id", "url"]
EXPECTED_PORTAL = "immobiliare"
EXPECTED_MIN_LISTINGS = 25  # la prima pagina Immobiliare ne restituisce 25


@pytest.fixture(scope="module")
def html() -> str:
    if not FIXTURE.exists():
        pytest.skip(f"Fixture mancante: {FIXTURE}")
    return FIXTURE.read_text()


@pytest.fixture(scope="module")
def listings(html):
    return ImmobiliareScraper.parse_listings(html)


def test_parses_at_least_25_listings(listings):
    assert len(listings) >= EXPECTED_MIN_LISTINGS, (
        f"Attesi >= {EXPECTED_MIN_LISTINGS} annunci, trovati {len(listings)}"
    )


def test_required_fields_always_present(listings):
    """Ogni annuncio deve avere portal, external_id, url non vuoti."""
    for i, l in enumerate(listings):
        for f in REQUIRED_FIELDS:
            v = getattr(l, f)
            assert v, f"Annuncio {i}: campo '{f}' mancante (val={v!r})"


def test_portal_always_immobiliare(listings):
    assert all(l.portal == EXPECTED_PORTAL for l in listings)


def test_url_is_canonical_annunci_link(listings):
    for l in listings:
        assert l.url.startswith("https://www.immobiliare.it/annunci/"), l.url


def test_price_when_visible_is_int(listings):
    """Il prezzo, se presente, è un intero positivo plausibile."""
    prices = [l.price_eur for l in listings if l.price_eur is not None]
    assert prices, "Nessun annuncio con prezzo: sospetto di parsing rotto"
    for p in prices:
        assert isinstance(p, int)
        assert 100 <= p <= 50000, f"Prezzo fuori range plausibile: {p}"


def test_advertiser_type_classified(listings):
    """Ogni annuncio è classificato come 'agency' o 'private'."""
    for l in listings:
        assert l.advertiser_type in ("agency", "private"), (
            f"advertiser_type inatteso: {l.advertiser_type}"
        )


def test_location_contains_milano(listings):
    """Almeno il 90% degli annunci ha city == 'Milano' (alcuni hinterland ok)."""
    milano = sum(1 for l in listings if (l.city or "").lower() == "milano")
    assert milano / len(listings) >= 0.9, (
        f"Solo {milano}/{len(listings)} hanno city=Milano"
    )


def test_surface_parsed_to_int(listings):
    """Quando la superficie è presente è stata convertita da '94 m²' a int."""
    surfaces = [l.surface_m2 for l in listings if l.surface_m2 is not None]
    assert surfaces, "Nessuna superficie parsata"
    for s in surfaces:
        assert isinstance(s, int)
        assert 10 <= s <= 2000, f"Superficie fuori range: {s}"


def test_phones_when_present_are_strings(listings):
    """I telefoni esposti dall'advertiser sono stringhe non vuote."""
    for l in listings:
        for ph in l.phones:
            assert isinstance(ph, str) and ph.strip()
