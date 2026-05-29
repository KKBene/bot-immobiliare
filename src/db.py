"""Wrapper Supabase con upsert idempotenti e dedup contatti.

Tutta la logica di "se l'ho già visto/contattato non rifare" è qui.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from src.models import Listing
from src.normalize import normalize_email, normalize_phone_it

load_dotenv()

# Finestra di cool-off: non riscriviamo allo stesso contact sullo stesso canale
# entro questi giorni. 90 = "stessa stagione, già contattato".
OUTREACH_COOLOFF_DAYS = 90


# ---------- client factory ----------

_client: Optional[Client] = None


def client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


# ============================================================================
# LISTINGS
# ============================================================================

def upsert_listing(sb: Client, listing: Listing) -> dict:
    """Upsert idempotente su (portal, external_id).

    Aggiorna last_seen_at + incrementa scraped_count se l'annuncio esiste già.
    Mantiene first_seen_at della prima volta.
    """
    payload = {
        "portal": listing.portal,
        "external_id": listing.external_id,
        "url": listing.url,
        "title": listing.title,
        "description": listing.description,
        "price_eur": listing.price_eur,
        "surface_m2": listing.surface_m2,
        "rooms": listing.rooms,
        "bathrooms": listing.bathrooms,
        "floor": listing.floor,
        "typology": listing.typology,
        "address": listing.address,
        "city": listing.city,
        "macrozone": listing.macrozone,
        "microzone": listing.microzone,
        "latitude": listing.latitude,
        "longitude": listing.longitude,
        "advertiser_type": listing.advertiser_type,
        "advertiser_name": listing.advertiser_name,
        "visibility": listing.visibility,
        "contract": listing.contract,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
    # Cerca esistente per decidere INSERT vs UPDATE con count
    existing = (
        sb.table("listings")
        .select("id, scraped_count")
        .eq("portal", listing.portal)
        .eq("external_id", listing.external_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        payload["scraped_count"] = (row["scraped_count"] or 0) + 1
        res = (
            sb.table("listings")
            .update(payload)
            .eq("id", row["id"])
            .execute()
        )
        return {"action": "updated", "id": row["id"]}
    res = sb.table("listings").insert(payload).execute()
    return {"action": "inserted", "id": res.data[0]["id"]}


# ============================================================================
# CONTACTS
# ============================================================================

def get_or_create_contact(
    sb: Client,
    *,
    phone_raw: Optional[str] = None,
    email_raw: Optional[str] = None,
    display_name: Optional[str] = None,
    kind: Optional[str] = None,
    source: str = "advertiser",
) -> Optional[dict]:
    """Dedup su phone_e164 OR email. Restituisce il record o None se nessun
    identificatore valido.
    """
    phone = normalize_phone_it(phone_raw)
    email = normalize_email(email_raw)
    if not phone and not email:
        return None

    # Cerca per phone OR email. NB: i kwargs di _merge_contact devono usare i
    # nomi delle COLONNE DB (phone_e164, email, display_name, kind).
    query = sb.table("contacts").select("*")
    if phone and email:
        # cerco prima per phone (più stabile), fallback email
        q = query.eq("phone_e164", phone).limit(1).execute()
        if q.data:
            return _merge_contact(sb, q.data[0], phone_e164=phone, email=email,
                                  display_name=display_name, kind=kind)
        q = sb.table("contacts").select("*").eq("email", email).limit(1).execute()
        if q.data:
            return _merge_contact(sb, q.data[0], phone_e164=phone, email=email,
                                  display_name=display_name, kind=kind)
    elif phone:
        q = query.eq("phone_e164", phone).limit(1).execute()
        if q.data:
            return _merge_contact(sb, q.data[0], phone_e164=phone,
                                  display_name=display_name, kind=kind)
    elif email:
        q = query.eq("email", email).limit(1).execute()
        if q.data:
            return _merge_contact(sb, q.data[0], email=email,
                                  display_name=display_name, kind=kind)

    # INSERT
    payload = {
        "phone_e164": phone,
        "email": email,
        "display_name": display_name,
        "kind": kind,
        "source": source,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    res = sb.table("contacts").insert(payload).execute()
    return res.data[0]


def _merge_contact(sb: Client, existing: dict, **new_fields) -> dict:
    """Aggiorna campi mancanti del contact esistente (no overwrite di valori
    già presenti) + bump last_seen_at.
    """
    updates: dict = {"last_seen_at": datetime.now(timezone.utc).isoformat()}
    for k, v in new_fields.items():
        if v is None:
            continue
        if existing.get(k) in (None, "") and existing.get(k) != v:
            updates[k] = v
    res = sb.table("contacts").update(updates).eq("id", existing["id"]).execute()
    return res.data[0] if res.data else existing


# ============================================================================
# LISTING ↔ CONTACT
# ============================================================================

def link_listing_contact(
    sb: Client, listing_id: int, contact_id: int, role: str = "advertiser"
) -> dict:
    """Idempotente: la PK include (listing_id, contact_id, role), upsert no-op
    se esiste.
    """
    payload = {
        "listing_id": listing_id,
        "contact_id": contact_id,
        "role": role,
    }
    res = (
        sb.table("listing_contacts")
        .upsert(payload, on_conflict="listing_id,contact_id,role")
        .execute()
    )
    return res.data[0] if res.data else payload


# ============================================================================
# OUTREACH GATE (cuore della logica anti-doppio-contatto)
# ============================================================================

def can_outreach(sb: Client, contact_id: int, channel: str) -> tuple[bool, str]:
    """Decide se è lecito contattare il contact su quel canale.

    Restituisce (allowed, reason).

    Blocchi (in ordine):
      1. contact.opted_out_at IS NOT NULL  → mai più, qualunque canale
      2. contact.do_not_contact = true     → manuale
      3. esiste già outreach_log per (contact_id, channel) negli ultimi
         OUTREACH_COOLOFF_DAYS con status in (queued/sent/delivered/replied)
    """
    c = (
        sb.table("contacts")
        .select("opted_out_at, do_not_contact")
        .eq("id", contact_id)
        .single()
        .execute()
    )
    if not c.data:
        return (False, "contact_not_found")
    if c.data.get("opted_out_at"):
        return (False, "opted_out")
    if c.data.get("do_not_contact"):
        return (False, "do_not_contact_flag")

    since = (
        datetime.now(timezone.utc) - timedelta(days=OUTREACH_COOLOFF_DAYS)
    ).isoformat()
    prior = (
        sb.table("outreach_log")
        .select("id, status, sent_at, queued_at")
        .eq("contact_id", contact_id)
        .eq("channel", channel)
        .in_("status", ["queued", "sent", "delivered", "replied"])
        .gte("queued_at", since)
        .limit(1)
        .execute()
    )
    if prior.data:
        return (False, f"already_contacted_within_{OUTREACH_COOLOFF_DAYS}d")
    return (True, "ok")


def log_outreach(
    sb: Client,
    *,
    contact_id: int,
    listing_id: Optional[int],
    channel: str,
    status: str,
    template_id: Optional[str] = None,
    message: Optional[str] = None,
    provider_id: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    payload = {
        "contact_id": contact_id,
        "listing_id": listing_id,
        "channel": channel,
        "status": status,
        "template_id": template_id,
        "message": message,
        "provider_id": provider_id,
        "error": error,
    }
    if status in ("sent", "delivered"):
        payload["sent_at"] = datetime.now(timezone.utc).isoformat()
    res = sb.table("outreach_log").insert(payload).execute()
    return res.data[0]


def mark_opted_out(sb: Client, contact_id: int) -> None:
    """Segna il contact come opt-out: mai più outreach su nessun canale."""
    sb.table("contacts").update(
        {"opted_out_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", contact_id).execute()


# ============================================================================
# Sync orchestrator: dato un Listing parsato, fa tutto.
# ============================================================================

def sync_listing_with_contacts(sb: Client, listing: Listing) -> dict:
    """Upsert listing + crea/aggiorna contatti advertiser + linka.

    Restituisce un mini-report per logging.
    """
    listing_res = upsert_listing(sb, listing)
    listing_id = listing_res["id"]
    contacts_made: list[int] = []

    # 1) Telefoni esposti dall'advertiser
    for phone in listing.phones:
        c = get_or_create_contact(
            sb,
            phone_raw=phone,
            display_name=listing.advertiser_name,
            kind=listing.advertiser_type,
            source="advertiser",
        )
        if c:
            link_listing_contact(sb, listing_id, c["id"])
            contacts_made.append(c["id"])

    # 2) Telefoni estratti dal testo (più rari ma utili per privati)
    for phone in listing.raw_phones_in_text:
        c = get_or_create_contact(
            sb, phone_raw=phone,
            display_name=listing.advertiser_name,
            kind=listing.advertiser_type, source="text",
        )
        if c:
            link_listing_contact(sb, listing_id, c["id"])
            contacts_made.append(c["id"])

    # 3) Email estratte dal testo
    for email in listing.raw_emails_in_text:
        c = get_or_create_contact(
            sb, email_raw=email,
            display_name=listing.advertiser_name,
            kind=listing.advertiser_type, source="text",
        )
        if c:
            link_listing_contact(sb, listing_id, c["id"])
            contacts_made.append(c["id"])

    return {
        "listing_action": listing_res["action"],
        "listing_id": listing_id,
        "contacts_linked": len(set(contacts_made)),
    }
