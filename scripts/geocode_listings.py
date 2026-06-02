"""Backfill latitude/longitude su listings senza coordinate.

Adesso il geocoding gira ANCHE inline nella pipeline (vedi src/pipeline.py
+ src/geocoding.py), quindi questo script serve solo per:
  - backfill iniziale (annunci pre-feature)
  - re-geocoding selettivo (--force)

Uso:
    python scripts/geocode_listings.py
    python scripts/geocode_listings.py --limit 50
    python scripts/geocode_listings.py --force --portal idealista
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from src.db import client  # noqa: E402
from src.geocoding import geocode_address  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--portal", choices=("idealista", "immobiliare"), default=None)
    args = p.parse_args()

    sb = client()
    q = (
        sb.table("listings")
        .select("id, portal, external_id, address, microzone, city, latitude, longitude")
        .order("first_seen_at", desc=True)
    )
    if args.portal:
        q = q.eq("portal", args.portal)
    if not args.force:
        q = q.is_("latitude", "null")
    if args.limit:
        q = q.limit(args.limit)
    rows = q.execute().data

    print(f"→ {len(rows)} listings da geocodificare")
    ok = skip = fail = 0
    for i, row in enumerate(rows, 1):
        addr = row.get("address")
        zone = row.get("microzone")
        if not addr and not zone:
            skip += 1
            continue
        coords = geocode_address(addr, zone, row.get("city") or "Milano")
        if coords:
            lat, lon = coords
            sb.table("listings").update(
                {"latitude": lat, "longitude": lon}
            ).eq("id", row["id"]).execute()
            ok += 1
            print(f"  [{i:>3}/{len(rows)}] ✓ #{row['id']} {addr!r} → ({lat:.4f}, {lon:.4f})")
        else:
            fail += 1
            print(f"  [{i:>3}/{len(rows)}] ✗ #{row['id']} {addr!r}")

    print(f"\n=== Done ===\n  geocoded: {ok}\n  no input: {skip}\n  failed:   {fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
