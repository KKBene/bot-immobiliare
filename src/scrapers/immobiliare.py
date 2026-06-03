"""Scraper Immobiliare.it.

Strategia: Immobiliare è protetto da DataDome. Si bypassa con curl_cffi che
impersona il TLS fingerprint di Chrome. Il payload utile è il JSON dentro
<script id="__NEXT_DATA__"> — niente parsing HTML.

Path al payload: props.pageProps.dehydratedState.queries[0].state.data.results
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

import logging

from curl_cffi import requests as creq

from src.anti_detect import Backoff, TransientError, get_circuit_breaker
from src.models import Listing

logger = logging.getLogger("immobiliare")

_cb_immobiliare = get_circuit_breaker("immobiliare", threshold=3, pause_seconds=1800)
_backoff = Backoff(max_attempts=3, base_sleep=2.0, factor=2.0, jitter_pct=0.25)

BASE_URL = "https://www.immobiliare.it"
LIST_URL_TEMPLATE = BASE_URL + "/affitto-case/{city}/"

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

# Regex per estrarre contatti dal testo libero (descrizione / titolo).
#
# Strategia: la regex è permissiva (cattura sequenze di cifre intervallate da
# separatori). La validazione finale è delegata a normalize_phone_it() che
# scarta lunghezze fuori range italiano (8-11 cifre dopo prefisso).
#
# Prefisso opzionale: +39 / 39 / 0039
# Trigger: cellulare 3XX o fisso 0X / 0XX / 0XXX (Milano=02, Roma=06, ecc.)
# Separatori ammessi all'interno: space, dot, dash, slash
PHONE_RE = re.compile(
    r"""(?:\+?39[\s.\-]?|0039[\s.\-]?)?     # prefisso internazionale opz
        (?:3\d{2}|0\d{1,3})                  # cell 3XX o fisso 0X..0XXX
        [\s.\-/]?
        (?:\d[\s.\-/]?){5,9}                 # 5-9 cifre con separatori
        \d                                   # cifra finale
    """,
    re.VERBOSE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class ImmobiliareScraper:
    """Scraper della listing page di Immobiliare per una città."""

    def __init__(self, city: str = "milano", impersonate: str = "chrome"):
        self.city = city
        self.impersonate = impersonate

    # ---------- fetch ----------

    def list_url(self, page: int = 1) -> str:
        """URL listing ordinato per data desc (più recenti prima).

        IMPORTANTE: senza `criterio=data`, la pagina 1 è la vetrina
        sponsorizzata (sempre gli stessi 25 annunci ordinati per "rilevanza")
        → la paginazione dinamica si fermava subito al primo passaggio del
        bot.  Verificato 2026-06-02: tutti i nostri 336 'removed' Immobiliare
        derivavano da questo bug.
        """
        url = LIST_URL_TEMPLATE.format(city=self.city)
        params = ["criterio=data", "ordine=desc"]
        if page > 1:
            params.append(f"pag={page}")
        return url + "?" + "&".join(params)

    @_backoff.wrap(circuit=_cb_immobiliare)
    def fetch_list_html(self, page: int = 1, timeout: int = 25) -> str:
        """GET via smart_get (Bright Data on/off) + retry+backoff+CB."""
        from src.proxy import smart_get
        url = self.list_url(page)
        r = smart_get(url, impersonate=self.impersonate, timeout=timeout)
        if r.status_code in (403, 429) or 500 <= r.status_code < 600:
            raise TransientError(f"status={r.status_code} for {url}")
        r.raise_for_status()
        return r.text

    # ---------- parse ----------

    @staticmethod
    def extract_next_data(html: str) -> dict:
        m = NEXT_DATA_RE.search(html)
        if not m:
            raise ValueError("__NEXT_DATA__ non trovato (anti-bot o pagina cambiata)")
        return json.loads(m.group(1))

    @staticmethod
    def _results_from_next_data(data: dict) -> list[dict]:
        try:
            return data["props"]["pageProps"]["dehydratedState"]["queries"][0][
                "state"
            ]["data"]["results"]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Path ai results non valido: {e}") from e

    @staticmethod
    def _parse_surface(raw: Optional[str]) -> Optional[int]:
        """'94 m²' -> 94, None -> None."""
        if not raw:
            return None
        m = re.search(r"(\d+)", raw)
        return int(m.group(1)) if m else None

    @classmethod
    def _classify_advertiser(cls, advertiser: dict) -> tuple[str, Optional[str]]:
        """Restituisce (type, displayName).

        - se c'è una agency con label="agenzia" / "agente immobiliare" -> agency
        - altrimenti private
        """
        agency = advertiser.get("agency") if advertiser else None
        if not agency:
            return ("private", None)
        label = (agency.get("label") or "").lower()
        if "privato" in label:
            return ("private", agency.get("displayName"))
        return ("agency", agency.get("displayName"))

    @classmethod
    def _phones_from_advertiser(cls, advertiser: dict) -> list[str]:
        if not advertiser:
            return []
        out: list[str] = []
        agency = advertiser.get("agency") or {}
        for p in agency.get("phones", []) or []:
            v = p.get("value")
            if v:
                out.append(v)
        supervisor = advertiser.get("supervisor") or {}
        for p in supervisor.get("phones", []) or []:
            v = p.get("value")
            if v and v not in out:
                out.append(v)
        return out

    @classmethod
    def parse_listings(cls, html: str) -> list[Listing]:
        data = cls.extract_next_data(html)
        results = cls._results_from_next_data(data)
        listings: list[Listing] = []

        for r in results:
            re_ = r.get("realEstate") or {}
            seo = r.get("seo") or {}
            props = re_.get("properties") or []
            prop = props[0] if props else {}

            advertiser = re_.get("advertiser") or {}
            adv_type, adv_name = cls._classify_advertiser(advertiser)

            price_obj = re_.get("price") or {}
            location = prop.get("location") or {}

            title = prop.get("caption") or seo.get("anchor")
            description = prop.get("description")
            text_blob = " ".join(filter(None, [title, description]))

            raw_phones = list(set(PHONE_RE.findall(text_blob)))
            raw_emails = list(set(EMAIL_RE.findall(text_blob)))

            # Fallback: cerca telefoni offuscati (3.4.2.1...) nella descrizione.
            # Spesso i privati su Immobiliare nascondono il numero così.
            from src.normalize import find_phones_in_text
            phones_from_text = find_phones_in_text(text_blob)

            listing = Listing(
                portal="immobiliare",
                external_id=str(re_.get("id") or ""),
                url=seo.get("url") or "",
                title=title,
                description=description,
                price_eur=price_obj.get("value"),
                surface_m2=cls._parse_surface(prop.get("surface")),
                rooms=str(prop.get("rooms")) if prop.get("rooms") else None,
                bathrooms=str(prop.get("bathrooms")) if prop.get("bathrooms") else None,
                floor=(prop.get("floor") or {}).get("abbreviation"),
                typology=(prop.get("typology") or {}).get("name"),
                address=location.get("address"),
                city=location.get("city"),
                macrozone=location.get("macrozone"),
                microzone=location.get("microzone"),
                latitude=location.get("latitude"),
                longitude=location.get("longitude"),
                advertiser_type=adv_type,
                advertiser_name=adv_name,
                # Phones: combiniamo quelli esposti dall'advertiser + quelli
                # estratti dalla descrizione (offuscati). dedup E.164.
                phones=cls._merge_phones(
                    cls._phones_from_advertiser(advertiser),
                    phones_from_text,
                ),
                raw_phones_in_text=raw_phones,
                raw_emails_in_text=raw_emails,
                visibility=re_.get("visibility"),
                contract=re_.get("contract"),
            )
            listings.append(listing)
        return listings

    @staticmethod
    def _merge_phones(advertiser_phones: list[str], text_phones: list[str]) -> list[str]:
        """Unisce phones advertiser + phones-da-testo, dedup su E.164."""
        from src.normalize import normalize_phone_it
        seen_e164: set[str] = set()
        out: list[str] = []
        for p in advertiser_phones + text_phones:
            e164 = normalize_phone_it(p)
            if e164 and e164 not in seen_e164:
                seen_e164.add(e164)
                out.append(p)
        return out

    # ========================================================================
    # ENRICH DETAIL — recupera phone da detail page __NEXT_DATA__
    # ========================================================================
    #
    # Validato empiricamente (3 giugno 2026) su 10 privati Immobiliare:
    #   - 1/10 ha phone esposto in advertiser.supervisor.phones
    #   - 9/10 ha phones=[] + hasCallNumbers=True (nascosto dietro click reveal)
    #
    # L'enrich qui implementato cattura quel 10% che ha il numero pubblicamente.
    # Per gli altri serve browser headless (TODO Playwright).

    def fetch_detail_json(self, ext_id: str, timeout: int = 20) -> dict:
        """Scarica detail page via smart_get (Bright Data se attivo).

        Solleva TransientError se DataDome blocca o il JSON è inatteso.
        Su Immobiliare la detail page è il caso più ostile: privilegia
        Bright Data per minimizzare 403.
        """
        from src.proxy import smart_get
        url = f"{BASE_URL}/annunci/{ext_id}/"
        r = smart_get(
            url,
            impersonate="safari17_2_ios",
            headers={"Accept-Language": "it-IT,it;q=0.9"},
            timeout=timeout,
        )
        if "captcha-delivery" in r.text or r.status_code in (403, 429):
            raise TransientError(f"Detail {ext_id} bloccato (status {r.status_code})")
        r.raise_for_status()
        return self.extract_next_data(r.text)

    def enrich_with_detail(self, listing: Listing) -> Listing:
        """Arricchisce un Listing con phone presi dal detail page.

        Modifica listing in-place e lo restituisce.
        - Se `aiCallable` è True → skip (Paolo non vuole "Chiama AI")
        - Se advertiser.supervisor/agency.phones presenti → li aggiunge
        - Cerca anche numeri offuscati nella description COMPLETA (più lunga
          del listing card → più chance di trovare numeri nascosti)

        Non solleva su errore di rete: log warning + ritorna listing inalterato.
        """
        try:
            data = self.fetch_detail_json(listing.external_id)
        except Exception as e:
            logger.warning(f"detail fetch failed for {listing.external_id}: {e}")
            return listing

        try:
            re_obj = (
                data.get("props", {}).get("pageProps", {})
                .get("detailData", {}).get("realEstate") or {}
            )
        except AttributeError:
            return listing

        adv = re_obj.get("advertiser") or {}

        # Skip "Chiama AI" — flag conservativo
        if adv.get("aiCallable") is True:
            logger.info(f"{listing.external_id}: Chiama AI → skip phone enrich")
            return listing

        # Phones da supervisor (privati) + agency (agenzie)
        adv_phones = self._phones_from_advertiser(adv)

        # Description completa dal detail page
        props = re_obj.get("properties") or []
        prop = props[0] if props else {}
        full_description = prop.get("description") or ""

        from src.normalize import find_phones_in_text
        text_phones = find_phones_in_text(
            " ".join([listing.title or "", full_description])
        )

        merged = self._merge_phones(
            advertiser_phones=listing.phones + adv_phones,
            text_phones=text_phones,
        )
        if merged != listing.phones:
            logger.info(
                f"{listing.external_id}: enrich → +{len(merged) - len(listing.phones)} phones"
            )
            listing.phones = merged

        # Aggiorna anche description se più ricca
        if full_description and (not listing.description
                                  or len(full_description) > len(listing.description)):
            listing.description = full_description

        return listing

    # ---------- convenience ----------

    def scrape_page(self, page: int = 1) -> list[Listing]:
        html = self.fetch_list_html(page=page)
        return self.parse_listings(html)

    def scrape_pages(
        self,
        start: int = 1,
        end: int = 1,
        sleep_between: float = 1.5,
    ) -> Iterable[Listing]:
        """Genera annunci da più pagine; ferma se incontra una pagina vuota.

        Lo sleep evita di battere troppo Immobiliare (curl_cffi è veloce ma
        bombardarli accende DataDome). 1.5s è un compromesso conservativo.
        """
        import time
        for page in range(start, end + 1):
            listings = self.scrape_page(page)
            if not listings:
                return
            for l in listings:
                yield l
            if page < end:
                time.sleep(sleep_between)
