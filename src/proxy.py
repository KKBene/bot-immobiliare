"""Proxy anti-bot — supporto multi-provider con fallback automatico.

Ordine di priorità (se più provider configurati):
  1. Scrapfly (env `SCRAPFLY_API_KEY`)
  2. Bright Data Web Unlocker (env `BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE`)
  3. curl_cffi diretto (sempre disponibile, gratis ma 403-prone)

Tutti i provider fanno DataDome bypass + IP italiano residenziale.

Doc:
  - https://scrapfly.io/docs/scrape-api/getting-started
  - https://docs.brightdata.com/scraping-automation/web-unlocker/quickstart
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from curl_cffi import requests as creq

from src.anti_detect import TransientError

logger = logging.getLogger("proxy")

BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
SCRAPFLY_ENDPOINT = "https://api.scrapfly.io/scrape"


def is_scrapfly_enabled() -> bool:
    return bool(os.environ.get("SCRAPFLY_API_KEY"))


def is_brightdata_enabled() -> bool:
    return bool(
        os.environ.get("BRIGHTDATA_API_KEY")
        and os.environ.get("BRIGHTDATA_ZONE")
    )


def scrapfly_get(
    url: str,
    *,
    country: str = "it",
    timeout: int = 60,
    asp: bool = True,
    render_js: bool = False,
) -> requests.Response:
    """Fetch via Scrapfly Web Scraping API.

    `asp=True` attiva l'anti-scraping (DataDome bypass).
    `render_js=False` evita il costo extra del browser (per Idealista/Immobiliare
    il JSON è già nel server-rendered HTML, non serve JS).
    """
    api_key = os.environ["SCRAPFLY_API_KEY"]
    params = {
        "key": api_key,
        "url": url,
        "country": country,
        "asp": "true" if asp else "false",
        "render_js": "true" if render_js else "false",
    }
    try:
        r = requests.get(SCRAPFLY_ENDPOINT, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise TransientError(f"scrapfly network error: {e}") from e

    if r.status_code == 429:
        raise TransientError("scrapfly rate-limited (429)")
    if r.status_code >= 500:
        raise TransientError(f"scrapfly 5xx ({r.status_code})")
    if r.status_code == 401 or r.status_code == 403:
        raise RuntimeError(
            f"scrapfly auth/credits failed ({r.status_code}). "
            f"Verifica key e crediti rimanenti."
        )
    if r.status_code != 200:
        raise TransientError(f"scrapfly status={r.status_code}")

    # Scrapfly imbusta la risposta in JSON: il content originale è in
    # result.content e lo status del target in result.status_code
    try:
        body = r.json()
    except Exception as e:
        raise TransientError(f"scrapfly bad JSON: {e}") from e
    result = body.get("result") or {}

    # Costruiamo una pseudo-Response con l'interfaccia che serve agli scrapers
    proxy_response = requests.Response()
    proxy_response.status_code = result.get("status_code", 200)
    proxy_response._content = (result.get("content") or "").encode("utf-8")
    proxy_response.encoding = "utf-8"
    proxy_response.url = url
    # Header del target (per Content-Type ecc.)
    for k, v in (result.get("response_headers") or {}).items():
        proxy_response.headers[k] = v
    return proxy_response


def brightdata_get(
    url: str,
    *,
    country: str = "it",
    format: str = "raw",
    timeout: int = 60,
) -> requests.Response:
    """Fetch via Bright Data Web Unlocker.

    Restituisce un `requests.Response` con:
      - .status_code: status finale (Bright Data ritorna 200 se tutto ok)
      - .text: HTML/JSON ottenuto dal target
      - .headers: header proxied

    Solleva TransientError su errori di rate-limit Bright Data o se
    `can_make_requests: false` (zone scaduta/non configurata).
    """
    api_key = os.environ["BRIGHTDATA_API_KEY"]
    zone = os.environ["BRIGHTDATA_ZONE"]

    payload = {
        "zone": zone,
        "url": url,
        "format": format,
        "country": country,
        # method default GET; possiamo aggiungere "method": "POST" se serve
    }

    try:
        r = requests.post(
            BRIGHTDATA_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise TransientError(f"brightdata network error: {e}") from e

    if r.status_code == 429:
        raise TransientError("brightdata rate-limited (429)")
    if r.status_code >= 500:
        raise TransientError(f"brightdata 5xx ({r.status_code})")
    if r.status_code == 401:
        raise RuntimeError("brightdata auth failed (zone scaduta? key invalida?)")
    return r


def smart_get(
    url: str,
    *,
    impersonate: str = "safari17_2_ios",
    headers: Optional[dict] = None,
    timeout: int = 25,
    prefer_proxy: bool = True,
) -> requests.Response | creq.Response:
    """GET con ordine di priorità: Scrapfly → Bright Data → curl_cffi diretto.

    Il chiamante può forzare `prefer_proxy=False` per saltare i proxy su
    pagine "facili" (es. listing Idealista che già passa via diretto)
    e risparmiare crediti del proxy.
    """
    if prefer_proxy and is_scrapfly_enabled():
        try:
            return scrapfly_get(url, timeout=timeout)
        except Exception as e:
            logger.warning(f"scrapfly fail, prossimo provider: {e}")

    if prefer_proxy and is_brightdata_enabled():
        try:
            return brightdata_get(url, timeout=timeout)
        except Exception as e:
            logger.warning(f"brightdata fail, fallback diretto: {e}")

    h = {"Accept-Language": "it-IT,it;q=0.9"}
    if headers:
        h.update(headers)
    return creq.get(url, impersonate=impersonate, headers=h, timeout=timeout)


# Backward-compat alias (mantenuto perché usato in tests)
def prefer_brightdata_compat():  # pragma: no cover
    pass
