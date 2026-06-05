"""Test del parser spese condominiali."""

from __future__ import annotations

import pytest

from src.normalize import extract_expenses_eur


@pytest.mark.parametrize("text,expected", [
    # Caso classico Idealista (annuncio Marino)
    ("Canone mensile Euro 950 + Euro 150 di spese condominiali mensili", 150),
    # Variations
    ("+ Euro 80 spese", 80),
    ("spese condo 70 €", 70),
    ("spese condominiali 200€/mese", 200),
    ("70€ spese condo", 70),
    ("100 € di spese condominiali", 100),
    ("Condominio 120€", 120),
])
def test_extracts_valid_expenses(text, expected):
    assert extract_expenses_eur(text) == expected


@pytest.mark.parametrize("text", [
    "",
    None,
    "Nessuna informazione sulle spese",
    "Anno di costruzione 1995",
    "Piano 8 con ascensore",
    "Cap 20121 Milano",
])
def test_no_extraction_when_absent(text):
    assert extract_expenses_eur(text) is None


def test_extract_rejects_implausible_values():
    """Valori fuori range (1-9 o >1500) non vengono accettati."""
    # 8 troppo basso
    assert extract_expenses_eur("piano 8") is None
    # 2026 (anno) non viene matchato dai pattern (non ha keyword spese)
    assert extract_expenses_eur("dal 2026 disponibile") is None


def test_realistic_idealista_text():
    descr = (
        "Bilocale via Test, 80 mq, 3° piano. Contratto 4+4. "
        "Canone Euro 950 mensile + Euro 150 di spese condominiali. "
        "No agenzie."
    )
    assert extract_expenses_eur(descr) == 150
