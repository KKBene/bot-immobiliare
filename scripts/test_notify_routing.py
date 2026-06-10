"""Test di routing notifiche Telegram (per verificare i secret Actions).

Manda 2 messaggi:
  - 1 listing fittizio → kind='listing' (Paolo + cislyfree)
  - 1 anomalia fittizia → kind='anomaly' (solo cislyfree)

Uso:
    python scripts/test_notify_routing.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.health import Anomaly, notify_anomalies  # noqa: E402
from src.models import Listing  # noqa: E402
from src.notify import notify_new_private_listing  # noqa: E402


def main() -> int:
    print("Env presenti:")
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "TELEGRAM_CHAT_ID_LISTINGS", "TELEGRAM_CHAT_ID_ANOMALIES"):
        v = os.environ.get(k, "")
        if v:
            print(f"  {k} = {'SET ('+str(len(v))+' chars)' if 'TOKEN' in k else v}")
        else:
            print(f"  {k} = (vuoto)")

    listing = Listing(
        portal="idealista",
        external_id="TEST_ROUTING",
        url="https://www.idealista.it/immobile/TEST/",
        advertiser_type="private",
        advertiser_name="Routing Test",
        microzone="Sempione", city="Milano",
        price_eur=1234, surface_m2=42, rooms="2",
        phones=["+393331234567"],
    )
    print("\n→ Invio LISTING (atteso: Paolo + cislyfree)")
    ok_l = notify_new_private_listing(listing)
    print(f"   risultato: {ok_l}")

    anomalies = [
        Anomaly(level="WARN", code="routing_test",
                message="Test routing dal workflow Actions: deve arrivare SOLO a cislyfree."),
    ]
    print("\n→ Invio ANOMALY (atteso: solo cislyfree)")
    ok_a = notify_anomalies(anomalies, run_id=0)
    print(f"   risultato: {ok_a}")

    return 0 if (ok_l and ok_a) else 1


if __name__ == "__main__":
    raise SystemExit(main())
