"""Backfill latitude/longitude su listings che ne sono privi (Idealista).

Strategia: Nominatim (OpenStreetMap) — gratis, no API key.
Rate limit 1 req/sec come da ToS Nominatim.

Uso:
    python scripts/geocode_listings.py                # geocodifica tutti i mancanti
    python scripts/geocode_listings.py --limit 30     # primi N (per testare)
    python scripts/geocode_listings.py --force        # rigeocodifica anche se già fatto
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.db import client  # noqa: E402

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "BOT_IMMOBILIARE/1.0 (kamalbene40@gmail.com)"


def geocode(address: str | None, zone: str | None, city: str = "Milano") -> tuple[float, float] | None:
    """Tenta 3 query in ordine di specificità."""
    queries = []
    if address:
        queries.append(f"{address}, {city}, Italia")
    if address and zone:
        queries.append(f"{address}, {zone}, {city}, Italia")
    if zone:
        queries.append(f"{zone}, {city}, Italia")
    queries.append(f"{city}, Italia")  # fallback estremo

    for q in queries:
        try:
            r = requests.get(
                NOMINATIM,
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "it"},
                headers={"User-Agent": UA, "Accept-Language": "it-IT,it"},
                timeout=15,
            )
            data = r.json() if r.status_code == 200 else []
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                # bbox Milano grande: lat 45.35-45.55, lon 9.0-9.30
                if 45.3 <= lat <= 45.6 and 8.9 <= lon <= 9.4:
                    return (lat, lon)
        except Exception as e:
            print(f"  ⚠️  geocode error for {q!r}: {e}")
        time.sleep(1.05)  # Nominatim rate limit
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    sb = client()
    q = (
        sb.table("listings")
        .select("id, portal, external_id, address, microzone, city, latitude, longitude")
        .order("first_seen_at", desc=True)
    )
    if not args.force:
        q = q.is_("latitude", "null")
    if args.limit:
        q = q.limit(args.limit)
    rows = q.execute().data

    print(f"→ {len(rows)} listings da geocodificare")
    ok = 0
    skip = 0
    fail = 0
    for i, row in enumerate(rows, 1):
        addr = row.get("address")
        zone = row.get("microzone")
        if not addr and not zone:
            skip += 1
            continue
        coords = geocode(addr, zone, row.get("city") or "Milano")
        if coords:
            lat, lon = coords
            sb.table("listings").update(
                {"latitude": lat, "longitude": lon}
            ).eq("id", row["id"]).execute()
            ok += 1
            print(f"  [{i:>3}/{len(rows)}] ✓ #{row['id']} {addr!r} → ({lat:.4f}, {lon:.4f})")
        else:
            fail += 1
            print(f"  [{i:>3}/{len(rows)}] ✗ #{row['id']} {addr!r} non trovato")

    print(f"\n=== Done ===\n  geocoded: {ok}\n  no input: {skip}\n  failed:   {fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
