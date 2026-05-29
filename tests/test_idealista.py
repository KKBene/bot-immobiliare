"""Test parsing Idealista.

Split:
  - test offline su fixture: parse_list_basic (struttura HTML)
  - test live (marker integration): enrich_with_api su pochi annunci
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.scrapers.idealista import IdealistaScraper

FIXTURE = Path(__file__).parent / "fixtures" / "idealista_milano_p1.html"


@pytest.fixture(scope="module")
def html() -> str:
    if not FIXTURE.exists():
        pytest.skip(f"Fixture mancante: {FIXTURE}")
    return FIXTURE.read_text()


@pytest.fixture(scope="module")
def basics(html):
    return IdealistaScraper.parse_list_basic(html)


# ============================================================================
# OFFLINE — parsing della listing card
# ============================================================================

def test_parses_at_least_25_listings(basics):
    assert len(basics) >= 25, len(basics)


def test_required_fields_present(basics):
    for l in basics:
        assert l.portal == "idealista"
        assert l.external_id and l.external_id.isdigit()
        assert l.url.startswith("https://www.idealista.it/immobile/")


def test_price_parsed(basics):
    prices = [l.price_eur for l in basics if l.price_eur is not None]
    assert prices, "Nessun prezzo parsato"
    for p in prices:
        assert isinstance(p, int) and 100 <= p <= 100000


def test_surface_parsed(basics):
    surfaces = [l.surface_m2 for l in basics if l.surface_m2 is not None]
    assert surfaces
    for s in surfaces:
        assert 10 <= s <= 2000


def test_description_present_for_most(basics):
    with_desc = sum(1 for l in basics if l.description and len(l.description) > 30)
    assert with_desc / len(basics) >= 0.7


# ============================================================================
# LIVE — chiamata API per arricchire
# ============================================================================

@pytest.mark.integration
def test_enrich_first_listing(basics):
    """Live: chiama API su PRIMO annuncio e verifica struttura."""
    scraper = IdealistaScraper()
    enriched = scraper.enrich_with_api(basics[0])
    assert enriched.advertiser_type in ("agency", "private")
    assert enriched.advertiser_name, "advertiser_name vuoto"
    # almeno 1 phone catturato
    assert enriched.phones, "Nessun phone tornato dall'API"
    for p in enriched.phones:
        # numero o formatted; lo normalizziamo come applicabile
        assert any(ch.isdigit() for ch in p)


@pytest.mark.integration
def test_enrich_detects_known_private(basics):
    """Annuncio 7103669 deve essere classificato come privato."""
    target = next((b for b in basics if b.external_id == "7103669"), None)
    if not target:
        pytest.skip("Annuncio 7103669 non presente nel fixture (può cambiare)")
    scraper = IdealistaScraper()
    enriched = scraper.enrich_with_api(target)
    assert enriched.advertiser_type == "private"
    assert enriched.phones, "Numero telefono assente"
