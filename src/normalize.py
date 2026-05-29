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
