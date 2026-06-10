"""Sync degli annunci privati su Google Sheet (per Paolo Vailati).

L'utente segna manualmente la colonna 'Contattato' (Sì/No) per gestire
l'outreach. Il bot:
  - aggiunge righe per NUOVI privati (no duplicati: dedup su `url`)
  - aggiorna campi modificati per privati esistenti (es. price cambiato)
  - NON tocca la colonna 'Contattato' (preserva l'editing manuale)

DUE METODI DI AUTH supportati (in ordine di priorità):

  1. Apps Script Web App URL (più semplice — niente Google Cloud)
       env: `GOOGLE_SHEETS_WEBHOOK_URL`
       L'utente deploya nel foglio uno Apps Script pubblico, il bot manda
       POST JSON. Vedi docs/GOOGLE_SHEET.md.

  2. Service Account JSON (più strutturato)
       env: `GOOGLE_SHEETS_CREDENTIALS_JSON` o `GOOGLE_SHEETS_CREDENTIALS_FILE`
       + `GOOGLE_SHEET_ID`
       Account google cloud + service account + condivisione foglio.

Disabilitato (no-op) se nessuno dei due è configurato.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("sheets")

# Colonne del worksheet "Privati" (ordine = colonne A, B, C, ...)
COLUMNS = [
    "URL",
    "Portale",
    "Status",          # active = ancora sul portale  |  removed = sparito da >48h
    "Inserzionista",
    "Telefono",
    "Zona",
    "Prezzo €/mese",
    "Spese €/mese",
    "Totale €/mese",
    "Mq",
    "Locali",
    "Indirizzo",
    "Pubblicato il",   # data pubblicazione sul portale (≠ Visto il)
    "Visto il",        # quando il bot l'ha intercettato la prima volta
    "Contattato",      # Sì/No, modificata MANUALMENTE da Paolo
]
URL_COL_IDX = 0       # url è la chiave di dedup
CONTACTED_COL_IDX = COLUMNS.index("Contattato")
# Colonne user-edited: il bot NON le sovrascrive mai in update
# (Apps Script Webhook gestisce questa logica server-side; per il fallback
# Service Account, ci pensa _sync_via_service_account a saltarle).
USER_EDITED_COLS = ("Contattato", "Status")
USER_EDITED_IDX = tuple(COLUMNS.index(c) for c in USER_EDITED_COLS)

SHEET_TAB_NAME = "Privati"


def _webhook_url() -> Optional[str]:
    """Apps Script Web App URL se configurato."""
    return os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL")


def _config() -> Optional[tuple[dict, str]]:
    """Ritorna (credentials_dict, sheet_id) o None se Service Account
    non configurato."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        return None
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    creds_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
    if creds_json:
        try:
            return (json.loads(creds_json), sheet_id)
        except json.JSONDecodeError as e:
            logger.warning(f"GOOGLE_SHEETS_CREDENTIALS_JSON malformato: {e}")
            return None
    if creds_file and os.path.exists(creds_file):
        try:
            with open(creds_file) as f:
                return (json.load(f), sheet_id)
        except Exception as e:
            logger.warning(f"Impossibile leggere {creds_file}: {e}")
            return None
    return None


def is_enabled() -> bool:
    """True se almeno uno dei due metodi è configurato."""
    return bool(_webhook_url() or _config())


def _client():
    """Autentica gspread via service account. Solleva se mal configurato."""
    import gspread
    from google.oauth2.service_account import Credentials
    cfg = _config()
    if not cfg:
        raise RuntimeError("Google Sheets non configurato (vedi src/sheets.py)")
    creds_dict, sheet_id = cfg
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds), sheet_id


def _ensure_worksheet(sh, tab_name: str):
    """Restituisce il worksheet, lo crea con header se non esiste."""
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=2000, cols=len(COLUMNS) + 2)
        ws.append_row(COLUMNS, value_input_option="USER_ENTERED")
        # bold header
        ws.format(
            f"A1:{chr(64 + len(COLUMNS))}1",
            {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.95, "blue": 0.9}},
        )
        ws.freeze(rows=1)
    return ws


def _listing_row(listing: dict, contact_phone: Optional[str] = None,
                 contacted: str = "") -> list:
    """Costruisce la riga ordinata secondo COLUMNS."""
    seen = (listing.get("first_seen_at") or "")[:16].replace("T", " ")
    pub = (listing.get("published_at") or "")[:16].replace("T", " ")
    return [
        listing.get("url") or "",
        listing.get("portal") or "",
        listing.get("status") or "",
        listing.get("advertiser_name") or "",
        contact_phone or "",
        listing.get("microzone") or "",
        listing.get("price_eur") or "",
        listing.get("expenses_eur") or "",
        listing.get("total_eur") or "",
        listing.get("surface_m2") or "",
        listing.get("rooms") or "",
        listing.get("address") or "",
        pub,
        seen,
        contacted,
    ]


