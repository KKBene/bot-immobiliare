"""Anti-detection helpers: jitter, retry+backoff, circuit breaker, UA pool.

Pensato per essere usato dai scraper senza diventare invadente:

    from src.anti_detect import safe_sleep, Backoff, get_circuit_breaker

    cb = get_circuit_breaker("idealista")
    backoff = Backoff(...)

    @backoff.wrap(circuit=cb)
    def fetch(...):
        ...

Vedi `docs/ANTI_DETECTION.md` per il razionale.
"""

from __future__ import annotations

import functools
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

# ============================================================================
# Jitter
# ============================================================================

def jitter(value: float, pct: float = 0.20) -> float:
    """Restituisce `value` con jitter uniforme ±pct.

    Es: jitter(1.5, 0.20) ∈ [1.2, 1.8].
    """
    delta = value * pct
    return value + random.uniform(-delta, delta)


def safe_sleep(seconds: float, pct: float = 0.20) -> None:
    """sleep con jitter — sostituto drop-in di time.sleep nei loop di scrape."""
    time.sleep(max(0.0, jitter(seconds, pct)))


# ============================================================================
# Circuit Breaker
# ============================================================================

@dataclass
class CircuitBreaker:
    """Pausa il sistema dopo N errori consecutivi (403/429).

    Usage:
        cb.open_on_error()   # registra errore
        cb.reset()           # registra successo
        cb.guard()           # blocca con sleep se è aperto
    """
    name: str
    threshold: int = 3
    pause_seconds: int = 1800           # 30 min
    consecutive_failures: int = 0
    opened_until: Optional[datetime] = None

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.opened_until = None

    def open_on_error(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.opened_until = (
                datetime.now(timezone.utc) + timedelta(seconds=self.pause_seconds)
            )

    def is_open(self) -> bool:
        if not self.opened_until:
            return False
        if datetime.now(timezone.utc) >= self.opened_until:
            # cooldown finito → resetta
            self.reset()
            return False
        return True

    def remaining_seconds(self) -> float:
        if not self.opened_until:
            return 0.0
        delta = (self.opened_until - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)

    def guard(self) -> None:
        """Se aperto, dorme fino a fine cooldown. Use con cautela."""
        if self.is_open():
            time.sleep(self.remaining_seconds() + 1)


_circuits: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Cache per-name dei CB. Permette stesso CB da più chiamanti."""
    if name not in _circuits:
        _circuits[name] = CircuitBreaker(name=name, **kwargs)
    return _circuits[name]


# ============================================================================
# Retry + exponential backoff
# ============================================================================

class TransientError(Exception):
    """Errore che merita retry. Sollevato da .wrap quando status ∈ retry_on."""


@dataclass
class Backoff:
    """Retry con backoff esponenziale + jitter.

    Usage:
        backoff = Backoff(max_attempts=3, base_sleep=1.5)

        @backoff.wrap(circuit=cb)
        def fetch():
            r = creq.get(...)
            if r.status_code in (403, 429):
                raise TransientError(r.status_code)
            return r
    """
    max_attempts: int = 3
    base_sleep: float = 1.5
    factor: float = 2.0                  # base_sleep, base_sleep*2, base_sleep*4, ...
    jitter_pct: float = 0.20
    max_sleep: float = 60.0

    def wrap(self, circuit: Optional[CircuitBreaker] = None):
        def deco(fn: Callable):
            @functools.wraps(fn)
            def inner(*args, **kwargs):
                if circuit:
                    circuit.guard()
                last_exc: Optional[Exception] = None
                for attempt in range(1, self.max_attempts + 1):
                    try:
                        result = fn(*args, **kwargs)
                        if circuit:
                            circuit.reset()
                        return result
                    except TransientError as e:
                        last_exc = e
                        if circuit:
                            circuit.open_on_error()
                            if circuit.is_open():
                                # rispetta CB: non riprovare subito
                                break
                        if attempt == self.max_attempts:
                            break
                        sleep_s = min(
                            self.max_sleep,
                            self.base_sleep * (self.factor ** (attempt - 1)),
                        )
                        time.sleep(jitter(sleep_s, self.jitter_pct))
                if last_exc:
                    raise last_exc
            return inner
        return deco


# ============================================================================
# User-Agent pool (per quando torniamo a non impersonare TLS)
# ============================================================================

# NB: ai fini di curl_cffi questo ha effetto MARGINALE perché il TLS fingerprint
# è il segnale dominante. Lo teniamo per debugging e per quando si è loggati
# (le AJAX session-bound dei portali ispezionano l'UA).
UAS_SAFARI_IOS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
]
UAS_SAFARI_MAC = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]
UAS_CHROME = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

UA_POOLS = {
    "safari_ios": UAS_SAFARI_IOS,
    "safari_mac": UAS_SAFARI_MAC,
    "chrome": UAS_CHROME,
}


def pick_ua(pool: str = "safari_ios") -> str:
    return random.choice(UA_POOLS.get(pool, UAS_CHROME))
