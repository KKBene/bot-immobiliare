"""Step 6 — Outreach engine in dry-run.

Uso:
    python scripts/run_step6.py              # solo simulazione, niente DB
    python scripts/run_step6.py --queue      # scrive 'queued' in outreach_log
    python scripts/run_step6.py --limit 10
    python scripts/run_step6.py --include-agencies   # default privates only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import client  # noqa: E402
from src.outreach import compose_sms, prepare_batch, queue_outreach  # noqa: E402
from src.models import Listing  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--queue", action="store_true",
                   help="Scrivi i messaggi in outreach_log come queued")
    p.add_argument("--include-agencies", action="store_true")
    p.add_argument("--channel", default="sms")
    args = p.parse_args()

    sb = client()
    batch = prepare_batch(
        sb,
        only_privates=not args.include_agencies,
        only_with_phone=True,
        channel=args.channel,
        limit=args.limit,
    )

    sendable = [b for b in batch if b["can"]]
    blocked = [b for b in batch if not b["can"]]

    print(f"=== BATCH PREPARATO (channel={args.channel}) ===")
    print(f"  candidati totali: {len(batch)}")
    print(f"  inviabili:        {len(sendable)}")
    print(f"  bloccati:         {len(blocked)}")
    if blocked:
        from collections import Counter
        reasons = Counter(b["reason"] for b in blocked)
        print(f"  motivi blocchi:   {dict(reasons)}")

    print(f"\n=== ESEMPI MESSAGGI (primi {min(5, len(sendable))}) ===")
    for i, b in enumerate(sendable[:5], 1):
        c = b["contact"]
        l = b["listing"]
        listing_obj = Listing(
            portal=(l or {}).get("portal", "?"),
            external_id=(l or {}).get("external_id", "?"),
            url=(l or {}).get("url", ""),
            title=(l or {}).get("title"),
            advertiser_name=(l or {}).get("advertiser_name"),
            macrozone=(l or {}).get("macrozone"),
            microzone=(l or {}).get("microzone"),
            address=(l or {}).get("address"),
        )
        msg = compose_sms(listing_obj, c)
        print(f"\n  [{i}] → {c.get('phone_e164')} ({c.get('display_name') or '?'})")
        print(f"      annuncio: {(l or {}).get('url', '?')}")
        print(f"      messaggio ({len(msg)} char):")
        print(f"      {msg!r}")

    if args.queue:
        print(f"\n=== QUEUE ===")
        queued = 0
        for b in sendable:
            res = queue_outreach(sb, b["contact"], b["listing"], channel=args.channel)
            if res:
                queued += 1
        print(f"  Messaggi accodati in outreach_log (status=queued): {queued}")
    else:
        print(f"\n  (Dry-run: niente scritto in DB. Aggiungi --queue per accodare.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
