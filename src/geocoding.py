"""Geocoding indirizzi via Nominatim (OpenStreetMap).

Gratuito, no API key, rate limit 1 req/sec come da ToS.

Esposto in 2 modi:
  - `geocode_address(address, zone, city)` → (lat, lon) | None
    funzione pura, con cache in memoria per non richiamare due volte
    lo stesso indirizzo nel ciclo
  - `geocode_listing_inplace(sb, listing)` → True/False
    cerca le coordinate e SCRIVE su DB se trovate. Idempotente.

Usato sia dal cycle (inline, mentre scopre nuovi annunci) sia dallo
script batch `scripts/geocode_listings.py` per il backfill.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Optional, Tuple

import requests

from src.models import Listing

logger = logging.getLogger("geocoding")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "BOT_IMMOBILIARE/1.0 (kamalbene40@gmail.com)"
# Bounding box Milano allargato (city + hinterland stretto)
MILANO_BBOX = (45.3, 8.9, 45.6, 9.4)  # lat_min, lon_min, lat_max, lon_max
# Sleep minimo tra chiamate (Nominatim 1 req/sec policy)
_RATE_LIMIT_S = 1.05
_last_call_ts = [0.0]


def _respect_rate_limit() -> None:
    elapsed = time.time() - _last_call_ts[0]
    if elapsed < _RATE_LIMIT_S:
        time.sleep(_RATE_LIMIT_S - elapsed)
    _last_call_ts[0] = time.time()


@lru_cache(maxsize=2048)
def _query_nominatim(q: str) -> Optional[Tuple[float, float]]:
    """Una singola query Nominatim, con rate-limit + cache lru.

    Restituisce (lat, lon) se il primo risultato è dentro la bbox Milano,
    altrimenti None.
    """
    _respect_rate_limit()
    try:
        r = requests.get(
            NOMINATIM,
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "it"},
            headers={"User-Agent": UA, "Accept-Language": "it-IT,it"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        lat_min, lon_min, lat_max, lon_max = MILANO_BBOX
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return (lat, lon)
        return None
    except Exception as e:
        logger.warning(f"nominatim error for {q!r}: {e}")
        return None


def geocode_address(
    address: Optional[str],
    zone: Optional[str] = None,
    city: str = "Milano",
) -> Optional[Tuple[float, float]]:
    """Restituisce (lat, lon) per un indirizzo IT, o None se non trovabile.

    Prova progressivamente query più generiche.
    """
    candidates = []
    if address and zone:
        candidates.append(f"{address}, {zone}, {city}, Italia")
    if address:
        candidates.append(f"{address}, {city}, Italia")
    if zone:
        candidates.append(f"{zone}, {city}, Italia")
    for q in candidates:
        coords = _query_nominatim(q)
        if coords:
            return coords
    return None


def geocode_listing_inplace(sb, listing: Listing) -> bool:
    """Geocodifica un Listing e aggiorna `latitude`/`longitude` sulla riga
    DB corrispondente. No-op se l'indirizzo manca.

    Idempotente: se la riga ha già le coordinate, restituisce True senza
    chiamare Nominatim.
    """
    if listing.latitude and listing.longitude:
        return True
    if not (listing.address or listing.microzone):
        return False
    coords = geocode_address(listing.address, listing.microzone, listing.city or "Milano")
    if not coords:
        return False
    lat, lon = coords
    listing.latitude = lat
    listing.longitude = lon
    # Aggiorna la riga in listings
    try:
        sb.table("listings").update(
            {"latitude": lat, "longitude": lon}
        ).eq("portal", listing.portal).eq("external_id", listing.external_id).execute()
        return True
    except Exception as e:
        logger.warning(f"db update geocoding fail for {listing.external_id}: {e}")
        return False
