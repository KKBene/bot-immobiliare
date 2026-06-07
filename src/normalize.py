"""Normalizzazione contatti italiani per dedup robusta.

Regola chiave: due rappresentazioni dello stesso numero/email devono produrre
la stessa stringa, altrimenti la unique constraint fallisce a fare dedup.
"""

from __future__ import annotations

import re
from typing import Optional

_DIGITS_RE = re.compile(r"\D+")


def normalize_phone_it(raw: Optional[str]) -> Optional[str]:
    """Restituisce il numero in formato E.164 italiano (+39...) o None.

    Casi gestiti:
      '02 8736 4229'       -> '+390287364229'   (fisso)
      '+39 02 8736 4229'   -> '+390287364229'
      '0039 333 1234567'   -> '+393331234567'
      '333 1234567'        -> '+393331234567'   (cellulare, 10 cifre)
      '3331234567'         -> '+393331234567'
      '+393331234567'      -> '+393331234567'
      'tel: 333.12.34.567' -> '+393331234567'
      ''                   -> None
      'abc'                -> None
    """
    if not raw:
        return None
    digits = _DIGITS_RE.sub("", raw)
    if not digits:
        return None

    # Rimuovi prefisso internazionale italiano espresso come 0039 / 39
    if digits.startswith("0039"):
        digits = digits[4:]
    elif digits.startswith("39") and len(digits) >= 11:
        # rischio: numeri che iniziano per 39 senza essere prefisso (raro per IT)
        digits = digits[2:]

    # Numeri fissi italiani: iniziano con 0 (es. 02 Milano)
    # Cellulari: iniziano con 3, 9-10 cifre
    if not digits:
        return None

    if len(digits) < 8 or len(digits) > 11:
        # Fuori range plausibile per IT
        return None

    return "+39" + digits


