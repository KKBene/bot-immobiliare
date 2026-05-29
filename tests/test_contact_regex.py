"""Test offline delle regex di estrazione contatti dal testo libero.

Goal: 100% precision (zero falsi positivi su esempi noti negativi).
Per il recall: cataloghiamo i pattern che vogliamo catturare con esempi
canonici.
"""

from __future__ import annotations

import pytest

from src.scrapers.immobiliare import EMAIL_RE, PHONE_RE
from src.normalize import normalize_phone_it


# ============================================================================
# CASI POSITIVI — devono essere catturati
# ============================================================================

POSITIVE_PHONE = [
    # privato lascia numero cellulare nel testo
    ("Chiamare 333 1234567 per info", "333 1234567"),
    ("Tel: +39 333 1234567",          "+39 333 1234567"),
    ("Telefono 3331234567",           "3331234567"),
    ("info al 333.12.34.567",         "333.12.34.567"),
    ("contatto 333-1234567",          "333-1234567"),
    # numero fisso Milano
    ("Studio: 02 8736 4229",          "02 8736 4229"),
    ("Ufficio 02-87364229",           "02-87364229"),
]


@pytest.mark.parametrize("text,expected_substring", POSITIVE_PHONE)
def test_phone_regex_catches(text, expected_substring):
    matches = PHONE_RE.findall(text)
    assert matches, f"Niente trovato in {text!r}"
    # almeno un match deve normalizzare a un E.164 valido
    canon = {normalize_phone_it(m) for m in matches} - {None}
    assert canon, f"Match non normalizzabili: {matches}"


# ============================================================================
# CASI NEGATIVI — NON devono essere catturati come telefono
# ============================================================================

NEGATIVE_PHONE = [
    "Anno di costruzione 1995",                # 4 cifre
    "Superficie 94 m²",                        # 2 cifre + unità
    "Riferimento RIF-001234",                  # alfanumerico
    "Codice IPE 175,5 kWh",                    # decimal con virgola
    "12345",                                   # solo 5 cifre
    "L'appartamento è situato al piano 8",     # 1 cifra
    "Cap 20121 Milano",                        # CAP a 5 cifre
]


@pytest.mark.parametrize("text", NEGATIVE_PHONE)
def test_phone_regex_no_false_positives_on_neutral_text(text):
    """Caso permissivo: la regex può matchare, ma normalize_phone_it deve
    restituire None su tutti i match (= scartati come telefono).
    """
    matches = PHONE_RE.findall(text)
    canon = {normalize_phone_it(m) for m in matches} - {None}
    assert not canon, (
        f"FALSO POSITIVO su {text!r}: catturati {matches}, normalizzati {canon}"
    )


# ============================================================================
# EMAIL
# ============================================================================

POSITIVE_EMAIL = [
    "Scrivere a mario.rossi@gmail.com",
    "info@studio-immobiliare.it",
    "richieste: a.bianchi+casa@dominio.co.uk",
]


@pytest.mark.parametrize("text", POSITIVE_EMAIL)
def test_email_regex_catches(text):
    matches = EMAIL_RE.findall(text)
    assert matches, f"Niente email in {text!r}"


NEGATIVE_EMAIL = [
    "Visita @lunedì alle 18",      # no domain
    "Anno 2020.05.29",             # date
    "tinyurl.com/abc",             # url senza @
    "12345 codice",                # no @
]


@pytest.mark.parametrize("text", NEGATIVE_EMAIL)
def test_email_regex_no_match(text):
    assert not EMAIL_RE.findall(text), f"falso positivo su {text!r}"


# ============================================================================
# REALISTIC: dato un blocco di testo lungo, estrae solo i contatti reali
# ============================================================================

REAL_LIKE_BODY = """
Appartamento trilocale in zona Navigli, 90 mq, 3° piano con ascensore.
Anno di costruzione 1995, classe energetica G (175 kWh/m²).
Riferimento annuncio: RIF-2024-001.
Per visite scrivere a m.rossi@studiocasa.it oppure chiamare il 339-1234567.
Tel. ufficio 02 8736 4229.
"""


def test_realistic_extraction_only_real_contacts():
    phones = PHONE_RE.findall(REAL_LIKE_BODY)
    canon = sorted({normalize_phone_it(p) for p in phones} - {None})
    assert canon == ["+390287364229", "+393391234567"], canon
    emails = EMAIL_RE.findall(REAL_LIKE_BODY)
    assert emails == ["m.rossi@studiocasa.it"]
