"""Master script: un ciclo completo di scrape + sync + mark stale.

Paginazione DINAMICA: si ferma quando il backlog di una pagina è esaurito
(≥90% degli annunci già in DB). `--max-pages` è solo un safety cap.

Uso:
    python scripts/run_cycle.py                       # paginazione dinamica, max 15 pagine
    python scripts/run_cycle.py --max-pages 30        # alza il cap (catch-up iniziale)
    python scripts/run_cycle.py --city milano
    python scripts/run_cycle.py --stale-hours 72      # tolleranza più larga per stale
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline import DEFAULT_MAX_PAGES, run_cycle  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                   help="Safety cap su numero pagine (default %(default)s)")
    p.add_argument("--city", default="milano")
    p.add_argument("--stale-hours", type=int, default=48,
                   help="Marca 'removed' annunci non rivisti da > N ore")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stats = run_cycle(
        max_pages=args.max_pages,
        city=args.city,
        stale_hours=args.stale_hours,
    )
    print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False))

    portal_counts = stats.portal_counts or {}
    real_portals = {k: v for k, v in portal_counts.items() if not k.startswith("_")}
    both_failed = (
        real_portals
        and all(not (v.get("synced_new", 0) or v.get("touched_existing", 0))
                for v in real_portals.values())
        and stats.errors
    )
    return 1 if both_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
