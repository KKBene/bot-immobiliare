"""Test della paginazione dinamica + mark stale.

Usa mock per non sbattere sui portali. Verifica la logica di stop dinamico
e dell'interazione con `listing_already_in_db`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models import Listing
from src.pipeline import (
    DEFAULT_MAX_PAGES,
    STOP_WHEN_ALREADY_SEEN_PCT,
    cycle_idealista,
    mark_stale_listings,
)


def _make_listing(ext_id: str, kind: str = "private") -> Listing:
    # phone deterministico ma indipendente dal formato di ext_id (può contenere "_")
    phone_suffix = abs(hash(ext_id)) % 10_000_000
    return Listing(
        portal="idealista",
        external_id=ext_id,
        url=f"https://www.idealista.it/immobile/{ext_id}/",
        title=f"Test {ext_id}",
        advertiser_type=kind,
        advertiser_name=f"Tester{ext_id}",
        microzone="Test Zone",
        city="Milano",
        phones=[f"+39333{phone_suffix:07d}"],
    )


def test_stops_when_page_fully_known(monkeypatch):
    """Con min_pages=1 e pagina 100% nota → stop subito dopo p1."""
    sb = MagicMock()

    fake_basics_pages = {
        1: [_make_listing(str(i)) for i in range(1, 11)],
        2: [_make_listing(str(i)) for i in range(11, 21)],
        3: [_make_listing(str(i)) for i in range(21, 31)],
    }

    def fake_fetch(self, page):
        return f"HTML_PAGE_{page}"

    def fake_parse(html):
        page_num = int(html.split("_")[-1])
        return fake_basics_pages[page_num]

    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.fetch_list_html", fake_fetch
    )
    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.parse_list_basic",
        staticmethod(fake_parse),
    )
    monkeypatch.setattr(
        "src.pipeline.listing_already_in_db", lambda sb, p, eid: True
    )
    monkeypatch.setattr("src.pipeline.sync_listing_with_contacts",
                        lambda sb, l: {"listing_action": "updated", "id": 1, "contacts_linked": 0})
    monkeypatch.setattr("src.pipeline.safe_sleep", lambda *a, **kw: None)

    stats = cycle_idealista(sb, max_pages=5, min_pages=1)
    assert stats.portal_counts["idealista"].get("pages_explored") == 1


def test_min_pages_forces_coverage_even_if_first_page_fully_known(monkeypatch):
    """Con min_pages=3 e tutte note → esplora 3 pagine prima di stoppare."""
    sb = MagicMock()
    pages = {p: [_make_listing(f"p{p}_{i}") for i in range(10)] for p in range(1, 6)}

    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.fetch_list_html",
        lambda self, page: f"HTML_{page}",
    )
    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.parse_list_basic",
        staticmethod(lambda html: pages[int(html.split("_")[-1])]),
    )
    monkeypatch.setattr("src.pipeline.listing_already_in_db", lambda sb, p, eid: True)
    monkeypatch.setattr("src.pipeline.sync_listing_with_contacts",
                        lambda sb, l: {"listing_action": "updated", "id": 1, "contacts_linked": 0})
    monkeypatch.setattr("src.pipeline.safe_sleep", lambda *a, **kw: None)

    stats = cycle_idealista(sb, max_pages=5, min_pages=3)
    assert stats.portal_counts["idealista"]["pages_explored"] == 3


def test_paginates_to_max_when_all_new(monkeypatch):
    """Se ogni pagina è 100% nuova → arriva fino a max_pages."""
    sb = MagicMock()

    def fake_fetch(self, page):
        return f"HTML_PAGE_{page}"

    def fake_parse(html):
        page = int(html.split("_")[-1])
        return [_make_listing(f"{page}_{i}") for i in range(5)]

    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.fetch_list_html", fake_fetch
    )
    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.parse_list_basic",
        staticmethod(fake_parse),
    )
    monkeypatch.setattr(
        "src.pipeline.listing_already_in_db", lambda sb, p, eid: False
    )

    enriched_basics = []
    def fake_enrich(self, basic, **kw):
        enriched_basics.append(basic.external_id)
        return basic

    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.enrich_with_api", fake_enrich
    )
    monkeypatch.setattr("src.pipeline.sync_listing_with_contacts",
                        lambda sb, l: {"listing_action": "inserted", "id": 1, "contacts_linked": 1})
    monkeypatch.setattr("src.pipeline.notify_new_private_listing", lambda l: True)
    monkeypatch.setattr("src.pipeline.safe_sleep", lambda *a, **kw: None)

    stats = cycle_idealista(sb, max_pages=3)
    assert stats.portal_counts["idealista"]["pages_explored"] == 3
    assert stats.portal_counts["idealista"]["synced_new"] == 15  # 3 pagine × 5
    assert stats.portal_counts["idealista"]["new_private"] == 15


def test_stops_when_threshold_crossed_mid_paging(monkeypatch):
    """Pagina 1: 50% nuovi · pagina 2: 100% nuovi · pagina 3: 90% già visti → stop."""
    sb = MagicMock()
    pages_db = {
        # listings già in DB
        "p1_2", "p1_3", "p1_4", "p1_5",
        "p3_1", "p3_2", "p3_3", "p3_4", "p3_5",
        "p3_6", "p3_7", "p3_8", "p3_9",
    }

    def fake_fetch(self, page):
        return f"HTML_PAGE_{page}"

    def fake_parse(html):
        page = int(html.split("_")[-1])
        return [_make_listing(f"p{page}_{i}") for i in range(1, 11)]

    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.fetch_list_html", fake_fetch
    )
    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.parse_list_basic",
        staticmethod(fake_parse),
    )
    monkeypatch.setattr(
        "src.pipeline.listing_already_in_db",
        lambda sb, p, eid: eid in pages_db,
    )
    monkeypatch.setattr(
        "src.scrapers.idealista.IdealistaScraper.enrich_with_api",
        lambda self, b, **kw: b,
    )
    monkeypatch.setattr("src.pipeline.sync_listing_with_contacts",
                        lambda sb, l: {"listing_action": "inserted", "id": 1, "contacts_linked": 0})
    monkeypatch.setattr("src.pipeline.notify_new_private_listing", lambda l: True)
    monkeypatch.setattr("src.pipeline.safe_sleep", lambda *a, **kw: None)

    stats = cycle_idealista(sb, max_pages=10)
    # Page 3 ha 9/10 = 90% in DB → stop
    assert stats.portal_counts["idealista"]["pages_explored"] == 3


# ============================================================================
# Mark stale
# ============================================================================

def test_mark_stale_calls_supabase_correctly(monkeypatch):
    """Verifica che la chiamata UPDATE includa il cutoff giusto e neq status."""
    sb = MagicMock()
    chain = MagicMock()
    sb.table.return_value.update.return_value.lt.return_value.neq.return_value.execute.return_value = chain
    chain.data = [{"id": 1}, {"id": 2}]

    n = mark_stale_listings(sb, hours=48)
    assert n == 2
    sb.table.assert_called_with("listings")
    sb.table().update.assert_called_with({"status": "removed"})
    # lt cutoff è ~48h fa: verifico almeno che neq status="removed" sia chiamato
    sb.table().update().lt().neq.assert_called_with("status", "removed")
