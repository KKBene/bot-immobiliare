"""Rapida vista dello stato DB."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.db import client


def main() -> None:
    sb = client()
    print("=== Stato DB ===")
    counts_cols = {
        "listings": "id",
        "contacts": "id",
        "listing_contacts": "listing_id",  # composite PK, no `id`
        "outreach_log": "id",
    }
    for table, col in counts_cols.items():
        n = sb.table(table).select(col, count="exact").limit(1).execute().count
        print(f"  {table:20} {n}")

    print("\n=== Per portale ===")
    for portal in ("idealista", "immobiliare"):
        n = sb.table("listings").select("id", count="exact").eq(
            "portal", portal
        ).limit(1).execute().count
        n_priv = (
            sb.table("listings").select("id", count="exact")
            .eq("portal", portal).eq("advertiser_type", "private")
            .limit(1).execute().count
        )
        n_active = (
            sb.table("listings").select("id", count="exact")
            .eq("portal", portal).eq("status", "active")
            .limit(1).execute().count
        )
        n_removed = (
            sb.table("listings").select("id", count="exact")
            .eq("portal", portal).eq("status", "removed")
            .limit(1).execute().count
        )
        print(f"  {portal:15} {n} totali ({n_active} active, {n_removed} removed), {n_priv} privati")

    print("\n=== Contatti per kind ===")
    for kind in ("private", "agency"):
        n = sb.table("contacts").select("id", count="exact").eq(
            "kind", kind
        ).limit(1).execute().count
        n_phone = (
            sb.table("contacts").select("id", count="exact")
            .eq("kind", kind).not_.is_("phone_e164", "null")
            .limit(1).execute().count
        )
        print(f"  {kind:10} {n} ({n_phone} con telefono)")

    print("\n=== Ultimi 15 privati con telefono ===")
    rows = (
        sb.table("contacts")
        .select("id, display_name, phone_e164, first_seen_at")
        .eq("kind", "private")
        .not_.is_("phone_e164", "null")
        .order("first_seen_at", desc=True)
        .limit(15)
        .execute()
        .data
    )
    for r in rows:
        ts = (r.get("first_seen_at") or "")[:16].replace("T", " ")
        print(f"  #{r['id']:>4}  {ts}  {(r['display_name'] or '?'):<25} {r['phone_e164']}")


if __name__ == "__main__":
    main()
