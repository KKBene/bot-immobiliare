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
