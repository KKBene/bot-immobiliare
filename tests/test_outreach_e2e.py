"""Test E2E del flow outreach (con DB live).

⚠️  DESTRUCTIVE: pulisce outreach_log e modifica contacts. Skip di default.
Per eseguirlo:
    RUN_DESTRUCTIVE_TESTS=1 pytest tests/test_outreach_e2e.py -m destructive
"""

from __future__ import annotations

import pytest

from src.db import client
from src.outreach import compose_sms, prepare_batch, queue_outreach

pytestmark = pytest.mark.destructive


@pytest.fixture(scope="module")
def sb():
    """Test isolato:
      - pulisce outreach_log
      - garantisce ≥ 2 contact privati con phone + listing collegato

    Non dipende da quanto altri test hanno scritto/cancellato.
    """
    s = client()
    s.table("outreach_log").delete().neq("id", -1).execute()
    s.table("contacts").update(
        {"opted_out_at": None, "do_not_contact": False}
    ).neq("id", -1).execute()

    # Inserisci 2 contact privati di test (idempotente: phone unique)
    test_contacts = [
        {"phone_e164": "+393999000001", "display_name": "TestPriv1",
         "kind": "private", "source": "test_e2e"},
        {"phone_e164": "+393999000002", "display_name": "TestPriv2",
         "kind": "private", "source": "test_e2e"},
    ]
    for c in test_contacts:
        existing = (
            s.table("contacts")
            .select("id")
            .eq("phone_e164", c["phone_e164"])
            .limit(1)
            .execute()
        )
        if existing.data:
            cid = existing.data[0]["id"]
            s.table("contacts").update({"opted_out_at": None,
                                        "do_not_contact": False,
                                        "kind": "private"}).eq("id", cid).execute()
        else:
            s.table("contacts").insert(c).execute()

    # Listing fittizio collegato
    listing_payload = {
        "portal": "idealista",
        "external_id": "TEST_E2E_999",
        "url": "https://www.idealista.it/immobile/TEST_E2E_999/",
        "title": "Test E2E in Sempione, Milano",
        "microzone": "Sempione",
        "city": "Milano",
        "advertiser_type": "private",
        "contract": "rent",
    }
    existing_l = (
        s.table("listings")
        .select("id")
        .eq("portal", "idealista")
        .eq("external_id", "TEST_E2E_999")
        .limit(1)
        .execute()
    )
    if existing_l.data:
        listing_id = existing_l.data[0]["id"]
    else:
        listing_id = s.table("listings").insert(listing_payload).execute().data[0]["id"]

    # Link contacts ↔ listing
    for c in test_contacts:
        cid = s.table("contacts").select("id").eq("phone_e164", c["phone_e164"]).execute().data[0]["id"]
        s.table("listing_contacts").upsert(
            {"listing_id": listing_id, "contact_id": cid, "role": "advertiser"},
            on_conflict="listing_id,contact_id,role"
        ).execute()
    return s


def test_prepare_batch_finds_privates(sb):
    batch = prepare_batch(sb, only_privates=True, only_with_phone=True, limit=20)
    sendable = [b for b in batch if b["can"]]
    assert sendable, "Atteso ≥1 contatto privato con telefono contattabile"
    for b in sendable:
        assert b["contact"]["kind"] == "private"
        assert b["contact"]["phone_e164"]


def test_queue_inserts_in_outreach_log(sb):
    batch = prepare_batch(sb, only_privates=True, limit=5)
    sendable = [b for b in batch if b["can"]]
    queued_count = 0
    for b in sendable:
        res = queue_outreach(sb, b["contact"], b["listing"], channel="sms")
        if res:
            queued_count += 1
    assert queued_count >= 1, "Nessun messaggio accodato"

    # Verifico che siano in outreach_log
    rows = (
        sb.table("outreach_log")
        .select("id, channel, status, message")
        .eq("status", "queued")
        .eq("channel", "sms")
        .execute()
    )
    assert len(rows.data) == queued_count
    for r in rows.data:
        assert "STOP" in r["message"]


def test_second_run_blocks_duplicates(sb):
    """Dopo aver accodato, riprovare → gate blocca."""
    batch = prepare_batch(sb, only_privates=True, limit=5)
    new_queued = 0
    for b in batch:
        if b["can"]:
            res = queue_outreach(sb, b["contact"], b["listing"], channel="sms")
            if res:
                new_queued += 1
    assert new_queued == 0, (
        f"Gate rotta: ha accodato {new_queued} duplicati"
    )


def test_opt_out_excludes_from_batch(sb):
    """Se segno un contact opted_out, scompare dai candidati 'can'."""
    # prendo un contact privato qualsiasi
    contacts = (
        sb.table("contacts")
        .select("id")
        .eq("kind", "private")
        .not_.is_("phone_e164", "null")
        .limit(1)
        .execute()
    )
    if not contacts.data:
        pytest.skip("nessun contact privato disponibile")
    cid = contacts.data[0]["id"]
    # opt-out
    from src.db import mark_opted_out
    mark_opted_out(sb, cid)
    # ora il batch non lo deve marcare can=True
    batch = prepare_batch(sb, only_privates=True, limit=50)
    for b in batch:
        if b["contact"]["id"] == cid:
            # Se viene incluso, deve avere can=False con reason opted_out
            assert not b["can"]
            return
    # Anche meglio: non viene proprio incluso (perché il SELECT filtra
    # opted_out_at IS NULL). Test ok.
