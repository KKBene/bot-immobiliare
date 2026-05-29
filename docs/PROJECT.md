# 🏠 BOT_IMMOBILIARE

> Monitora Idealista + Immobiliare a Milano, intercetta nuovi affitti da privati,
> normalizza in un CRM Supabase, prepara messaggi SMS personalizzati per
> proporre **gestione affitti a medio termine**. Cliente: Paolo Vailati.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   📡  scrape (ogni 3h)      🧠  enrich           💾  store               │
│        Idealista + Immo.  →   phone via API   →   Supabase 5 tabelle     │
│              │                     │                    │                │
│              ▼                     ▼                    ▼                │
│      📨  outreach engine    🛡️  gate            🚀  send (Twilio)        │
│        compose SMS       →   no dup + opt-out  →   long code +39         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Stato d'arte

| Step | Cosa | Test | Stato |
|:-:|:--|:-:|:-:|
| 1 | Scraper Immobiliare lista Milano (`curl_cffi` chrome) | 9 | ✅ |
| 2 | Schema Supabase 5 tabelle + idempotenza + dedup contatti | 29 | ✅ |
| 3 | Regex contatti IT + paginazione | 22 | ✅ |
| 4 | **Idealista API-only**: telefono in chiaro via JSON | 7 | ✅ |
| ~~5~~ | ~~Reveal headless con account burner~~ | — | 🚫 obsoleto |
| 6 | Outreach engine (composer + dry-run + gate) | 16 | ✅ |
| 7 | Twilio SMS live | — | ⏳ attende account Paolo |
| 8 | Phone Immobiliare via `__NEXT_DATA__` detail | — | 🟡 funzionale, da integrare |
| 9 | Master cycle + Dockerfile + GitHub Actions | — | ✅ |
| 10 | Dashboard read-only | — | 💡 future |

**`83/83` test passing.** Run cycle reale: **~60s** per 1+1 pagine.

---

## 🎯 Scoperta che vale il progetto

Idealista nasconde nel `var config` del detail page **gli URL AJAX del frontend**.
Tra di essi:

```
/it/ajax/listingController/adContactInfoForDetail.ajax?adId={X}
    └─→ { isAdProfessional, firstName, commercialName, adTypologyName, ... }

/it/ajax/ads/{X}/contact-phones
    └─→ { phone1: { formatted: "335 742 0063",
                    number: "+393357420063" } }
```

Entrambi restituiscono **JSON puro senza login**, con TLS fingerprint Safari iOS
(`curl_cffi impersonate="safari17_2_ios"`).

**Conseguenza**: lo Step 5 (reveal headless con account burner + Playwright)
non serve. Tutto via HTTP stateless. **Niente browser, niente account, niente
proxy a pagamento** per la pipeline base.

> ⚠️ Trappola: usando `creq.Session()` persistente, DataDome marca il cookie
> `datadome` come bot al 2° AJAX → 403. Le chiamate devono essere stateless,
> una per request.

---

## 🗄️ Schema dati (Supabase)

```
┌────────────────────┐         ┌────────────────────┐         ┌────────────────────┐
│      LISTINGS      │◄────────│  LISTING_CONTACTS  │────────►│      CONTACTS      │
├────────────────────┤         ├────────────────────┤         ├────────────────────┤
│ id                 │         │ listing_id (FK)    │         │ id                 │
│ portal             │         │ contact_id (FK)    │         │ phone_e164  UNIQUE │
│ external_id        │         │ role               │         │ email       UNIQUE │
│ url                │         │                    │         │ display_name       │
│ price_eur          │         └────────────────────┘         │ kind  (priv/agency)│
│ surface_m2         │                                        │ opted_out_at       │
│ advertiser_type    │                                        │ do_not_contact     │
│ ...                │                                        │ first/last_seen_at │
│ first/last_seen_at │                                        └────────────────────┘
│ scraped_count      │                                                  ▲
│ UNIQUE(portal,     │                                                  │
│       external_id) │                                                  │
└────────────────────┘                                                  │
        ▲                                                               │
        │                                                               │
        │       ┌────────────────────┐                                  │
        └───────│   OUTREACH_LOG     │──────────────────────────────────┘
                ├────────────────────┤
                │ id                 │
                │ contact_id (FK)    │
                │ listing_id (FK)    │
                │ channel (sms/...)  │
                │ status             │  queued|sent|delivered|failed|replied|opted_out
                │ message            │
                │ provider_id        │  twilio sid
                │ queued/sent_at     │
                └────────────────────┘

┌────────────────────┐
│   PORTAL_ACCOUNTS  │   (riserva strategica per form-portale se mai servirà)
├────────────────────┤
│ id, portal, email  │
│ password_enc       │
│ status             │  active|cooldown|banned
│ reveals_today      │
│ forms_today        │
│ last_used_at       │
│ cooldown_until     │
└────────────────────┘
```

### Dedup multi-livello

