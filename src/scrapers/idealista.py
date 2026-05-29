"""Scraper Idealista.it (API-only, no browser, no parsing fragile).

Pipeline:
  1. Listing page HTML → estraggo solo `data-element-id` degli <article>
     (più price/title/zone come quick metadata, ma robusto al cambio CSS)
  2. Per ogni ID: due chiamate JSON nascoste scoperte via `var config` della
     detail page:
       a. /it/ajax/listingController/adContactInfoForDetail.ajax?adId={id}
          → isAdProfessional (priv/agency), nome, ecc.
       b. /it/ajax/ads/{id}/contact-phones
          → telefono in chiaro (formattato + E.164) SENZA login!
  3. Listing arricchito con dati strutturati.

DataDome bypass: curl_cffi `impersonate="safari17_2_ios"`. 10/10 stabilità
verificata su 10 ad consecutivi.

Sleep raccomandato tra detail call: ≥1.0s per non innescare rate limit.
"""

from __future__ import annotations

import re
import time
from typing import Iterable, Optional

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests as creq

from src.anti_detect import Backoff, TransientError, get_circuit_breaker, safe_sleep
from src.models import Listing

# Circuit breaker condiviso per tutto Idealista: 3 errori consecutivi → 30min pause.
_cb_idealista = get_circuit_breaker("idealista", threshold=3, pause_seconds=1800)
_backoff = Backoff(max_attempts=3, base_sleep=2.0, factor=2.0, jitter_pct=0.25)

BASE_URL = "https://www.idealista.it"
LIST_URL_TEMPLATE = BASE_URL + "/affitto-case/{city}-{city}/"
DETAIL_URL_TEMPLATE = BASE_URL + "/immobile/{ad_id}/"
INFO_URL_TEMPLATE = (
    BASE_URL + "/it/ajax/listingController/adContactInfoForDetail.ajax?adId={ad_id}"
)
PHONES_URL_TEMPLATE = BASE_URL + "/it/ajax/ads/{ad_id}/contact-phones"

IMPERSONATE = "safari17_2_ios"

