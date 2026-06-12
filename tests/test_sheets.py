"""Test del sync Google Sheets (mock gspread)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.sheets import (
    COLUMNS,
    CONTACTED_COL_IDX,
    URL_COL_IDX,
    _listing_row,
    is_enabled,
    sync_private_listings,
)


def test_columns_have_contattato_at_correct_position():
    """Il bot DEVE preservare 'Contattato' — verifico che l'indice sia
    quello atteso (per non sovrascriverlo per errore)."""
    assert COLUMNS[CONTACTED_COL_IDX] == "Contattato"
    assert COLUMNS[URL_COL_IDX] == "URL"


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_WEBHOOK_URL", raising=False)
    assert is_enabled() is False


def test_disabled_without_creds(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "x")
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_WEBHOOK_URL", raising=False)
    assert is_enabled() is False


def test_enabled_with_json_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "x")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON",
                      '{"type":"service_account","client_email":"x"}')
    assert is_enabled() is True


def test_listing_row_uses_correct_order():
    listing = {
        "url": "https://www.idealista.it/immobile/1/",
        "advertiser_name": "Marino",
        "microzone": "Sempione",
        "address": "Via X",
        "price_eur": 950,
        "surface_m2": 35,
        "rooms": "1",
        "first_seen_at": "2026-06-03T20:30:00",
    }
    row = _listing_row(listing, contact_phone="+393357420063", contacted="No")
    from src.sheets import COLUMNS
    by_col = dict(zip(COLUMNS, row))
    assert by_col["URL"] == listing["url"]
    assert by_col["Inserzionista"] == "Marino"
    assert by_col["Telefono"] == "+393357420063"
    assert by_col["Prezzo €/mese"] == 950
    assert by_col["Mq"] == 35
    assert by_col["Locali"] == "1"
    assert by_col["Contattato"] == "No"
    # Niente più colonne rimosse
    for removed_col in ("Portale", "Spese €/mese", "Totale €/mese", "Status"):
        assert removed_col not in by_col


def test_sync_noop_when_not_configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    sb = MagicMock()
    result = sync_private_listings(sb)
    assert result["added"] == 0
    assert "not_configured" in result.get("reason", "")
    sb.table.assert_not_called()


def test_sync_appends_new_and_updates_existing(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("GOOGLE_SHEET_ID", "ID")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON",
                      '{"type":"service_account","client_email":"x"}')

    sb = MagicMock()
    # listings query
    listings_resp = MagicMock()
    listings_resp.data = [
        {"id": 1, "url": "https://x.it/1",
         "advertiser_name": "A", "microzone": "Z", "price_eur": 100,
         "first_seen_at": "2026-06-03T00:00:00"},
        {"id": 2, "url": "https://x.it/2",
         "advertiser_name": "B", "microzone": "Z", "price_eur": 200,
         "first_seen_at": "2026-06-03T00:00:00"},
    ]
    # listing_contacts
    lc_resp = MagicMock()
    lc_resp.data = [
        {"listing_id": 1, "contact_id": 10},
        {"listing_id": 2, "contact_id": 20},
    ]
    # contacts
    contacts_resp = MagicMock()
    contacts_resp.data = [
        {"id": 10, "phone_e164": "+393111111111", "kind": "private"},
        {"id": 20, "phone_e164": "+393222222222", "kind": "private"},
    ]

    # Configura chain mocks (signature dinamica: la chain di select.eq...order
    # può variare a seconda dei filtri)
    def fake_table(name):
        t = MagicMock()
        if name == "listings":
            # Dopo `.eq("advertiser_type","private").order(...).limit(...).execute()`
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = listings_resp
        elif name == "listing_contacts":
            # Chunked: select.in_("listing_id", chunk).execute
            t.select.return_value.in_.return_value.execute.return_value = lc_resp
        elif name == "contacts":
            t.select.return_value.in_.return_value.execute.return_value = contacts_resp
        return t
    sb.table.side_effect = fake_table

    # Mock gspread
    ws = MagicMock()
    # url 1 già nel foglio (riga 2), url 2 nuovo
    ws.get_all_values.return_value = [
        COLUMNS,  # header riga 1
        ["https://x.it/1", "idealista", "A_vecchio", "+39 old"] + [""] * (len(COLUMNS) - 4),
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    client = MagicMock()
    client.open_by_key.return_value = sh
    with patch("src.sheets._client", return_value=(client, "ID")):
        result = sync_private_listings(sb)

    assert result["added"] == 1   # url 2 nuovo
    assert result["updated"] == 1 # url 1 aggiornato
    # append_rows chiamato con il nuovo
    appended = ws.append_rows.call_args.args[0]
    assert any("https://x.it/2" in row[URL_COL_IDX] for row in appended)
    # update batch ha chiamato batch_update; verifica che NON tocchi colonna Contattato
    batch_calls = ws.batch_update.call_args.args[0]
    for cell in batch_calls:
        range_str = cell["range"]
        col_letter = range_str[0]
        # Contattato = col 13 = M
        assert col_letter != chr(65 + CONTACTED_COL_IDX), (
            f"BUG: il sync ha tentato di scrivere nella colonna "
            f"Contattato ({chr(65 + CONTACTED_COL_IDX)})"
        )