| Livello | Chiave | Scenario |
|---|---|---|
| **Annunci** | `(portal, external_id)` | Re-scrape → `UPDATE` con `last_seen_at` + `scraped_count++` |
| **Contatti** | `phone_e164` o `email` | "02 8736 4229", "+39 02 8736 4229", "0039 02 87364229" → 1 record |
| **Outreach** | `(contact_id, channel) recent` | No doppio invio entro 90gg; `opted_out_at` blocca per sempre |

---

## 📁 Layout repo

```
BOT_IMMOBILIARE/
├── src/
│   ├── models.py             # Dataclass Listing (24 campi)
│   ├── normalize.py          # phone IT → E.164, email lowercase
│   ├── db.py                 # client Supabase + upsert + gate outreach
│   ├── pipeline.py           # master cycle (Idealista + Immobiliare)
│   ├── outreach.py           # compose SMS + prepare_batch + queue
│   └── scrapers/
│       ├── immobiliare.py    # curl_cffi chrome, parse __NEXT_DATA__
│       └── idealista.py      # curl_cffi safari17_ios, 2 endpoint AJAX
├── scripts/
│   ├── run_step1.py          # scrape Immobiliare standalone
│   ├── run_step2.py          # sync DB
│   ├── run_step4.py          # scrape Idealista con --enrich
│   ├── run_step6.py          # outreach dry-run / queue
│   └── run_cycle.py          # MASTER: tutto in uno
├── sql/01_schema.sql         # schema DDL idempotente
├── tests/                    # 83 test (offline + integration)
│   ├── fixtures/             # HTML salvati per riproducibilità
│   └── test_*.py
├── docs/
│   ├── PROJECT.md            # questo file
│   └── ANTI_DETECTION.md     # analisi anti-tracking
├── Dockerfile + .dockerignore
├── .github/workflows/scrape-cycle.yml   # cron 3h
├── .env / .env.example       # credenziali (gitignored)
└── README.md
```

---

## 🚀 Quickstart

```bash
PY=/Users/macbook/Desktop/Code/.venv/bin/python3

# Test tutti
$PY -m pytest tests/                        # 83 in ~70s

# Cycle scrape + sync (Idealista + Immobiliare)
$PY scripts/run_cycle.py --idealista 2 --immo 2

# Outreach dry-run (vedi messaggi senza inviare)
$PY scripts/run_step6.py --limit 5

# Outreach con accodamento DB (status=queued, pronto per Twilio)
$PY scripts/run_step6.py --queue
```

### Deploy

| Opzione | Costo | Affidabilità | Setup |
|---|---|---|---|
| **GitHub Actions** (file `.github/workflows/scrape-cycle.yml`) | 0€ | 🟢🟢 | Push repo + Secrets `SUPABASE_*` |
| Railway + cron | ~5€/mese | 🟢🟢🟢 | Connect repo + cron tab |
| VPS + crontab | ~5€/mese | 🟢🟢🟢 | SSH + crontab + .env |

---

## 📈 Risultati real-world

Dopo un cycle reale su Milano pagina 1:

- Idealista: 30 annunci, **2 privati con telefono** (Vincenzo, Marino)
- Immobiliare: 25 annunci, **0 privati** (vetrina è 100% agenzie)
- Pagine 5-12 Immobiliare: 1 non-agenzia su 200 → **Immobiliare ha pochissimi privati**

### Take-away strategico

> Per il target "privati che pubblicano affitti", **Idealista è il portale primario**.
> Immobiliare resta utile per monitoring del mercato e contatto con piccole
> agenzie (potenziali partner / clienti di gestione).

---

## 🔐 Sicurezza & GDPR

- `.env` gitignored, mai committato
- Credenziali Supabase + portali in env-vars su CI
- Gate opt-out applicata su ogni outreach
- Registro completo in `outreach_log` per accountability
- Cold SMS commerciali a privati italiani: **base giuridica legittimo interesse**
  (Art. 6(1)(f) GDPR + Art. 130 Codice Privacy) — richiede:
  - Informativa concisa nel messaggio (chi sei + come optarsi out)
  - Registro dei contatti e degli opt-out
  - Sospensione immediata su richiesta dell'interessato

Per il dettaglio dei vettori di tracciamento e delle contromisure, vedi
[`ANTI_DETECTION.md`](./ANTI_DETECTION.md).

---

## 🛣️ Roadmap residua

1. **Step 8 integration**: aggiungere `enrich_with_detail()` allo scraper Immobiliare
   (replica del pattern Idealista, usando `__NEXT_DATA__` della detail page)
2. **Step 7 Twilio live**: 50 righe di codice dopo registrazione account
3. **Mitigazioni anti-detect**: jitter cron, UA rotation, circuit breaker
4. **Dashboard read-only**: Streamlit o Supabase web → vista funnel
   `nuovo → contattato → risposto → cliente`
5. **Webhook STOP**: endpoint che riceve risposte SMS Twilio → `mark_opted_out`

---

<p align="center"><em>Built with curl_cffi · BeautifulSoup · Supabase · pytest</em></p>