def _load_private_listings(sb, limit: int) -> tuple[list[dict], dict]:
    """Estrae TUTTI i privati attivi dal DB + mapping listing→phone.

    Ritorna (listings_list, listing_id_to_phone).
    NB: include anche privati SENZA phone (la colonna Telefono sarà vuota).

    IMPORTANTE: Supabase REST default ritorna max 1000 righe per query.
    Pre-filtriamo listing_contacts solo per gli ID privati, in chunk da 100.
    """
    # NB: includiamo ANCHE i listings con status='removed' — sono lead che
    # potrebbero ancora essere validi (proprietario contattabile anche dopo
    # che l'annuncio è sparito dal portale). La colonna 'Status' nel foglio
    # permette a Paolo di filtrarli a vista.
    listings_rows = (
        sb.table("listings")
        .select("id, url, portal, advertiser_name, microzone, address, "
                "price_eur, expenses_eur, total_eur, surface_m2, rooms, "
                "first_seen_at, published_at, status")
        .eq("advertiser_type", "private")
        .order("first_seen_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    if not listings_rows:
        return [], {}

    # Carica listing_contacts SOLO per i listing privati (chunk per evitare
    # URL troppo lunghi se ci sono moltissimi privati)
    listing_ids = [l["id"] for l in listings_rows]
    lc_rows: list = []
    for chunk_start in range(0, len(listing_ids), 100):
        chunk = listing_ids[chunk_start:chunk_start + 100]
        rs = (
            sb.table("listing_contacts")
            .select("listing_id, contact_id")
            .in_("listing_id", chunk)
            .execute()
            .data
        )
        lc_rows.extend(rs)

    contact_ids = list({r["contact_id"] for r in lc_rows})
    contacts_by_id: dict = {}
    for chunk_start in range(0, len(contact_ids), 100):
        chunk = contact_ids[chunk_start:chunk_start + 100]
        cs = (
            sb.table("contacts")
            .select("id, phone_e164, kind")
            .in_("id", chunk)
            .execute()
            .data
        )
        for c in cs:
            contacts_by_id[c["id"]] = c

    listing_to_phone: dict = {}
    for lc in lc_rows:
        c = contacts_by_id.get(lc["contact_id"])
        if c and c.get("kind") == "private" and c.get("phone_e164"):
            listing_to_phone.setdefault(lc["listing_id"], c["phone_e164"])

    return listings_rows, listing_to_phone


def _sync_via_webhook(listings_rows: list[dict], listing_to_phone: dict) -> dict:
    """Manda i listings al webhook Apps Script.

    Il payload è un JSON: {"columns": [...], "rows": [[...], ...]}
    L'Apps Script lato Google fa il merge per URL preservando 'Contattato'.
    """
    import requests
    url = _webhook_url()
    if not url:
        return {"added": 0, "updated": 0, "skipped": 0, "reason": "not_configured"}

    payload = {
        "columns": COLUMNS,
        "rows": [
            _listing_row(l, listing_to_phone.get(l["id"], ""))
            for l in listings_rows
            if l.get("url")
        ],
    }
    try:
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        body = r.json()
        return {
            "added": body.get("added", 0),
            "updated": body.get("updated", 0),
            "skipped": body.get("skipped", 0),
        }
    except Exception as e:
        logger.warning(f"Apps Script webhook fail: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "error": str(e)}


def _sync_via_service_account(listings_rows: list[dict],
                              listing_to_phone: dict) -> dict:
    """Sync via gspread + Service Account (fallback)."""
    client, sheet_id = _client()
    sh = client.open_by_key(sheet_id)
    ws = _ensure_worksheet(sh, SHEET_TAB_NAME)

    # Stato attuale del foglio (URL → riga#)
    existing = ws.get_all_values()
    url_to_row = {}
    if len(existing) >= 2:
        for idx, row in enumerate(existing[1:], start=2):
            if row and row[URL_COL_IDX]:
                url_to_row[row[URL_COL_IDX]] = idx

    added = updated = skipped = 0
    new_rows: list[list] = []
    updates: list = []

    for l in listings_rows:
        url = l.get("url")
        if not url:
            skipped += 1
            continue
        phone = listing_to_phone.get(l["id"], "")
        if url in url_to_row:
            updates.append((url_to_row[url], l, phone))
        else:
            new_rows.append(_listing_row(l, phone, contacted="No"))
            added += 1

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")

    if updates:
        cell_updates = []
        for row_idx, l, phone in updates:
            row = _listing_row(l, phone)
            for col_idx, val in enumerate(row):
                # Skip TUTTE le colonne user-edited (Contattato, Status)
                if col_idx in USER_EDITED_IDX:
                    continue
                if val == "":
                    continue
                col_letter = chr(65 + col_idx)
                cell_updates.append({
                    "range": f"{col_letter}{row_idx}",
                    "values": [[str(val)]],
                })
            updated += 1
        if cell_updates:
            ws.batch_update(cell_updates, value_input_option="USER_ENTERED")

    return {"added": added, "updated": updated, "skipped": skipped}


def sync_private_listings(sb, *, limit: int = 1000) -> dict:
    """Sincronizza TUTTI i privati attivi dal DB nel foglio Google.

    Include anche privati SENZA phone (colonna telefono vuota).
    Preserva la colonna 'Contattato' (modificata a mano dal cliente).

    Sceglie automaticamente Apps Script Webhook (preferito) o Service Account.
    Idempotente: dedup su URL.
    """
    if not is_enabled():
        logger.info("Google Sheets non configurato → skip sync")
        return {"added": 0, "updated": 0, "skipped": 0, "reason": "not_configured"}

    listings_rows, listing_to_phone = _load_private_listings(sb, limit)

    # Preferenza: webhook (più semplice da configurare per l'utente)
    if _webhook_url():
        result = _sync_via_webhook(listings_rows, listing_to_phone)
    else:
        result = _sync_via_service_account(listings_rows, listing_to_phone)

    logger.info(
        f"[sheets] {result.get('added', 0)} aggiunti, "
        f"{result.get('updated', 0)} aggiornati, "
        f"{result.get('skipped', 0)} skip "
        f"(privati totali: {len(listings_rows)})"
    )
    return result
