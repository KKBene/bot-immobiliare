# BOT_IMMOBILIARE

Scraper Immobiliare.it + Idealista.it per Milano. Intercetta nuove inserzioni di
affitto e prepara outreach (SMS Twilio + form portale) per proporre la gestione
in affitto a medio termine.

## Stato (83 test passing)

- [x] **Step 1** — Scraper Immobiliare lista Milano (`curl_cffi` chrome bypassa DataDome)
- [x] **Step 2** — Schema Supabase 5 tabelle + idempotenza + dedup contatti + outreach gate
- [x] **Step 3** — Regex contatti IT + paginazione
- [x] **Step 4** — Scraper Idealista **API-only**: scoperti 2 endpoint AJAX (`adContactInfoForDetail`, `contact-phones`) che restituiscono telefono in chiaro
- [x] **Step 5 SALTATO** — phone arriva via API, non serve reveal headless
- [x] **Step 6** — Outreach engine (composer + dry-run + gate integrata)
- [x] **Step 9** — Master cycle + Dockerfile + GitHub Actions cron 3h
- [ ] Step 7 — Outreach SMS Twilio live (Paolo registra account)
- [ ] Step 8 — Immobiliare phone reveal API (parking)
- [ ] Step 10 — Dashboard read-only

## Architettura

```
┌────────────────────────────────────────────────────────────┐
│  scripts/run_cycle.py (cron ogni 3h)                       │
└────────────────────────────────────────────────────────────┘
            │
   ┌────────┴────────┐
   ▼                 ▼
[Idealista]      [Immobiliare]
 - listing HTML   - listing __NEXT_DATA__
 - dedup DB       - dedup DB
 - per nuovi:     - sync
   info+phones
   API JSON
   ↓
[src/db.py] → upsert listings + contacts (dedup phone_e164) + link

[src/outreach.py]
   prepare_batch → can_outreach (gate: opt-out + no doppio invio) →
   queue_outreach (status=queued) → [Twilio send]
```

## Comandi principali

```bash
PY=/Users/macbook/Desktop/Code/.venv/bin/python3

# Test tutti
$PY -m pytest tests/

# Cycle completo (scrape + sync)
$PY scripts/run_cycle.py --idealista 2 --immo 2

# Outreach dry-run (vedi messaggi senza inviare)
$PY scripts/run_step6.py --limit 5

# Outreach con accodamento in DB (status=queued)
$PY scripts/run_step6.py --queue

# Dashboard (Streamlit) → http://localhost:8501
$PY -m streamlit run dashboard/app.py
```

## Dashboard

3 pagine + Home (KPI + grafici):

| Pagina | Cosa |
|---|---|
| 🏠 Home | KPI (annunci, contatti, outreach) + grafici per portale × inserzionista, prezzi, top zone, funnel, timeline |
| 📋 Listings | Tabella filtrabile (portale, tipo inserzionista, range prezzo, zona, full-text) + export CSV |
| 👤 Contatti | Tabella con join numero-annunci + azioni manuali opt-out / do-not-contact / riattiva |
| 📨 Outreach | Funnel status + breakdown canale + log filtrato con join contact + listing |

Auth opzionale: imposta `DASHBOARD_PASSWORD` in `.env` per attivarla.

## Setup

```bash
# venv condivisa già a /Users/macbook/Desktop/Code/.venv
pip install -r requirements.txt
cp .env.example .env   # già compilato per questo deploy
```

## Comandi

```bash
# Run scraper live (Step 1)
python scripts/run_step1.py
python scripts/run_step1.py --save-fixture   # rigenera fixture per i test

# Test
pytest -v
```

## Deploy in cloud

Tutto gratis — dashboard sempre online + cron auto: vedi [`docs/DEPLOY.md`](docs/DEPLOY.md).

Riepilogo: GitHub repo + Streamlit Community Cloud (dashboard) + GitHub Actions (cron 3h) + Supabase (DB).

## Note legali

- Cold SMS commerciali a privati in Italia richiedono opt-out chiaro e base
  giuridica documentata (art. 130 Codice Privacy).
- Form portale automatizzato viola TOS Immobiliare/Idealista → account
  burner, mai usare account personali.
