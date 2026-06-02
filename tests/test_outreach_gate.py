"""Test della gate `can_outreach`: regola anti-doppio-contatto + opt-out.

⚠️  DESTRUCTIVE: crea/cancella contacts e outreach_log reali. Skip di default.
Per eseguirlo:
    RUN_DESTRUCTIVE_TESTS=1 pytest tests/test_outreach_gate.py -m destructive

Casi coperti:
  1. contatto vergine → allowed
  2. contatto con outreach SMS recente → blocked su SMS, allowed su email
  3. opt-out → blocked su qualunque canale
  4. flag do_not_contact → blocked
"""

from __future__ import annotations

import pytest

from src.db import (
    can_outreach,
    client,
    get_or_create_contact,
    log_outreach,
    mark_opted_out,
)

pytestmark = pytest.mark.destructive


@pytest.fixture(scope="module")
def sb():
    return client()


@pytest.fixture
def fresh_contact(sb):
    """Crea un contact unico per ogni test, e lo pulisce a fine test."""
    import uuid
    phone = f"+393{uuid.uuid4().int % 10**9:09d}"
    c = sb.table("contacts").insert(
        {"phone_e164": phone, "kind": "private", "source": "test"}
    ).execute().data[0]
    yield c
    # cleanup
    sb.table("outreach_log").delete().eq("contact_id", c["id"]).execute()
    sb.table("contacts").delete().eq("id", c["id"]).execute()


def test_virgin_contact_allowed(sb, fresh_contact):
    ok, reason = can_outreach(sb, fresh_contact["id"], "sms")
    assert ok, reason
    assert reason == "ok"


def test_recent_outreach_blocks_same_channel(sb, fresh_contact):
    log_outreach(
        sb,
        contact_id=fresh_contact["id"],
        listing_id=None,
        channel="sms",
        status="sent",
        message="test",
    )
    ok, reason = can_outreach(sb, fresh_contact["id"], "sms")
    assert not ok, "Doveva bloccare: outreach già fatto sullo stesso canale"
    assert "already_contacted" in reason


def test_recent_outreach_does_not_block_different_channel(sb, fresh_contact):
    log_outreach(
        sb,
        contact_id=fresh_contact["id"],
        listing_id=None,
        channel="sms",
        status="sent",
        message="test sms",
    )
    ok, reason = can_outreach(sb, fresh_contact["id"], "email")
    assert ok, f"Email doveva essere allowed (SMS già fatto, diverso canale): {reason}"


def test_opt_out_blocks_all_channels(sb, fresh_contact):
    mark_opted_out(sb, fresh_contact["id"])
    for ch in ("sms", "email", "portal_form", "whatsapp"):
        ok, reason = can_outreach(sb, fresh_contact["id"], ch)
        assert not ok, f"Canale {ch} doveva essere bloccato da opt-out"
        assert reason == "opted_out"


def test_do_not_contact_flag_blocks(sb, fresh_contact):
    sb.table("contacts").update({"do_not_contact": True}).eq(
        "id", fresh_contact["id"]
    ).execute()
    ok, reason = can_outreach(sb, fresh_contact["id"], "sms")
    assert not ok
    assert reason == "do_not_contact_flag"


def test_failed_outreach_does_not_block_retry(sb, fresh_contact):
    """Un tentativo fallito (status='failed') NON deve impedire un retry."""
    log_outreach(
        sb,
        contact_id=fresh_contact["id"],
        listing_id=None,
        channel="sms",
        status="failed",
        error="network",
    )
    ok, reason = can_outreach(sb, fresh_contact["id"], "sms")
    assert ok, f"Failed deve essere retry-abile: reason={reason}"
