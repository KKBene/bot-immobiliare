"""Test del parser di numeri offuscati nella descrizione."""

from __future__ import annotations

import pytest

from src.normalize import find_phones_in_text


# ============================================================================
# CASI POSITIVI — devono essere estratti
# ============================================================================

@pytest.mark.parametrize("text,expected", [
    # standard
    ("Chiamami al 333 1234567", ["+393331234567"]),
    ("Tel: +39 333 1234567", ["+393331234567"]),
    ("0039 333 1234567", ["+393331234567"]),
    # offuscati ANTI-BOT classici
    ("3.3.3.1.2.3.4.5.6.7", ["+393331234567"]),
    ("3-3-3-1-2-3-4-5-6-7", ["+393331234567"]),
    ("3 3 3 1 2 3 4 5 6 7", ["+393331234567"]),
    # mix di formati
    ("3.3.3.1234567", ["+393331234567"]),
    ("333-12-34-567", ["+393331234567"]),
    ("333/12/34/567", ["+393331234567"]),
    # fissi Milano
    ("Studio: 02 8736 4229", ["+390287364229"]),
    ("02-87364229", ["+390287364229"]),
    ("0 2 8 7 3 6 4 2 2 9", ["+390287364229"]),
])
def test_finds_phones(text, expected):
    result = find_phones_in_text(text)
    for e in expected:
        assert e in result, f"Mancato {e} in {text!r}: trovati {result}"


# ============================================================================
# CASI NEGATIVI — NON devono essere catturati
# ============================================================================

@pytest.mark.parametrize("text", [
    "Anno di costruzione 1995",          # 4 cifre
    "Codice IPE 175,5 kWh",              # numero con virgola decimale
    "Cap 20121 Milano",                  # CAP 5 cifre
    "Anno 2020.05.29",                   # data
    "L'appartamento è al piano 8",       # 1 cifra
    "Codice fiscale RSSMRA80A01H501Z",   # codice fiscale
    "",
    "no numero qui",
])
def test_rejects_non_phone(text):
    result = find_phones_in_text(text)
    assert result == [], f"Falso positivo su {text!r}: {result}"


# ============================================================================
# MULTI: il testo contiene più numeri
# ============================================================================

def test_extracts_multiple_phones():
    text = (
        "Per visite chiamare il 339-1234567 oppure il numero fisso "
        "0 2 8 7 3 6 4 2 2 9. Rif: RIF-2024-001."
    )
    result = find_phones_in_text(text)
    assert "+393391234567" in result
    assert "+390287364229" in result
    assert len(result) == 2  # niente falsi positivi su RIF-2024-001


def test_realistic_obfuscated_in_description():
    """Esempio reale di descrizione di un privato che offusca."""
    descr = (
        "Bilocale luminoso a Milano zona Navigli. 80mq, 3 piano. "
        "No agenzie. Per info scrivere o chiamare al "
        "3.3.5.7.4.2.0.0.6.3 grazie."
    )
    result = find_phones_in_text(descr)
    assert "+393357420063" in result


def test_does_not_match_random_long_digit_sequence():
    """Sequenze di 8+ cifre che NON cominciano con 3 o 0 vengono scartate."""
    text = "ID interno: 12345678901, riferimento 87654321"
    result = find_phones_in_text(text)
    assert result == []
