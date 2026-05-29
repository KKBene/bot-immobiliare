"""Step 4 — Idealista API-based: scrape listing + enrich con detail API.

Uso:
    python scripts/run_step4.py                       # solo listing, no enrich
    python scripts/run_step4.py --enrich              # listing + API detail
    python scripts/run_step4.py --enrich --sync       # + upsert in Supabase
    python scripts/run_step4.py --enrich --limit 5    # solo primi N (test)
    python scripts/run_step4.py --save-fixture        # rigenera fixture
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.idealista import IdealistaScraper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--city", default="milano")
    parser.add_argument("--enrich", action="store_true",
                        help="Arricchisci con chiamate API detail (+telefono)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limita N annunci (utile per testare enrich)")
    parser.add_argument("--sleep", type=float, default=1.2)
    parser.add_argument("--save-fixture", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--show", type=int, default=2)
    args = parser.parse_args()

    scraper = IdealistaScraper(city=args.city)
    print(f"→ Fetch {scraper.list_url(args.page)}")
    html = scraper.fetch_list_html(page=args.page)
    print(f"  HTML scaricato ({len(html):,} char)")
    if args.save_fixture:
        path = ROOT / "tests" / "fixtures" / f"idealista_{args.city}_p{args.page}.html"
        path.write_text(html)
        print(f"  Fixture salvato in {path}")

    basics = IdealistaScraper.parse_list_basic(html)
    print(f"  Parsati {len(basics)} annunci base")

    if args.limit:
        basics = basics[: args.limit]

    listings = []
    if args.enrich:
        import time
        print(f"  Enrich via API (sleep {args.sleep}s)...")
        for i, b in enumerate(basics, 1):
            try:
                enriched = scraper.enrich_with_api(b)
                listings.append(enriched)
                tag = "🟢" if enriched.advertiser_type == "private" else "🔵"
                phone = enriched.phones[0] if enriched.phones else "—"
                print(f"  [{i:2d}/{len(basics)}] {tag} {enriched.advertiser_type:7} "
                      f"{enriched.advertiser_name or '?':<35} → {phone}")
            except Exception as e:
                print(f"  [{i:2d}/{len(basics)}] ⚠️  {b.external_id}: {e}")
                listings.append(b)
            if i < len(basics):
                time.sleep(args.sleep)
    else:
        listings = basics

    print()
    by_adv = Counter(l.advertiser_type for l in listings)
    with_phone = sum(1 for l in listings if l.phones)
    privates_with_phone = sum(
        1 for l in listings if l.advertiser_type == "private" and l.phones
    )
    print("=== STATISTICHE ===")
    print(f"  Per inserzionista: {dict(by_adv)}")
    print(f"  Con telefono advertiser: {with_phone}/{len(listings)}")
    print(f"  PRIVATI con telefono: {privates_with_phone}")

    if args.sync:
        from src.db import client, sync_listing_with_contacts
        sb = client()
        actions = Counter()
        for l in listings:
            r = sync_listing_with_contacts(sb, l)
            actions[r["listing_action"]] += 1
        print(f"\n  Sync → inseriti: {actions['inserted']}, aggiornati: {actions['updated']}")

    print(f"\n=== PRIMI {args.show} ANNUNCI ===")
    for l in listings[: args.show]:
        d = l.to_dict()
        if d.get("description"):
            d["description"] = d["description"][:120] + "…"
        print(json.dumps(d, indent=2, ensure_ascii=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
