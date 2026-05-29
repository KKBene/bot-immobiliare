"""Run live: scarica la prima pagina Immobiliare Milano e mostra i risultati.

Uso:
    python scripts/run_step1.py
    python scripts/run_step1.py --save-fixture    # rigenera fixture per i test
    python scripts/run_step1.py --page 2
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Permette `python scripts/run_step1.py` senza installare il package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.immobiliare import ImmobiliareScraper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--city", default="milano")
    parser.add_argument("--save-fixture", action="store_true",
                        help="Salva l'HTML come fixture per i test")
    parser.add_argument("--show", type=int, default=3,
                        help="Quanti annunci stampare per esteso")
    args = parser.parse_args()

    scraper = ImmobiliareScraper(city=args.city)
    print(f"→ Fetch {scraper.list_url(args.page)}")
    html = scraper.fetch_list_html(page=args.page)
    print(f"  HTML scaricato ({len(html):,} char)")

    if args.save_fixture:
        path = ROOT / "tests" / "fixtures" / f"immobiliare_{args.city}_p{args.page}.html"
        path.write_text(html)
        print(f"  Fixture salvato in {path}")

    listings = ImmobiliareScraper.parse_listings(html)
    print(f"  Parsati {len(listings)} annunci\n")

    # Statistiche
    by_adv = Counter(l.advertiser_type for l in listings)
    with_phone = sum(1 for l in listings if l.phones)
    with_raw_phone = sum(1 for l in listings if l.raw_phones_in_text)
    with_raw_email = sum(1 for l in listings if l.raw_emails_in_text)
    prices = [l.price_eur for l in listings if l.price_eur]

    print("=== STATISTICHE ===")
    print(f"  Per inserzionista: {dict(by_adv)}")
    print(f"  Con telefono advertiser: {with_phone}/{len(listings)}")
    print(f"  Con telefono in testo:   {with_raw_phone}/{len(listings)}")
    print(f"  Con email in testo:      {with_raw_email}/{len(listings)}")
    if prices:
        print(f"  Prezzo: min={min(prices)}€  max={max(prices)}€  "
              f"mediana={sorted(prices)[len(prices)//2]}€")
    print()

    print(f"=== PRIMI {args.show} ANNUNCI ===")
    for l in listings[: args.show]:
        d = l.to_dict()
        # tronca description per leggibilità
        if d.get("description"):
            d["description"] = d["description"][:120] + "…"
        print(json.dumps(d, indent=2, ensure_ascii=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
