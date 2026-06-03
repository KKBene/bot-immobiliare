"""Test dell'enrich detail Immobiliare (offline con mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models import Listing
from src.scrapers.immobiliare import ImmobiliareScraper


def _listing(**kw) -> Listing:
    base = dict(
        portal="immobiliare", external_id="999",
        url="https://www.immobiliare.it/annunci/999/",
        advertiser_type="private", advertiser_name=None,
        phones=[], description="", title="Test",
    )
    base.update(kw)
    return Listing(**base)


def _fake_detail(phones_supervisor=None, phones_agency=None,
                 ai_callable=False, description="Una bella casa"):
    """Costruisce un payload simile a __NEXT_DATA__ di una detail page."""
    advertiser = {"aiCallable": ai_callable}
    if phones_supervisor:
        advertiser["supervisor"] = {
            "type": "user", "label": "privato",
            "phones": [{"type": "tel1", "value": p} for p in phones_supervisor],
        }
    if phones_agency:
        advertiser["agency"] = {
            "label": "agenzia",
            "phones": [{"type": "vTel1", "value": p} for p in phones_agency],
        }
    return {
        "props": {"pageProps": {"detailData": {"realEstate": {
            "advertiser": advertiser,
            "properties": [{"description": description}],
        }}}}
    }


def test_enrich_extracts_supervisor_phone():
    s = ImmobiliareScraper()
    listing = _listing()
    with patch.object(s, "fetch_detail_json",
                      return_value=_fake_detail(phones_supervisor=["3387412806"])):
        out = s.enrich_with_detail(listing)
    assert "3387412806" in out.phones


def test_enrich_extracts_agency_phone():
    s = ImmobiliareScraper()
    listing = _listing(advertiser_type="agency")
    with patch.object(s, "fetch_detail_json",
                      return_value=_fake_detail(phones_agency=["02 8736 4229"])):
        out = s.enrich_with_detail(listing)
    assert any("8736" in p for p in out.phones)


def test_enrich_skips_chiama_ai():
    """Se aiCallable=True, NIENTE phone enrich (il numero è AI proxy)."""
    s = ImmobiliareScraper()
    listing = _listing()
    payload = _fake_detail(
        phones_supervisor=["1234567890"],  # numero che ci sarebbe ma...
        ai_callable=True,                  # ...è AI proxy
    )
    with patch.object(s, "fetch_detail_json", return_value=payload):
        out = s.enrich_with_detail(listing)
    assert out.phones == [], "Chiama AI doveva essere skippato"


def test_enrich_mines_obfuscated_phone_in_description():
    """Se phones=[] ma descrizione ha numero offuscato, lo cattura."""
    s = ImmobiliareScraper()
    listing = _listing(title="Bilocale Navigli")
    payload = _fake_detail(
        description="Per info chiamare al 3.3.5.7.4.2.0.0.6.3 grazie.",
    )
    with patch.object(s, "fetch_detail_json", return_value=payload):
        out = s.enrich_with_detail(listing)
    # find_phones_in_text restituisce E.164, ma _merge_phones tiene il formato
    # originale del candidato; quindi nel listing.phones avremo la versione
    # originale del numero estratto. Verifichiamo solo che ci sia ALMENO uno.
    assert len(out.phones) >= 1


def test_enrich_handles_fetch_failure_gracefully():
    s = ImmobiliareScraper()
    listing = _listing()
    with patch.object(s, "fetch_detail_json",
                      side_effect=RuntimeError("DataDome block")):
        out = s.enrich_with_detail(listing)
    # non solleva, ritorna il listing inalterato
    assert out.phones == []


def test_enrich_does_not_lose_existing_phones():
    s = ImmobiliareScraper()
    listing = _listing(phones=["02 8736 4229"])  # già esistente (valido)
    with patch.object(s, "fetch_detail_json",
                      return_value=_fake_detail(phones_supervisor=["3387412806"])):
        out = s.enrich_with_detail(listing)
    # i phones precedenti sono preservati + i nuovi aggiunti
    assert any("8736" in p for p in out.phones)
    assert any("3387412806" in p for p in out.phones)


def test_enrich_dedups_same_phone_in_multiple_sources():
    s = ImmobiliareScraper()
    listing = _listing(phones=["+39 338 7412806"])
    with patch.object(s, "fetch_detail_json",
                      return_value=_fake_detail(phones_supervisor=["3387412806"])):
        out = s.enrich_with_detail(listing)
    # stesso numero in 2 formati → dedup via E.164 → 1 solo entry
    assert len(out.phones) == 1


def test_enrich_upgrades_description_if_longer():
    s = ImmobiliareScraper()
    listing = _listing(description="breve")
    long_desc = "Descrizione molto più lunga e completa del listing card. " * 5
    with patch.object(s, "fetch_detail_json",
                      return_value=_fake_detail(description=long_desc)):
        out = s.enrich_with_detail(listing)
    assert out.description == long_desc
