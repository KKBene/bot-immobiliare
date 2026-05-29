"""Test offline del modulo anti_detect.

Verifica:
  - jitter sta nella forchetta attesa
  - Backoff riprova N volte poi solleva
  - CircuitBreaker apre dopo threshold e si chiude dopo cooldown
  - Backoff + CB interagiscono correttamente (CB apre → no più retry)
"""

from __future__ import annotations

import time

import pytest

from src.anti_detect import (
    Backoff,
    CircuitBreaker,
    TransientError,
    get_circuit_breaker,
    jitter,
    pick_ua,
    safe_sleep,
)


# ---------- jitter ----------

def test_jitter_in_bounds():
    for _ in range(200):
        v = jitter(2.0, 0.20)
        assert 1.6 <= v <= 2.4


def test_jitter_zero_pct():
    assert jitter(2.0, 0.0) == 2.0


# ---------- safe_sleep ----------

def test_safe_sleep_runs(monkeypatch):
    """safe_sleep deve chiamare time.sleep con value positivo."""
    captured = {}
    def fake_sleep(s):
        captured["s"] = s
    monkeypatch.setattr(time, "sleep", fake_sleep)
    safe_sleep(1.0, pct=0.50)
    assert "s" in captured
    assert 0.5 <= captured["s"] <= 1.5


# ---------- Circuit Breaker ----------

def test_cb_closed_initially():
    cb = CircuitBreaker(name="test1")
    assert not cb.is_open()


def test_cb_opens_after_threshold():
    cb = CircuitBreaker(name="test2", threshold=3, pause_seconds=10)
    cb.open_on_error()
    assert not cb.is_open()
    cb.open_on_error()
    assert not cb.is_open()
    cb.open_on_error()
    assert cb.is_open()
    assert cb.remaining_seconds() > 0


def test_cb_resets_on_success():
    cb = CircuitBreaker(name="test3", threshold=2, pause_seconds=10)
    cb.open_on_error()
    cb.reset()
    cb.open_on_error()
    assert not cb.is_open()  # solo 1 errore dopo il reset


def test_cb_factory_caches_by_name():
    a = get_circuit_breaker("cache_test_x", threshold=5)
    b = get_circuit_breaker("cache_test_x")
    assert a is b


# ---------- Backoff ----------

def test_backoff_succeeds_on_first_try():
    bk = Backoff(max_attempts=3, base_sleep=0.001)
    calls = []
    @bk.wrap()
    def f():
        calls.append(1)
        return "ok"
    assert f() == "ok"
    assert len(calls) == 1


def test_backoff_retries_then_succeeds():
    bk = Backoff(max_attempts=3, base_sleep=0.001)
    attempts = {"n": 0}
    @bk.wrap()
    def f():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("simulated 403")
        return "ok"
    assert f() == "ok"
    assert attempts["n"] == 3


def test_backoff_gives_up_after_max():
    bk = Backoff(max_attempts=2, base_sleep=0.001)
    @bk.wrap()
    def f():
        raise TransientError("always fails")
    with pytest.raises(TransientError):
        f()


def test_backoff_with_cb_stops_retrying_when_open():
    """Quando il CB si apre, il backoff non deve continuare a battere."""
    cb = CircuitBreaker(name="bk_test", threshold=2, pause_seconds=60)
    bk = Backoff(max_attempts=5, base_sleep=0.001)
    attempts = {"n": 0}
    @bk.wrap(circuit=cb)
    def f():
        attempts["n"] += 1
        raise TransientError("status=403")
    with pytest.raises(TransientError):
        f()
    # threshold=2 → al 2° errore CB apre, niente più retry
    assert attempts["n"] == 2, f"Atteso 2 attempt, fatti {attempts['n']}"
    assert cb.is_open()


def test_non_transient_error_not_retried():
    bk = Backoff(max_attempts=3, base_sleep=0.001)
    attempts = {"n": 0}
    @bk.wrap()
    def f():
        attempts["n"] += 1
        raise ValueError("permanent")
    with pytest.raises(ValueError):
        f()
    assert attempts["n"] == 1


# ---------- UA pool ----------

def test_pick_ua_returns_string():
    for pool in ("safari_ios", "safari_mac", "chrome", "unknown_pool"):
        ua = pick_ua(pool)
        assert isinstance(ua, str) and "Mozilla" in ua
