"""Pipeline master: un ciclo completo di scrape + sync per tutti i portali.

Eseguito dal cron (ogni 3h) e dallo script CLI.

Comportamento:
  1. Per ogni portale attivo, scraper la prima N pagine
  2. Dedup via Supabase (gli annunci già presenti vengono SKIPPED prima
     dell'enrich → niente chiamate API inutili)
  3. Enrich + sync solo per i NUOVI annunci
  4. Log strutturato con counters

Robusto a singoli errori: un fallimento su un annuncio non rompe il ciclo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client

from src.anti_detect import safe_sleep
from src.db import client, sync_listing_with_contacts
from src.geocoding import geocode_listing_inplace
from src.health import detect_anomalies, notify_anomalies, save_cycle_run
from src.notify import notify_new_private_listing
from src.scrapers.idealista import IdealistaScraper
from src.scrapers.immobiliare import ImmobiliareScraper

# Default safety caps per la paginazione dinamica
DEFAULT_MAX_PAGES = 15
# Numero minimo di pagine da esplorare SEMPRE (a prescindere dal backlog).
# Garantisce copertura anche quando le prime pagine sono dominate da
# annunci-vetrina che cambiano poco (es. Immobiliare sponsored).
DEFAULT_MIN_PAGES = 3
# Soglia "pagina già esplorata": se ≥ X% degli annunci della pagina sono
# già in DB, fermiamo la paginazione (non c'è più backlog da prendere).
STOP_WHEN_ALREADY_SEEN_PCT = 0.90


logger = logging.getLogger("pipeline")


@dataclass
class CycleStats:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    portal_counts: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, portal: str, key: str, n: int = 1) -> None:
        self.portal_counts.setdefault(portal, {})
        self.portal_counts[portal][key] = self.portal_counts[portal].get(key, 0) + n

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "portals": self.portal_counts,
            "errors": self.errors,
        }


def listing_already_in_db(sb: Client, portal: str, external_id: str) -> bool:
    r = (
        sb.table("listings")
        .select("id", count="exact")
        .eq("portal", portal)
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    return bool(r.data)


# ============================================================================
# IDEALISTA — paginazione dinamica
# ============================================================================

def cycle_idealista(
    sb: Client,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    min_pages: int = DEFAULT_MIN_PAGES,
    city: str = "milano",
    sleep_between_details: float = 1.5,
    sleep_between_pages: float = 3.0,
    stop_pct: float = STOP_WHEN_ALREADY_SEEN_PCT,
    stats: Optional[CycleStats] = None,
) -> CycleStats:
    """Pagina dinamicamente fino a `max_pages` (safety cap), fermandosi
    quando una pagina contiene ≥ `stop_pct` annunci già in DB
    (backlog esaurito, non vale la pena continuare).
    """
    stats = stats or CycleStats()
    portal = "idealista"
    scraper = IdealistaScraper(city=city)

    for page in range(1, max_pages + 1):
        try:
            html = scraper.fetch_list_html(page=page)
            basics = IdealistaScraper.parse_list_basic(html)
        except Exception as e:
            err = f"idealista page {page}: {e}"
            logger.error(err)
            stats.errors.append(err)
            break

        if not basics:
            logger.info(f"[idealista p{page}] vuota, stop")
            break

        # Split nuovi vs già visti PRIMA di chiamare l'API
        already_seen = 0
        new_basics = []
        for b in basics:
            if listing_already_in_db(sb, portal, b.external_id):
                already_seen += 1
                # tocco scraped_count/last_seen_at anche sui già visti
                sync_listing_with_contacts(sb, b)
                stats.add(portal, "touched_existing")
            else:
                new_basics.append(b)

        stats.add(portal, "seen", len(basics))
        stats.add(portal, "scraped_basic", len(basics))
        already_pct = already_seen / len(basics)
        logger.info(
            f"[idealista p{page}] {len(basics)} totali, "
            f"{already_seen} già in DB ({already_pct:.0%}), "
            f"{len(new_basics)} da arricchire"
        )

        # Enrich + sync solo i nuovi (API call cost-effective)
        for i, b in enumerate(new_basics):
            try:
                enriched = scraper.enrich_with_api(b)
                sync_listing_with_contacts(sb, enriched)
                stats.add(portal, "synced_new")
                # 🌍 Geocoding inline (no-op se manca address; ~1s extra)
                try:
                    if geocode_listing_inplace(sb, enriched):
                        stats.add(portal, "geocoded")
                except Exception as ge:
                    logger.warning(f"geocode {b.external_id}: {ge}")
                if enriched.advertiser_type == "private":
                    stats.add(portal, "new_private")
                    # 🔔 Notifica Telegram sul nuovo privato
                    try:
                        notify_new_private_listing(enriched)
                    except Exception as ne:
                        logger.warning(f"notify failed: {ne}")
            except Exception as e:
                err = f"idealista enrich {b.external_id}: {e}"
                logger.warning(err)
                stats.errors.append(err)
                stats.add(portal, "errors")
            if i < len(new_basics) - 1:
                safe_sleep(sleep_between_details, pct=0.30)

        # Stop dinamico SOLO dopo aver garantito min_pages di copertura
        if page >= min_pages and already_pct >= stop_pct:
            logger.info(
                f"[idealista] backlog esaurito a p{page} ({already_pct:.0%} già visti), stop"
            )
            stats.add(portal, "pages_explored", page)
            break

        if page < max_pages:
            safe_sleep(sleep_between_pages, pct=0.25)
    else:
        # max_pages raggiunto senza stop dinamico
        stats.add(portal, "pages_explored", max_pages)
        logger.warning(
            f"[idealista] raggiunto max_pages={max_pages} senza esaurire backlog"
        )
    return stats


# ============================================================================
# IMMOBILIARE — paginazione dinamica
# ============================================================================

def cycle_immobiliare(
    sb: Client,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    min_pages: int = DEFAULT_MIN_PAGES,
    city: str = "milano",
    sleep_between_pages: float = 3.0,
    stop_pct: float = STOP_WHEN_ALREADY_SEEN_PCT,
    stats: Optional[CycleStats] = None,
) -> CycleStats:
    stats = stats or CycleStats()
    portal = "immobiliare"
    scraper = ImmobiliareScraper(city=city)

    for page in range(1, max_pages + 1):
        try:
            html = scraper.fetch_list_html(page=page)
            listings = ImmobiliareScraper.parse_listings(html)
        except Exception as e:
            err = f"immobiliare page {page}: {e}"
            logger.error(err)
            stats.errors.append(err)
            break

        if not listings:
            logger.info(f"[immobiliare p{page}] vuota, stop")
            break

        already_seen = 0
        new_listings = []
        for l in listings:
            if listing_already_in_db(sb, portal, l.external_id):
                already_seen += 1
                sync_listing_with_contacts(sb, l)  # touch
                stats.add(portal, "touched_existing")
            else:
                new_listings.append(l)

        stats.add(portal, "seen", len(listings))
        stats.add(portal, "scraped_basic", len(listings))
        already_pct = already_seen / len(listings)
        logger.info(
            f"[immobiliare p{page}] {len(listings)} totali, "
            f"{already_seen} già in DB ({already_pct:.0%}), "
            f"{len(new_listings)} nuovi"
        )

        for l in new_listings:
            try:
                sync_listing_with_contacts(sb, l)
                stats.add(portal, "synced_new")
                # Immobiliare ha già lat/lng nel __NEXT_DATA__, ma se mancassero
                # (per qualche annuncio non-standard) fallback su geocoding.
                if not (l.latitude and l.longitude):
                    try:
                        if geocode_listing_inplace(sb, l):
                            stats.add(portal, "geocoded")
                    except Exception as ge:
                        logger.warning(f"geocode {l.external_id}: {ge}")
                if l.advertiser_type == "private":
                    stats.add(portal, "new_private")
                    try:
                        notify_new_private_listing(l)
                    except Exception as ne:
                        logger.warning(f"notify failed: {ne}")
            except Exception as e:
                err = f"immobiliare sync {l.external_id}: {e}"
                logger.warning(err)
                stats.errors.append(err)
                stats.add(portal, "errors")

        if page >= min_pages and already_pct >= stop_pct:
            logger.info(
                f"[immobiliare] backlog esaurito a p{page} ({already_pct:.0%} già visti), stop"
            )
            stats.add(portal, "pages_explored", page)
            break

        if page < max_pages:
            safe_sleep(sleep_between_pages, pct=0.25)
    else:
        stats.add(portal, "pages_explored", max_pages)
        logger.warning(
            f"[immobiliare] raggiunto max_pages={max_pages} senza esaurire backlog"
        )
    return stats


# ============================================================================
# MARK STALE — annunci spariti dal portale
# ============================================================================

def mark_stale_listings(sb: Client, hours: int = 48) -> int:
    """Marca status='removed' per annunci non più visti da >hours ore.

    Idempotente. Conviene chiamarla una volta per ciclo di scrape: chi è
    sparito dal portale (locato/ritirato) viene segnato 'removed' e non
    appare più nella dashboard dei lead attivi.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    res = (
        sb.table("listings")
        .update({"status": "removed"})
        .lt("last_seen_at", cutoff)
        .neq("status", "removed")
        .execute()
    )
    n = len(res.data) if res.data else 0
    if n:
        logger.info(f"[mark_stale] marcati 'removed' {n} annunci (>{hours}h senza re-scrape)")
    return n


