"""Notifiche push via Telegram.

Auto-disabilitato se TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID non sono settati
(le funzioni diventano no-op). Così la pipeline gira identica anche senza
notifiche configurate.

Setup per Paolo:
  1. Apri Telegram, cerca @BotFather
  2. /newbot, scegli nome (es. "Paolo Vailati Lead Bot") e username (es. @paolovailati_lead_bot)
  3. BotFather restituisce un TOKEN tipo 1234567890:ABCdef…
  4. Scrivi /start al tuo nuovo bot (apri il link che BotFather ti dà)
  5. Visita https://api.telegram.org/bot<TOKEN>/getUpdates → trova `chat.id`
  6. Mettili nel .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  7. Test: python -c "from src.notify import test_telegram; test_telegram()"
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from src.models import Listing

logger = logging.getLogger("notify")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _telegram_config() -> Optional[tuple[str, list[str]]]:
    """Restituisce (token, [chat_id, ...]) o None se non configurato.

    Supporta TELEGRAM_CHAT_ID singolo o multipli separati da virgola.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    raw_ids = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not raw_ids:
        return None
    chat_ids = [c.strip() for c in raw_ids.split(",") if c.strip()]
    if not chat_ids:
        return None
    return (token, chat_ids)


def send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    """Invio messaggio low-level a TUTTI i chat_id configurati.

    Restituisce True se ALMENO UNO è stato inviato con successo.
    No-op (False) se Telegram non configurato — non solleva eccezioni:
    la pipeline non deve fallire perché manca la notifica.
    """
    config = _telegram_config()
    if not config:
        return False
    token, chat_ids = config
    any_ok = False
    for chat_id in chat_ids:
        try:
            r = requests.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
            if r.status_code != 200:
                logger.warning(f"telegram send to {chat_id} → {r.status_code}: {r.text[:200]}")
                continue
            any_ok = True
        except Exception as e:
            logger.warning(f"telegram exception for {chat_id}: {e}")
    return any_ok


def _escape_md(s: Optional[str]) -> str:
    """Escape minimo per Telegram Markdown legacy (parse_mode=Markdown)."""
    if not s:
        return ""
    for ch in ("_", "*", "[", "`"):
        s = s.replace(ch, "\\" + ch)
    return s


def notify_new_private_listing(listing: Listing) -> bool:
    """Notifica push per un nuovo annuncio PRIVATO appena syncato.

    Esempio output:
        🟢 *Nuovo affitto privato — Idealista*
        👤 *Marino* — `+393357420063`
        📍 Sempione, Milano
        💰 950 €/mese · 35 m² · 1 locale
        🔗 [Apri annuncio](https://www.idealista.it/immobile/7103669/)
    """
    if listing.advertiser_type != "private":
        return False

    portal_pretty = {
        "idealista": "Idealista",
        "immobiliare": "Immobiliare.it",
    }.get(listing.portal, listing.portal)

    name = _escape_md(listing.advertiser_name) or "—"
    phone = listing.phones[0] if listing.phones else "(non disponibile)"
    zone = _escape_md(listing.microzone or listing.macrozone or listing.address or "Milano")

    parts: list[str] = []
    if listing.price_eur:
        parts.append(f"{listing.price_eur:,} €/mese".replace(",", "."))
    if listing.surface_m2:
        parts.append(f"{listing.surface_m2} m²")
    if listing.rooms:
        parts.append(f"{listing.rooms} locali")
    spec_line = " · ".join(parts) if parts else ""

    text = (
        f"🟢 *Nuovo affitto privato — {portal_pretty}*\n\n"
        f"👤 *{name}* — `{phone}`\n"
        f"📍 {zone}, Milano\n"
    )
    if spec_line:
        text += f"💰 {spec_line}\n"
    text += f"🔗 [Apri annuncio]({listing.url})"
    return send_telegram(text)


def test_telegram() -> None:
    """Test rapido — esegui questo dopo aver settato TELEGRAM_*."""
    ok = send_telegram(
        "✅ *BOT\\_IMMOBILIARE*\n\n"
        "Telegram configurato correttamente.\n"
        "Da ora riceverai una notifica per ogni *nuovo annuncio privato* "
        "intercettato dal bot."
    )
    print("OK" if ok else "FAIL — verifica TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