def normalize_email(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    e = raw.strip().lower()
    # validazione minima
    if "@" not in e or "." not in e.split("@")[-1]:
        return None
    return e


# Pattern molto permissivo per catturare numeri italiani anche OFFUSCATI:
# - 333 1234567
# - 333.12.34.567
# - 3.3.3.1.2.3.4.5.6.7    ← tipico "anti-bot" dei privati
# - +39 333 1234567
# - 0039 333 1234567
# - 02-87364229
# Strategia: cattura sequenze di cifre+separatori ammessi (.,-/spazi),
# poi normalize_phone_it() ripulisce e valida la lunghezza.
_PHONE_CANDIDATE_RE = re.compile(
    r"(?:\+?39[\s.\-]?|0039[\s.\-]?)?"   # prefisso opzionale
    r"\d(?:[\s.\-/ ]?\d){7,13}"      # 8-14 cifre con separatori opzionali
)


# ============================================================================
# Estrazione spese condominiali
# ============================================================================
#
# Italiano vario: "spese condo", "spese condominiali", "+ Euro X spese",
# "+50€/mese", "150€ di condo", ecc.
# La regex cerca un numero a 2-4 cifre vicino a un token spese/condo,
# poi normalize_expense_eur() valida il range plausibile (10-1500 €/mese).

_EXPENSES_PATTERNS = [
    # "spese condo(miniali?) X" / "spese di Y €"
    re.compile(
        r"spes[ae](?:\s+(?:di|per|condo[a-z]*))?\s+(?:euro\s+)?€?\s*(\d{2,4})",
        re.IGNORECASE,
    ),
    # "X € spese condo(miniali?)" / "X di spese"
    re.compile(
        r"(?:euro\s+)?€?\s*(\d{2,4})\s*€?\s*(?:di\s+)?spes[ae]\s+(?:condo[a-z]*)?",
        re.IGNORECASE,
    ),
    # "+ Euro X" / "+ X € spese"
    re.compile(
        r"\+\s*(?:euro\s+|€\s*)?(\d{2,4})\s*€?\s*(?:di\s+spese|spese|condo)",
        re.IGNORECASE,
    ),
    # "X € di condominio" / "condo X €"
    re.compile(
        r"condo[a-z]*\s+(?:di\s+)?€?\s*(\d{2,4})",
        re.IGNORECASE,
    ),
]


def extract_expenses_eur(text: Optional[str]) -> Optional[int]:
    """Cerca le spese condominiali mensili in un testo libero IT.

    Restituisce int (€/mese) o None se non trova nulla di plausibile.
    Range valido: 10-1500 €/mese (filtra anni/CAP/codici).
    """
    if not text:
        return None
    candidates: list[int] = []
    for pat in _EXPENSES_PATTERNS:
        for m in pat.finditer(text):
            try:
                v = int(m.group(1))
                if 10 <= v <= 1500:
                    candidates.append(v)
            except (ValueError, IndexError):
                continue
    return candidates[0] if candidates else None


# ============================================================================
# Parsing data di pubblicazione (Idealista pattern relativo/assoluto)
# ============================================================================

_MONTH_IT = {
    "gennaio": 1, "gen": 1,
    "febbraio": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4,
    "maggio": 5, "mag": 5,
    "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7,
    "agosto": 8, "ago": 8,
    "settembre": 9, "set": 9, "sett": 9,
    "ottobre": 10, "ott": 10,
    "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}


def parse_italian_relative_date(text: Optional[str]) -> Optional[str]:
    """Parsifica espressioni di data IT (Idealista listing card) in ISO UTC.

    Formati supportati:
      "1 minuto" / "5 minuti"          → now() - X minuti
      "1 ora" / "3 ore"                → now() - X ore
      "1 giorno" / "2 giorni"          → now() - X giorni
      "1 settimana" / "2 settimane"    → now() - 7×N giorni
      "1 mese" / "2 mesi"              → now() - 30×N giorni
      "15 maggio"                      → 15/05/anno-corrente
      "1 giugno 2025"                  → 1/06/2025
      "1 minuto" / "ieri" / "oggi"     → casi speciali

    Restituisce stringa ISO 8601 UTC o None.
    """
    if not text:
        return None
    from datetime import datetime, timedelta, timezone

    t = text.strip().lower()
    now = datetime.now(timezone.utc)

    # casi speciali
    if t in ("oggi", "appena pubblicato"):
        return now.isoformat()
    if t == "ieri":
        return (now - timedelta(days=1)).isoformat()

    # 5 minuti / 1 minuto
    m = re.match(r"(\d+)\s*minut[oi]", t)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).isoformat()
    # 5 ore / 1 ora
    m = re.match(r"(\d+)\s*or[ea]", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()
    # 5 giorni / 1 giorno
    m = re.match(r"(\d+)\s*giorn[oi]", t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()
    # 1 settimana / 2 settimane
    m = re.match(r"(\d+)\s*settiman[ae]", t)
    if m:
        return (now - timedelta(days=7 * int(m.group(1)))).isoformat()
    # 1 mese / 2 mesi
    m = re.match(r"(\d+)\s*mes[ei]", t)
    if m:
        return (now - timedelta(days=30 * int(m.group(1)))).isoformat()

    # "15 maggio [2025]"
    m = re.match(r"(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", t)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        year = int(m.group(3)) if m.group(3) else now.year
        month = _MONTH_IT.get(month_name) or _MONTH_IT.get(month_name[:3])
        if month and 1 <= day <= 31:
            try:
                dt = datetime(year, month, day, tzinfo=timezone.utc)
                # Se la data sembra "futura" (es. settembre 2026 quando siamo a
                # giugno 2026), probabilmente è dell'anno prima.
                if dt > now + timedelta(days=30):
                    dt = datetime(year - 1, month, day, tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass

    return None


def find_phones_in_text(text: Optional[str]) -> list[str]:
    """Estrae da `text` tutti i numeri italiani validi, anche quelli
    offuscati con separatori tra ogni cifra (3.3.3.1.2.3 ecc).

    Restituisce una lista di E.164 unici, già normalizzati.
    Casi NON validi (CAP, anni, codici fiscali) vengono scartati grazie
    a normalize_phone_it() che enforce 8-11 cifre dopo prefisso.
    """
    if not text:
        return []
    out: list[str] = []
    seen = set()
    for m in _PHONE_CANDIDATE_RE.finditer(text):
        candidate = m.group()
        e164 = normalize_phone_it(candidate)
        if e164 and e164 not in seen:
            # Filtro extra: deve cominciare con +39 e avere 11-13 cifre totali
            # (cell IT: 10 cifre, fisso: 9-11 cifre)
            digits_after_prefix = e164[3:]  # rimuovo '+39'
            if 9 <= len(digits_after_prefix) <= 11:
                # Cell: deve iniziare con 3
                # Fisso: deve iniziare con 0
                if digits_after_prefix[0] in ("3", "0"):
                    out.append(e164)
                    seen.add(e164)
    return out
