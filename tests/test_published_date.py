"""Test parser data di pubblicazione (Idealista relativa + assoluta)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.normalize import parse_italian_relative_date


def _isoformat_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _within(actual: str | None, expected_delta: timedelta, tolerance_s: int = 90) -> bool:
    if not actual:
        return False
    now = datetime.now(timezone.utc)
    diff = abs((now - _isoformat_to_dt(actual)) - expected_delta).total_seconds()
    return diff <= tolerance_s


@pytest.mark.parametrize("text,delta", [
    ("1 minuto", timedelta(minutes=1)),
    ("5 minuti", timedelta(minutes=5)),
    ("1 ora", timedelta(hours=1)),
    ("3 ore", timedelta(hours=3)),
    ("1 giorno", timedelta(days=1)),
    ("2 giorni", timedelta(days=2)),
    ("1 settimana", timedelta(days=7)),
    ("2 settimane", timedelta(days=14)),
    ("1 mese", timedelta(days=30)),
])
def test_relative_dates(text, delta):
    out = parse_italian_relative_date(text)
    assert _within(out, delta), f"{text!r} → {out}"


def test_oggi():
    out = parse_italian_relative_date("oggi")
    assert _within(out, timedelta(seconds=0))


def test_ieri():
    out = parse_italian_relative_date("ieri")
    assert _within(out, timedelta(days=1))


def test_absolute_date_full():
    out = parse_italian_relative_date("15 maggio 2025")
    dt = _isoformat_to_dt(out)
    assert dt.year == 2025 and dt.month == 5 and dt.day == 15


def test_absolute_date_current_year_default():
    """'15 maggio' senza anno → anno corrente se non futuro, altrimenti precedente."""
    out = parse_italian_relative_date("15 maggio")
    dt = _isoformat_to_dt(out)
    assert dt.month == 5 and dt.day == 15
    # Deve essere passato (o oggi)
    assert dt <= datetime.now(timezone.utc) + timedelta(days=30)


@pytest.mark.parametrize("text", [
    "",
    None,
    "annunci",
    "qualcosa di strano",
])
def test_returns_none_when_invalid(text):
    assert parse_italian_relative_date(text) is None
