"""Dataclass per un annuncio normalizzato (indipendente dal portale)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Listing:
    # identificatori
    portal: str                       # "immobiliare" | "idealista"
    external_id: str                  # id annuncio sul portale
    url: str                          # url canonica annuncio

    # contenuto
    title: Optional[str] = None
    description: Optional[str] = None
    price_eur: Optional[int] = None     # canone mensile in €
    expenses_eur: Optional[int] = None  # spese condominiali mensili in €
    total_eur: Optional[int] = None     # price + expenses (canone "tutto incluso")
    surface_m2: Optional[int] = None
    rooms: Optional[str] = None         # "4" o "4+" (può essere stringa nei portali)
    bathrooms: Optional[str] = None
    floor: Optional[str] = None
    typology: Optional[str] = None      # "Appartamento", "Bilocale", ...

    # localizzazione
    address: Optional[str] = None
    city: Optional[str] = None
    macrozone: Optional[str] = None   # es. "Fiera, Sempione, City Life"
    microzone: Optional[str] = None   # es. "De Angeli"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # advertiser
    advertiser_type: Optional[str] = None    # "agency" | "private"
    advertiser_name: Optional[str] = None
    phones: list[str] = field(default_factory=list)   # da advertiser, già esposti

    # contatti grezzi (estratti da testo/descrizione, validati dopo)
    raw_phones_in_text: list[str] = field(default_factory=list)
    raw_emails_in_text: list[str] = field(default_factory=list)

    # meta
    visibility: Optional[str] = None         # "supervetrina" | "standard" | ...
    contract: Optional[str] = None           # "rent" | "sale"
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)
