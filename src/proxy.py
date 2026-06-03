"""Proxy via Bright Data Web Unlocker (gestione DataDome on/off).

Se configurato (env `BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE`), tutte le
fetch che usano questo modulo passano per Bright Data:
  - rotation di IP residenziali italiani
  - JS rendering + captcha solving DataDome
  - costo pay-per-request

Se NON configurato, fallback automatico a curl_cffi diretto (gratis, ma
soggetto a 403 DataDome quando IP è blacklistato).

Doc Bright Data Web Unlocker:
  https://docs.brightdata.com/scraping-automation/web-unlocker/quickstart
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


def is_brightdata_enabled() -> bool:
    return bool(
        os.environ.get("BRIGHTDATA_API_KEY")
        and os.environ.get("BRIGHTDATA_ZONE")
    )


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
    prefer_brightdata: bool = True,
) -> requests.Response | creq.Response:
    """GET intelligente.

    Se Bright Data configurato AND `prefer_brightdata` → passa via proxy.
    Altrimenti curl_cffi diretto (più veloce, gratis, ma soggetto a 403).

    Il chiamante può forzare `prefer_brightdata=False` per saltare il proxy
    su pagine "facili" (es. listing Idealista) e usare BD solo dove serve.
    """
    if prefer_brightdata and is_brightdata_enabled():
        try:
            return brightdata_get(url, timeout=timeout)
        except Exception as e:
            logger.warning(f"brightdata fail, fallback diretto: {e}")
            # cade su curl_cffi sotto

    h = {"Accept-Language": "it-IT,it;q=0.9"}
    if headers:
        h.update(headers)
    return creq.get(url, impersonate=impersonate, headers=h, timeout=timeout)
