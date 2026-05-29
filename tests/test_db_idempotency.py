"""Test integrazione: 2 run consecutivi dello stesso fixture → 0 duplicati.

Richiede Supabase live (.env). Marker: integration.
Esegue su un set di dati pulito (truncate iniziale delle tabelle).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db import client, sync_listing_with_contacts
from src.scrapers.immobiliare import ImmobiliareScraper

FIXTURE = Path(__file__).parent / "fixtures" / "immobiliare_milano_p1.html"


@pytest.fixture(scope="module")
def sb_clean():
    """Reset DB delle tabelle di lavoro prima del test."""
    sb = client()
    # Ordine: prima i figli (FK), poi i padri
    sb.table("listing_contacts").delete().neq("listing_id", -1).execute()
    sb.table("outreach_log").delete().neq("id", -1).execute()
    sb.table("contacts").delete().neq("id", -1).execute()
    sb.table("listings").delete().neq("id", -1).execute()
    return sb


@pytest.fixture(scope="module")
def listings():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture mancante: {FIXTURE}")
    return ImmobiliareScraper.parse_listings(FIXTURE.read_text())


def _counts(sb) -> dict:
    return {
        "listings": sb.table("listings").select("id", count="exact").execute().count,
        "contacts": sb.table("contacts").select("id", count="exact").execute().count,
        "links": sb.table("listing_contacts").select("listing_id", count="exact").execute().count,
    }


def test_first_run_inserts_all(sb_clean, listings):
    actions = []
    for l in listings:
        actions.append(sync_listing_with_contacts(sb_clean, l))
    after = _counts(sb_clean)
    assert after["listings"] == len(listings), (
        f"Atteso {len(listings)} listings, trovati {after['listings']}"
    )
    assert all(a["listing_action"] == "inserted" for a in actions)
    # tutti hanno almeno il telefono advertiser (agenzie) → ≥ len(listings) contacts unici o meno
    # Mi aspetto < len(listings) perché stessi agenti hanno stesso numero
    assert after["contacts"] > 0
    assert after["links"] >= after["contacts"]


def test_second_run_zero_duplicates(sb_clean, listings):
    before = _counts(sb_clean)
    actions = []
    for l in listings:
        actions.append(sync_listing_with_contacts(sb_clean, l))
    after = _counts(sb_clean)

    # ZERO nuovi record in tutte le tabelle
    assert after == before, (
        f"Dedup rotta!\n  before={before}\n  after ={after}"
    )
    # Tutte le action devono essere "updated" (re-scrape)
    assert all(a["listing_action"] == "updated" for a in actions), (
        Counter(a["listing_action"] for a in actions)
    )


def test_scraped_count_incremented(sb_clean, listings):
    """Dopo 2 run, scraped_count di un annuncio noto deve essere ≥ 2."""
    sample = listings[0]
    row = (
        sb_clean.table("listings")
        .select("scraped_count")
        .eq("portal", sample.portal)
        .eq("external_id", sample.external_id)
        .single()
        .execute()
    )
    assert row.data["scraped_count"] >= 2


# Necessario per il test sopra
from collections import Counter  # noqa: E402