PHONE_RE = re.compile(
    r"""(?:\+?39[\s.\-]?|0039[\s.\-]?)?
        (?:3\d{2}|0\d{1,3})
        [\s.\-/]?
        (?:\d[\s.\-/]?){5,9}
        \d
    """,
    re.VERBOSE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class IdealistaScraper:
    """Scraper Idealista API-based.

    Uso tipico:
        s = IdealistaScraper()
        for basic in s.scrape_list(page=1):
            full = s.enrich_with_api(basic)   # ← 2 chiamate API
            ...
    """

    def __init__(self, city: str = "milano", impersonate: str = IMPERSONATE):
        self.city = city
        self.impersonate = impersonate
        # NB: niente Session — DataDome marca il cookie 'datadome' come bot
        # appena si fa una chiamata AJAX usando una sessione persistente.
        # Chiamate fresche, una per request, sono 200 OK stabili.
        self._common_headers = {"Accept-Language": "it-IT,it;q=0.9"}

    def _get_raw(self, url: str, headers: Optional[dict] = None, timeout: int = 20):
        h = dict(self._common_headers)
        if headers:
            h.update(headers)
        return creq.get(url, impersonate=self.impersonate, headers=h, timeout=timeout)

    @_backoff.wrap(circuit=_cb_idealista)
    def _get(self, url: str, headers: Optional[dict] = None, timeout: int = 20):
        """GET con retry+backoff+circuit-breaker.

        Solleva TransientError su 403/429/5xx: il decorator riprova con
        backoff esponenziale. Dopo 3 fail consecutivi il CB apre per 30 min.
        """
        r = self._get_raw(url, headers=headers, timeout=timeout)
        if r.status_code in (403, 429) or 500 <= r.status_code < 600:
            raise TransientError(f"status={r.status_code} for {url}")
        return r

    # ---------- LISTING (HTML) ----------

    def list_url(self, page: int = 1) -> str:
        url = LIST_URL_TEMPLATE.format(city=self.city)
        return url + (f"lista-{page}.htm" if page > 1 else "")

    def fetch_list_html(self, page: int = 1, timeout: int = 25) -> str:
        url = self.list_url(page)
        r = self._get(url, timeout=timeout)
        if "captcha-delivery" in r.text or r.status_code == 403:
            raise RuntimeError(
                f"Idealista DataDome block (status={r.status_code}). "
                "Cambia impersonate o passa a CloakBrowser."
            )
        r.raise_for_status()
        return r.text

    @staticmethod
    def _text(node: Optional[Tag]) -> str:
        return node.get_text(" ", strip=True) if node else ""

    @staticmethod
    def _int_from(text: str) -> Optional[int]:
        m = re.search(r"\d[\d.]*", (text or "").replace(".", ""))
        return int(m.group()) if m else None

    @classmethod
    def _parse_title_zone(cls, title: str) -> tuple[Optional[str], Optional[str]]:
        if not title:
            return (None, None)
        parts = [p.strip() for p in title.split(",")]
        if len(parts) >= 3:
            head = parts[0]
            m = re.match(r"^[^,]+\s+in\s+(.+)$", head, re.IGNORECASE)
            address = m.group(1) if m else head
            zone = parts[-2]
            return (address, zone)
        return (title, None)

    @classmethod
    def parse_list_basic(cls, html: str) -> list[Listing]:
        """Estrae solo i dati che la listing card espone affidabilmente.

        L'enrichment via API completa il resto.
        """
        soup = BeautifulSoup(html, "lxml")
        articles = soup.find_all(
            "article", class_=lambda c: c and "item" in c.split()
        )
        out: list[Listing] = []
        for art in articles:
            ext_id = art.get("data-element-id")
            if not ext_id:
                continue
            link = art.select_one("a.item-link")
            href = link.get("href") if link else None
            url = (
                (BASE_URL + href) if href and href.startswith("/")
                else (href or DETAIL_URL_TEMPLATE.format(ad_id=ext_id))
            )
            title = (link.get("title") if link else None) or cls._text(link)
            price_el = art.select_one(".item-price")
            price_eur = cls._int_from(cls._text(price_el)) if price_el else None
            details = [
                cls._text(s) for s in art.select(".item-detail-char .item-detail")
            ]
            rooms = surface = floor = None
            for d in details:
                low = d.lower()
                if "local" in low or "stanz" in low:
                    rooms_m = re.search(r"\d+", d)
                    rooms = rooms_m.group() if rooms_m else None
                elif "m²" in d or "mq" in low:
                    surface = cls._int_from(d)
                elif "piano" in low or "rialzato" in low:
                    floor = d
            description = cls._text(art.select_one(".item-description, .description"))
            address, zone = cls._parse_title_zone(title)

            text_blob = " ".join(filter(None, [title, description]))
            out.append(Listing(
                portal="idealista",
                external_id=str(ext_id),
                url=url,
                title=title,
                description=description,
                price_eur=price_eur,
                surface_m2=surface,
                rooms=rooms,
                floor=floor,
                address=address,
                city="Milano",
                microzone=zone,
                contract="rent",
                raw_phones_in_text=list(set(PHONE_RE.findall(text_blob))),
                raw_emails_in_text=list(set(EMAIL_RE.findall(text_blob))),
            ))
        return out

    # ---------- DETAIL (JSON API) ----------

    def _api_headers(self, ad_id: str) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": DETAIL_URL_TEMPLATE.format(ad_id=ad_id),
            "X-Requested-With": "XMLHttpRequest",
        }

    def fetch_ad_info(self, ad_id: str, timeout: int = 15) -> dict:
        """Metadata ricche: privato/agenzia, nome, tipologia."""
        url = INFO_URL_TEMPLATE.format(ad_id=ad_id)
        r = self._get(url, headers=self._api_headers(ad_id), timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        if payload.get("result") != "OK":
            raise RuntimeError(f"adInfo non OK: {payload.get('message')}")
        return payload["data"]

    def fetch_ad_phones(self, ad_id: str, timeout: int = 15) -> dict:
        """Telefono dell'inserzionista in chiaro (formatted + E.164).

        Risposta tipica:
          {"phone1":{"formatted":"335 742 0063","number":"+393357420063","type":null},
           "phone2":null}
        """
        url = PHONES_URL_TEMPLATE.format(ad_id=ad_id)
        r = self._get(url, headers=self._api_headers(ad_id), timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {}

    def enrich_with_api(self, basic: Listing, sleep: float = 0.0) -> Listing:
        """Arricchisce un Listing base con info + telefoni dalla API JSON.

        Override:
          - advertiser_type da isAdProfessional
          - advertiser_name dal nome più ricco disponibile
          - phones dal contact-phones
          - typology da adTypologyName
        """
        info = self.fetch_ad_info(basic.external_id)
        if sleep:
            time.sleep(sleep)
        phones_payload = self.fetch_ad_phones(basic.external_id)

        basic.advertiser_type = "agency" if info.get("isAdProfessional") else "private"
        basic.advertiser_name = (
            info.get("commercialName")
            or " ".join(filter(None, [info.get("firstName"), info.get("lastName")]))
            or info.get("firstName")
        )
        basic.typology = info.get("adTypologyName")

        phones: list[str] = []
        for key in ("phone1", "phone2"):
            p = phones_payload.get(key) if isinstance(phones_payload, dict) else None
            if p:
                # preferisco il number E.164, fallback al formatted
                v = p.get("number") or p.get("formatted")
                if v:
                    phones.append(v)
        basic.phones = phones
        return basic

    # ---------- convenience ----------

    def scrape_page_enriched(
        self, page: int = 1, sleep_between_details: float = 1.5
    ) -> Iterable[Listing]:
        """Generatore: yield Listing arricchito uno per uno.

        Usa safe_sleep (jitter ±20%) per non avere cadenza regolare.
        """
        html = self.fetch_list_html(page=page)
        basics = self.parse_list_basic(html)
        for i, b in enumerate(basics):
            try:
                yield self.enrich_with_api(b)
            except Exception as e:
                print(f"  ⚠️  enrich fallito per {b.external_id}: {e}")
                yield b
            if i < len(basics) - 1:
                safe_sleep(sleep_between_details, pct=0.30)
