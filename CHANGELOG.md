# CHANGELOG

Storico delle modifiche significative al bot. Formato: `[versione/data] cosa è cambiato + perché`.

---

## 2026-06-22 — Cron ridotto a 3 run/giorno ⏰

Da `*/3 ore` (8 cycle/giorno) a **3 cycle/giorno**: 12:00 / 18:00 / 21:00 IT.

**Motivo**: il consumo BirdProxies a regime è ~9 MB/cycle. Con 8 cycle/giorno
si esaurirebbe il GB di test in ~13 giorni; con 3 cycle/giorno dura **~38 giorni**.

**Copertura**: Milano fa ~4 nuovi privati/giorno → margine 80x sulla capacità
(8 pagine = 240 listings/cycle). Zero rischio di perdere annunci nel gap.

---

## 2026-06-22 — BirdProxies residenziali IT 🐦

**Problema risolto**: dal 20/06 ca. Scrapfly free tier (1000 credit) esaurito → 429 ogni request. Su Actions, fallback `curl_cffi` diretto blocccato da DataDome (IP datacenter Microsoft) → 403 sia su Idealista che Immobiliare. Cycle id=50 (22/06): 0 listings scraped, 3 anomalie CRITICAL.

**Fix**: integrato **BirdProxies** (pool residenziale italiano sticky 1h) come provider prioritario in `src/proxy.py`. Session ID generato random per ogni request → IP rotation automatica.

**Nuovo ordine smart_get**: BirdProxies → Scrapfly → Bright Data → curl_cffi diretto.

**Env vars**:
- `BIRDPROXIES_ENABLED=true` → attiva il provider
- `BIRDPROXIES_HOST/PORT/PASSWORD` → credenziali pool

**Strategia anti-spreco GB**: locale `.env` ha `ENABLED=false` (curl_cffi diretto basta), Actions ha `ENABLED=true` hardcoded nel workflow → il GB lo brucia solo il cron cloud.

**Validato locale**: Idealista 200, Immobiliare 200, IP residenziale IT verificato.

---

## 2026-06-17 — Fix timeout Actions ⚡

**Problema risolto**: dal 15/06 in poi il cron Actions andava in timeout a 30 min, GitHub cancellava il job, niente cycle_runs salvato, niente notifiche Telegram.

**Causa accumulata**: feature aggiunte negli ultimi 10 giorni (sync foglio Google, enrich detail Immobiliare, published_at, multi-chat Telegram) avevano portato la durata del cycle da 10 → 30+ min.

**Fix**:
- `timeout-minutes` workflow Actions: **30 → 45 min**
- `--max-pages` cycle: **15 → 8** (paginazione dinamica ferma comunque prima quando il backlog è esaurito; safety cap inferiore)
- Nuova **soft deadline 25 min** in `run_cycle()`: se Idealista finisce tardi, Immobiliare viene skippato → `save_cycle_run` parte sempre + notifiche garantite. Immobiliare ripreso al cycle successivo.

---

## 2026-06-13 — Apps Script "universal" + schema snello a 11 colonne 📊

**Schema foglio**: rimosse `Portale` (visibile da URL), `Spese`, `Totale`, `Status` (mark_stale dava falsi positivi).

**Schema finale**:
```
URL · Inserzionista · Telefono · Zona · Prezzo €/mese · Mq · Locali ·
Indirizzo · Pubblicato il · Visto il · Contattato
```

**Apps Script `migrateHeader`**: ora gestisce **add + remove + reorder** delle colonne (non più solo "aggiunta"). Una volta deployato, modifiche future allo schema sono automatiche dal codice Python.

**Backup persistente Contattato**: nuova colonna DB `listings.manually_contacted_at`. Prima di ogni sync, `pull_contacted_status_from_sheet()` legge il foglio e salva i "Sì" in DB. Se cancello la tab per errore, i "Sì" ritornano al sync successivo. **Mai più perdere uno stato manuale.**

---

## 2026-06-10 — Routing notifiche Telegram per tipo 📱

Prima: tutti i destinatari ricevevano tutto. Ora:
- `TELEGRAM_CHAT_ID_LISTINGS` → annunci privati nuovi (Paolo + cislyfree)
- `TELEGRAM_CHAT_ID_ANOMALIES` → solo errori bot (solo cislyfree)
- `TELEGRAM_CHAT_ID` → fallback se le specifiche non sono settate

Paolo riceve **solo** le segnalazioni utili, niente rumore tecnico.

---

## 2026-06-08 — Sync foglio Google via Apps Script Webhook 📋

Bot scrive **tutti i privati attivi** nel foglio "Bot Affitti" ad ogni cycle (3h).

**Architettura**: Apps Script Web App "anyone access" → POST JSON con righe → preserva colonna `Contattato` modificata manualmente da Paolo.

**Dedup**: chiave = URL annuncio. Update preserva utente-edited, nuovo append con `Contattato="No"` di default.

---

## 2026-06-10 — Spese condominio + total_eur 💰

Estratti automaticamente:
- **Immobiliare**: campo strutturato `costs.condominiumExpenses` (formato "€ 470/mese")
- **Idealista**: regex IT sulla description (pattern: "spese condo 70€", "+ Euro 80", "150€ di spese", ecc.)

Nuovo campo `total_eur = price + expenses` per filtro "canone tutto incluso".

---

## 2026-06-04 — Enrich detail Immobiliare 🏠

Per ogni privato Immobiliare senza phone nel listing, il bot ora fetcha la pagina detail e cerca:
- `advertiser.supervisor.phones` (privati che hanno autorizzato il numero)
- mining dei numeri offuscati nella descrizione (`3.3.5.7.4.2.0.0.6.3` → `+393357420063`)
- skip `aiCallable=true` (numero AI proxy, non utile)

Copertura phone Immobiliare: 1/10 → ~3-4/10.

---

## 2026-06-03 — Health monitoring + alert Telegram 🚨

Tabella `cycle_runs` per audit. Funzioni:
- `detect_anomalies()`: rileva portal_no_activity, portal_stale (>24h), too_many_errors
- `notify_anomalies()`: alert Telegram con livello (CRITICAL/WARN)
- `save_cycle_run()`: persiste stats + errori + anomalie

---

## 2026-06-02 — Bypass DataDome con curl_cffi safari17 🔓

Immobiliare bloccava da cron Actions cloud. Soluzioni:
- Scrapfly Web Scraping API (anti-bot built-in, ~$30/mese a regime)
- Bright Data Web Unlocker (PAYG, prefund $25-50)
- Fallback: curl_cffi con TLS impersonate Safari iOS (gratis, funziona localmente)

Modulo `src/proxy.py` con `smart_get()` che usa rotation Scrapfly → Bright Data → curl_cffi diretto.

---

## 2026-05-31 — Telegram multi-chat 📲

`TELEGRAM_CHAT_ID` ora accetta lista separata da virgola. Send to all, OK se almeno uno success. Paolo (5434276318) + cislyfree (1243074559).

---

## 2026-05-29 — MVP 🚀

Setup iniziale:
- Scraper Idealista (API JSON nascoste, no HTML parsing)
- Scraper Immobiliare (`__NEXT_DATA__` JSON)
- Schema Supabase: listings, contacts, listing_contacts, outreach_log
- Dedup multi-livello (URL annuncio, phone normalizzato E.164)
- Cron GitHub Actions ogni 3h
- Dashboard Streamlit per consultazione
