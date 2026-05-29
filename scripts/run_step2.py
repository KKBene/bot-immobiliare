"""Step 2 — Scrape Immobiliare e upsert in Supabase con dedup.

Uso:
    python scripts/run_step2.py                  # fetch live e upsert
    python scripts/run_step2.py --use-fixture    # da fixture (no rete)
    python scripts/run_step2.py --pages 3        # multi-pagina

Stampa un report di quanti nuovi vs aggiornati e quanti contatti unici.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import client, sync_listing_with_contacts  # noqa: E402
from src.scrapers.immobiliare import ImmobiliareScraper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-fixture", action="store_true",
                        help="Usa l'HTML salvato in tests/fixtures/ (no rete)")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--city", default="milano")
    args = parser.parse_args()

    sb = client()
    scraper = ImmobiliareScraper(city=args.city)
    actions = Counter()
    total_listings = 0
    total_contact_links = 0

    for page in range(1, args.pages + 1):
        if args.use_fixture:
            fx = ROOT / "tests" / "fixtures" / f"immobiliare_{args.city}_p{page}.html"
            if not fx.exists():
                print(f"⚠️  Fixture mancante: {fx} — skip")
                continue
            html = fx.read_text()
            print(f"→ Pagina {page} da fixture ({len(html):,} char)")
        else:
            print(f"→ Pagina {page} live")
            html = scraper.fetch_list_html(page=page)

        listings = ImmobiliareScraper.parse_listings(html)
        print(f"  Parsati {len(listings)} annunci")

        for l in listings:
            report = sync_listing_with_contacts(sb, l)
            actions[report["listing_action"]] += 1
            total_listings += 1
            total_contact_links += report["contacts_linked"]

    print()
    print("=== REPORT SYNC ===")
    print(f"  Annunci processati:     {total_listings}")
    print(f"  Inseriti (nuovi):       {actions['inserted']}")
    print(f"  Aggiornati (rivisti):   {actions['updated']}")
    print(f"  Contatti linkati totali: {total_contact_links}")

    # Conteggi assoluti da DB
    n_listings = sb.table("listings").select("id", count="exact").execute()
    n_contacts = sb.table("contacts").select("id", count="exact").execute()
    n_links = sb.table("listing_contacts").select("listing_id", count="exact").execute()
    print()
    print("=== STATO DB ===")
    print(f"  listings:         {n_listings.count}")
    print(f"  contacts unici:   {n_contacts.count}")
    print(f"  listing_contacts: {n_links.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