# ============================================================================
# Master cycle
# ============================================================================

def run_cycle(
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    city: str = "milano",
    stale_hours: int = 48,
) -> CycleStats:
    """Master cycle: scrape paginato dinamico + mark stale + anomaly check.

    Alla fine del cycle:
      - salva una riga in cycle_runs (audit)
      - rileva anomalie (portale fermo, errori, ecc.)
      - manda alert Telegram se anomalie presenti
    """
    sb = client()
    stats = CycleStats()
    try:
        cycle_idealista(sb, max_pages=max_pages, city=city, stats=stats)
    except Exception as e:
        stats.errors.append(f"idealista cycle aborted: {e}")
        logger.exception("idealista cycle aborted")
    try:
        cycle_immobiliare(sb, max_pages=max_pages, city=city, stats=stats)
    except Exception as e:
        stats.errors.append(f"immobiliare cycle aborted: {e}")
        logger.exception("immobiliare cycle aborted")
    try:
        n_removed = mark_stale_listings(sb, hours=stale_hours)
        stats.portal_counts.setdefault("_global", {})["marked_removed"] = n_removed
    except Exception as e:
        stats.errors.append(f"mark_stale: {e}")
    stats.finished_at = datetime.now(timezone.utc).isoformat()

    # --- Health: salva run + rileva anomalie + notifica ---
    try:
        stats_dict = stats.to_dict()
        anomalies = detect_anomalies(sb, stats_dict)
        run_id = save_cycle_run(sb, stats_dict, anomalies)
        if anomalies:
            logger.warning(
                "Anomalie rilevate (%d): %s",
                len(anomalies), [a.code for a in anomalies],
            )
            notify_anomalies(anomalies, run_id=run_id)
            # marca come notified
            if run_id:
                try:
                    sb.table("cycle_runs").update({"notified": True}).eq("id", run_id).execute()
                except Exception:
                    pass
    except Exception as e:
        logger.exception(f"health check failed: {e}")

    return stats
