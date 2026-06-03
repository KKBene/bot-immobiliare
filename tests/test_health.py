"""Test detect_anomalies + notify_anomalies (offline, mock)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.health import Anomaly, detect_anomalies, notify_anomalies, save_cycle_run


# ---------- detect_anomalies ----------

def _mock_sb_with_last_seen(per_portal_hours_ago: dict):
    """Mock supabase che ritorna last_seen_at relativo."""
    sb = MagicMock()

    def fake_table(name):
        t = MagicMock()
        # listings.last_seen_at lookup
        def fake_select(*a, **kw):
            sel = MagicMock()
            def fake_eq(col, val):
                eq = MagicMock()
                eq.order = lambda *a, **kw: eq
                eq.limit = lambda n: eq
                hours_ago = per_portal_hours_ago.get(val)
                if hours_ago is None:
                    eq.execute = lambda: MagicMock(data=[])
                else:
                    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
                    eq.execute = lambda: MagicMock(data=[{"last_seen_at": ts}])
                return eq
            sel.eq = fake_eq
            return sel
        t.select = fake_select
        # cycle_runs.insert
        t.insert = lambda payload: MagicMock(execute=lambda: MagicMock(data=[{"id": 99}]))
        return t

    sb.table = fake_table
    return sb


def test_no_anomalies_when_everything_ok():
    sb = _mock_sb_with_last_seen({"idealista": 1, "immobiliare": 2})
    stats = {
        "portals": {
            "idealista": {"scraped_basic": 30, "synced_new": 5, "touched_existing": 25},
            "immobiliare": {"scraped_basic": 25, "synced_new": 0, "touched_existing": 25},
        },
        "errors": [],
    }
    assert detect_anomalies(sb, stats) == []


def test_anomaly_when_portal_did_not_scrape():
    sb = _mock_sb_with_last_seen({"idealista": 1, "immobiliare": 1})
    stats = {
        "portals": {
            "idealista": {"scraped_basic": 30, "synced_new": 5, "touched_existing": 25},
            "immobiliare": {"scraped_basic": 0, "synced_new": 0, "touched_existing": 0},
        },
        "errors": [],
    }
    anomalies = detect_anomalies(sb, stats)
    codes = [a.code for a in anomalies]
    assert "immobiliare_no_activity" in codes
    crit = [a for a in anomalies if a.code == "immobiliare_no_activity"]
    assert crit[0].level == "CRITICAL"


def test_anomaly_when_portal_stale():
    """Se l'ultimo last_seen è > 24h fa, alert CRITICAL."""
    sb = _mock_sb_with_last_seen({"idealista": 1, "immobiliare": 30})
    stats = {
        "portals": {
            "idealista": {"scraped_basic": 30, "synced_new": 1, "touched_existing": 29},
            "immobiliare": {"scraped_basic": 0, "synced_new": 0, "touched_existing": 0},
        },
        "errors": [],
    }
    anomalies = detect_anomalies(sb, stats)
    codes = [a.code for a in anomalies]
    assert "immobiliare_stale" in codes


def test_anomaly_when_many_errors():
    sb = _mock_sb_with_last_seen({"idealista": 1, "immobiliare": 1})
    stats = {
        "portals": {
            "idealista": {"scraped_basic": 30, "synced_new": 5, "touched_existing": 25},
            "immobiliare": {"scraped_basic": 25, "synced_new": 5, "touched_existing": 20},
        },
        "errors": ["err1", "err2", "err3", "err4", "err5"],
    }
    anomalies = detect_anomalies(sb, stats)
    assert any(a.code == "many_errors" for a in anomalies)


def test_anomaly_when_too_many_errors_is_critical():
    sb = _mock_sb_with_last_seen({"idealista": 1, "immobiliare": 1})
    stats = {
        "portals": {
            "idealista": {"scraped_basic": 30, "synced_new": 5, "touched_existing": 25},
            "immobiliare": {"scraped_basic": 25, "synced_new": 5, "touched_existing": 20},
        },
        "errors": [f"err{i}" for i in range(25)],
    }
    anomalies = detect_anomalies(sb, stats)
    crit = [a for a in anomalies if a.code == "too_many_errors"]
    assert crit and crit[0].level == "CRITICAL"


# ---------- notify_anomalies ----------

def test_notify_does_nothing_if_no_anomalies(monkeypatch):
    with patch("src.health.send_telegram") as mock_send:
        ok = notify_anomalies([])
    assert ok is False
    mock_send.assert_not_called()


def test_notify_sends_telegram_when_anomalies(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    anomalies = [
        Anomaly(level="CRITICAL", code="immobiliare_stale", message="Da 26h"),
        Anomaly(level="WARN", code="many_errors", message="5 errori"),
    ]
    with patch("src.health.send_telegram", return_value=True) as mock_send:
        ok = notify_anomalies(anomalies, run_id=42)
    assert ok is True
    assert mock_send.call_count == 1
    text = mock_send.call_args.args[0]
    assert "🚨" in text  # CRITICAL → header rosso
    assert "immobiliare_stale" in text
    assert "many_errors" in text
    assert "42" in text  # run_id


def test_notify_uses_warning_emoji_if_no_critical(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    anomalies = [Anomaly(level="WARN", code="many_errors", message="5 errori")]
    with patch("src.health.send_telegram", return_value=True) as mock_send:
        notify_anomalies(anomalies)
    text = mock_send.call_args.args[0]
    assert "⚠️" in text


# ---------- save_cycle_run ----------

def test_save_cycle_run_inserts_payload():
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": 7}]
    )
    stats = {
        "started_at": "2026-06-03T10:00:00+00:00",
        "finished_at": "2026-06-03T10:05:00+00:00",
        "portals": {"idealista": {"synced_new": 5}},
        "errors": ["e1"],
    }
    run_id = save_cycle_run(sb, stats, [
        Anomaly(level="WARN", code="x", message="y"),
    ])
    assert run_id == 7
    sb.table.assert_called_with("cycle_runs")
    payload = sb.table().insert.call_args.args[0]
    assert payload["duration_s"] == 300
    assert payload["stats"] == {"idealista": {"synced_new": 5}}
    assert payload["errors"] == ["e1"]
    assert payload["anomalies"][0]["code"] == "x"
