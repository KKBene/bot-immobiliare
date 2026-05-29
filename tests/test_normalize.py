"""Test offline pure-Python sulla normalizzazione (no DB)."""

from __future__ import annotations

import pytest

from src.normalize import normalize_email, normalize_phone_it


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("02 8736 4229", "+390287364229"),
        ("+39 02 8736 4229", "+390287364229"),
        ("0039 333 1234567", "+393331234567"),
        ("333 1234567", "+393331234567"),
        ("333.12.34.567", "+393331234567"),
        ("+393331234567", "+393331234567"),
        ("tel: 333-12-34-567", "+393331234567"),
        ("3331234567", "+393331234567"),
    ],
)
def test_phone_canonical(raw, expected):
    assert normalize_phone_it(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "123", "x" * 200])
def test_phone_invalid_returns_none(raw):
    assert normalize_phone_it(raw) is None


def test_same_phone_different_format_dedups():
    """Test killer: stesse cifre con format diversi → stesso E.164."""
    variants = [
        "+39 333 12 34 567",
        "0039 333 1234567",
        "tel: +39-333-1234567",
        "333/1234567",
        "3331234567",
    ]
    canon = {normalize_phone_it(v) for v in variants}
    assert canon == {"+393331234567"}, f"Dedup rotta: {canon}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Foo@Bar.Com", "foo@bar.com"),
        ("  user@dominio.it  ", "user@dominio.it"),
    ],
)
def test_email_canonical(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "no-at", "no-dot@x"])
def test_email_invalid_returns_none(raw):
    assert normalize_email(raw) is None
