"""Anomaly detection sui cycle runs + persistenza in DB.

Una "anomalia" è qualsiasi cosa che richiede attenzione umana:
  - portale fermo (last_seen > 24h fa)
  - cycle a 0 listings touchati (ne uno nuovo né uno rivisto)
  - >N errori in un cycle
  - circuit breaker rimasto aperto

Per ogni anomalia rilevata, mandiamo una notifica Telegram con livello
(WARN/CRITICAL) così Paolo può intervenire.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client

from src.notify import send_telegram

logger = logging.getLogger("health")

# Soglie configurabili
STALE_HOURS_THRESHOLD = 24       # portale fermo da più di N ore = CRITICAL
ERROR_COUNT_WARN = 5             # errori in un cycle = WARN
ERROR_COUNT_CRIT = 20            # = CRITICAL
PORTALS = ("idealista", "immobiliare")


@dataclass
class Anomaly:
    level: str       # "WARN" | "CRITICAL"
    code: str        # short identifier (es. "portal_stale")
    message: str     # human-readable

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


# ============================================================================
# Rilevatori
# ============================================================================

def detect_anomalies(sb: Client, stats: dict) -> list[Anomaly]:
    """Analizza stats del cycle + stato DB → lista di Anomaly."""
    out: list[Anomaly] = []
    portal_counts = stats.get("portals") or {}
    errors = stats.get("errors") or []

    # 1) Cycle senza alcuna attività su un portale: né nuovi né rivisti.
    for portal in PORTALS:
        pc = portal_counts.get(portal) or {}
        synced = pc.get("synced_new", 0)
        touched = pc.get("touched_existing", 0)
        scraped = pc.get("scraped_basic", 0)
        if scraped == 0:
            out.append(Anomaly(
                level="CRITICAL",
                code=f"{portal}_no_activity",
                message=(
                    f"{portal}: nessuna pagina scaricata (0 listings scraped). "
                    "Probabile blocco anti-bot (403) o errore di rete."
                ),
            ))
        elif synced == 0 and touched == 0 and scraped > 0:
            out.append(Anomaly(
                level="WARN",
                code=f"{portal}_no_sync",
                message=(
                    f"{portal}: scaricate {scraped} pagine ma niente "
                    "synced/touched. Possibile errore sync DB."
                ),
            ))

    # 2) Errori troppi
    n_err = len(errors)
    if n_err >= ERROR_COUNT_CRIT:
        out.append(Anomaly(
            level="CRITICAL",
            code="too_many_errors",
            message=f"{n_err} errori in un cycle (soglia critica {ERROR_COUNT_CRIT}).",
        ))
    elif n_err >= ERROR_COUNT_WARN:
        out.append(Anomaly(
            level="WARN",
            code="many_errors",
            message=f"{n_err} errori in un cycle.",
        ))

    # 3) Portale fermo da troppo tempo
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS_THRESHOLD))
        for portal in PORTALS:
            r = (
                sb.table("listings")
                .select("last_seen_at")
                .eq("portal", portal)
                .order("last_seen_at", desc=True)
                .limit(1)
                .execute()
            )
            if not r.data:
                continue
            last_seen = datetime.fromisoformat(r.data[0]["last_seen_at"])
            if last_seen < cutoff:
                hours = (datetime.now(timezone.utc) - last_seen).total_seconds() / 3600
                out.append(Anomaly(
                    level="CRITICAL",
                    code=f"{portal}_stale",
                    message=(
                        f"{portal}: nessun listing rivisto da {hours:.1f}h "
                        f"(soglia {STALE_HOURS_THRESHOLD}h). Il cron non sta "
                        "scrappando questo portale."
                    ),
                ))
    except Exception as e:
        logger.warning(f"stale check failed: {e}")

    return out


# ============================================================================
# Persistenza
# ============================================================================

def save_cycle_run(sb: Client, stats: dict, anomalies: list[Anomaly]) -> int | None:
    """Inserisce una riga in `cycle_runs` con tutto il payload del run."""
    try:
        started = stats.get("started_at")
        finished = stats.get("finished_at")
        duration = None
        if started and finished:
            try:
                duration = (
                    datetime.fromisoformat(finished) - datetime.fromisoformat(started)
                ).total_seconds()
            except Exception:
                pass
        payload = {
            "started_at": started or datetime.now(timezone.utc).isoformat(),
            "finished_at": finished,
            "duration_s": duration,
            "stats": stats.get("portals") or {},
            "errors": stats.get("errors") or [],
            "anomalies": [a.to_dict() for a in anomalies],
            "notified": False,
        }
        res = sb.table("cycle_runs").insert(payload).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        logger.warning(f"save_cycle_run failed: {e}")
    return None


# ============================================================================
# Notifica
# ============================================================================

def notify_anomalies(anomalies: list[Anomaly], run_id: int | None = None) -> bool:
    """Manda un messaggio Telegram con il riepilogo delle anomalie.

    Restituisce True se inviato.
    """
    if not anomalies:
        return False

    # Ordina CRITICAL prima
    sorted_anom = sorted(
        anomalies, key=lambda a: (0 if a.level == "CRITICAL" else 1, a.code)
    )

    has_crit = any(a.level == "CRITICAL" for a in anomalies)
    header_emoji = "🚨" if has_crit else "⚠️"
    header = f"{header_emoji} *BOT\\_IMMOBILIARE — Anomalie rilevate*"

    lines = [header, ""]
    for a in sorted_anom:
        icon = "🔴" if a.level == "CRITICAL" else "🟡"
        # Markdown escape minimo
        msg = a.message.replace("_", "\\_").replace("*", "\\*")
        lines.append(f"{icon} *{a.level}* — `{a.code}`")
        lines.append(f"   {msg}")
        lines.append("")

    if run_id:
        lines.append(f"_Run id: {run_id}_")

    text = "\n".join(lines)
    return send_telegram(text)
