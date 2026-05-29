"""Outreach engine (Step 6, dry-run-first).

Responsabilità:
  - compose_sms(listing, contact) → testo personalizzato (template fisso)
  - prepare_batch(sb, ...)        → seleziona contatti contattabili
  - queue_outreach(...)           → applica gate + scrive in outreach_log
                                    con status='queued' (no invio)
  - send_via_twilio(...)          → STUB: implementato quando Paolo
                                    registra Twilio. Cambia 'queued'→'sent'.

Politica:
  - Target di default: PRIVATI (kind='private'), non agenzie.
  - Gate anti-doppio-contatto: gestita da src.db.can_outreach().
  - Tutti i messaggi includono opt-out STOP (GDPR art. 130).
  - ASCII-safe per evitare UCS-2 encoding (SMS più corti / più costosi).
"""

from __future__ import annotations

from typing import Optional

from supabase import Client

from src.db import can_outreach, log_outreach
from src.models import Listing

# ====================================================================
# Template messaggio (singolo SMS, ~160 char ASCII)
# ====================================================================

SMS_TEMPLATE = (
    "Ciao{name_part}, ho visto il tuo annuncio{zone_part} su {portal_name}. "
    "Mi occupo di gestione affitti a medio termine a Milano: "
    "canone +30%, contratti 1-12 mesi, gestione totale. "
    "Se ti interessa una valutazione gratuita scrivimi. "
    "Paolo Vailati. "
    "STOP per non ricevere altri SMS."
)

PORTAL_NAMES = {
    "immobiliare": "Immobiliare.it",
    "idealista": "Idealista",
}


def _asciify(s: str) -> str:
    """Sostituisce accenti italiani con equivalenti ASCII per restare in
    GSM-7 (1 SMS = 160 char invece di 70 in UCS-2).
    """
    if not s:
        return ""
    mapping = str.maketrans({
        "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
        "À": "A", "È": "E", "É": "E", "Ì": "I", "Ò": "O", "Ù": "U",
        "’": "'", "‘": "'", "“": '"', "”": '"',
    })
    return s.translate(mapping)


def compose_sms(listing: Listing, contact: Optional[dict] = None) -> str:
    """Genera il testo SMS personalizzato.

    `contact` è il record DB del contact (per name); può essere None
    (allora usa advertiser_name del listing).
    """
    name = (contact or {}).get("display_name") or listing.advertiser_name or ""
    # primo nome only (es. "Marino Rossi" → "Marino")
    first_name = name.split()[0] if name else ""
    name_part = f" {first_name}" if first_name else ""

    zone = listing.microzone or listing.macrozone or listing.address or ""
    zone_part = f" in {zone}" if zone else ""

    portal_name = PORTAL_NAMES.get(listing.portal, listing.portal)

    msg = SMS_TEMPLATE.format(
        name_part=name_part, zone_part=zone_part, portal_name=portal_name
    )
    return _asciify(msg)


# ====================================================================
# Batch preparation
# ====================================================================

def prepare_batch(
    sb: Client,
    *,
    only_privates: bool = True,
    only_with_phone: bool = True,
    channel: str = "sms",
    limit: int = 50,
) -> list[dict]:
    """Restituisce una lista di dict {contact, listing, can, reason} per i
    contatti candidati all'invio.

    Non scrive in DB. La decisione di accodare l'invio è in `queue_outreach`.
    """
    # 1) Query contacts privati con telefono
    q = sb.table("contacts").select("*")
    if only_privates:
        q = q.eq("kind", "private")
    if only_with_phone:
        q = q.not_.is_("phone_e164", "null")
    q = q.is_("opted_out_at", "null").eq("do_not_contact", False)
    contacts = q.limit(limit * 3).execute().data  # ne prendo qualcuno in più

    candidates: list[dict] = []
    for c in contacts:
        # gate
        ok, reason = can_outreach(sb, c["id"], channel)
        if not ok:
            candidates.append({"contact": c, "listing": None,
                               "can": False, "reason": reason})
            continue
        # trovo il listing più recente legato a questo contact
        link = (
            sb.table("listing_contacts")
            .select("listing_id, listings(*)")
            .eq("contact_id", c["id"])
            .limit(1)
            .execute()
        )
        listing_dict = link.data[0]["listings"] if link.data else None
        candidates.append({"contact": c, "listing": listing_dict,
                           "can": True, "reason": "ok"})
        if sum(1 for x in candidates if x["can"]) >= limit:
            break
    return candidates


# ====================================================================
# Queue / send
# ====================================================================

def queue_outreach(
    sb: Client,
    contact: dict,
    listing_dict: Optional[dict],
    channel: str = "sms",
    template_id: str = "v1",
) -> Optional[dict]:
    """Compone il messaggio + applica gate + scrive in outreach_log con
    status='queued'. Non invia: l'invio sarà fatto dal provider step.
    """
    ok, reason = can_outreach(sb, contact["id"], channel)
    if not ok:
        return None
    if listing_dict:
        listing_obj = Listing(
            portal=listing_dict.get("portal", "?"),
            external_id=listing_dict.get("external_id", "?"),
            url=listing_dict.get("url", ""),
            title=listing_dict.get("title"),
            advertiser_name=listing_dict.get("advertiser_name"),
            macrozone=listing_dict.get("macrozone"),
            microzone=listing_dict.get("microzone"),
            address=listing_dict.get("address"),
        )
    else:
        listing_obj = Listing(portal="?", external_id="?", url="")
    msg = compose_sms(listing_obj, contact)
    listing_id = listing_dict.get("id") if listing_dict else None
    return log_outreach(
        sb,
        contact_id=contact["id"],
        listing_id=listing_id,
        channel=channel,
        status="queued",
        template_id=template_id,
        message=msg,
    )


def send_via_twilio(*args, **kwargs):
    """STUB. Implementato quando Paolo registra Twilio."""
    raise NotImplementedError(
        "Twilio non ancora configurato. Vedi .env TWILIO_* keys e Step 7."
    )
