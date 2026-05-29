# 🛡️ ANTI-DETECTION & ANTI-TRACKING

> Come Idealista, Immobiliare, Twilio, WhatsApp, gli inserzionisti e (in
> ultima analisi) il Garante Privacy ci possono tracciare — e cosa stiamo
> già facendo o dovremmo fare per minimizzare la superficie.

```
   👤 Tu                       ⚙️ Bot                       🎯 Portali / Twilio / Destinatari
                  ─────HTTP────►                  ─────SMS────►
   ◄────metric─── │ Vettori   │ ◄───metric────  │ Vettori
                  │ trackabili│                 │ trackabili
                  └───────────┘                 └───────────┘
```

---

## 1. Modello di minaccia

Non tutti i "tracciatori" sono uguali. Mappa rapida:

| Attore | Cosa vuole capire | Cosa fa se ci becca |
|---|---|---|
| **DataDome** (Idealista, Immo.) | "Sei un bot?" | 403, captcha, IP ban temporaneo (ore) |
| **Idealista/Immobiliare backoffice** | "Stai facendo scraping massivo?" | Ban IP/account, segnalazione legale (raro) |
| **Twilio compliance** | "Spam? Phishing?" | Sospensione account, perdita numero |
| **Operatori telefonici IT (TIM, Voda)** | "Numero che spamma?" | Filtering, scoring sender |
| **Destinatari SMS** | "Chi è? Spam?" | Block numero, segnalano al 4884 (anti-spam) |
| **Garante Privacy** | "Cold marketing senza consenso?" | Ammenda 20k–200k€, ordine di cessazione |

**Implicazione**: difenderci da DataDome non basta. Twilio reputation, sender
score e GDPR sono fronti separati con i loro segnali e mitigazioni.

---

## 2. Come ti traccia DataDome (anti-bot dei portali)

DataDome è un servizio anti-bot che firma ogni request con uno score di
"botness" sommando segnali su 5 layer:

### 2.1 TLS fingerprint (JA3 / JA4)
La sequenza di cipher offerti, l'ordine, le estensioni e le curve forniscono
una "impronta digitale" del client TLS. Python `requests` ha un JA3 noto come
bot. Browser reali hanno JA3 specifici per Chrome/Safari/Firefox/versione.

> ✅ **Già mitigato**: usiamo `curl_cffi impersonate="chrome"` (Immobiliare)
> e `impersonate="safari17_2_ios"` (Idealista). Stessa libreria curl-impersonate
> riproduce TLS handshake e ALPN reali.

### 2.2 HTTP/2 frame order
HTTP/2 ha campi opzionali (`SETTINGS_HEADER_TABLE_SIZE`, ordine pseudo-headers
`:method/:path/:scheme/:authority`). Ogni browser ha un ordine canonico.
curl normale ha ordine "atipico" rilevabile. Anche questo è impersonato
da curl_cffi.

> ✅ **Già mitigato** stesso pacchetto.

### 2.3 Cookie behaviour (il vero motivo del 403 con Session)
DataDome emette un cookie `datadome` alla prima visita. Il JS del sito
emette poi un POST a `dd.idealista.it/js/` con segnali ambientali del browser
(window, screen, canvas, ecc.). Se quel POST non arriva, il cookie viene
marcato "challenged" e nuove request con quello stesso cookie tornano 403.

> ✅ **Già mitigato**: chiamate **stateless** (`creq.get()` senza Session).
> Ogni request riceve un cookie fresco e non viene "downgradata".
> Vedi `src/scrapers/idealista.py:78-83` con il commento esplicativo.

### 2.4 IP reputation
- **Data-center IP** (AWS, GCP, Hetzner) sono in blacklist condivisa →
  challenge immediato.
- **Residential proxies** (Bright Data, Smartproxy, Oxylabs): IP di ISP
  retail → trattati come utenti reali.
- **Cellular IPs** (4G/5G): i più puliti.

> ⚠️ **Mitigazione consigliata**: per scrape continuo da VPS è meglio
> aggiungere un proxy residenziale ($15-25/GB). Per ora, dal Mac di Paolo
> via ISP retail = OK.

### 2.5 Volume + cadenza
Bot fa N request/min in pattern regolare. Umani hanno burst irregolari,
pause, scroll, errori.

> ⚠️ **Mitigazione**: introduciamo **jitter** sul cron (3h±15min) e sulle
> sleep tra detail (1.5s ± 0.5s). Vedi §6.

---

## 3. Come ti traccia Twilio (anti-spam SMS)

Twilio non ti vuole come cliente se sei spammer (perderebbero accreditamento
operatori). Segnali su cui ti scorano:

| Segnale | Soglia tipica | Conseguenza |
|---|---|---|
| **Throughput** | >1 SMS/sec da long code | Throttle |
| **Opt-out rate** | >2% dei destinatari risponde STOP | Account review |
| **Spam keyword score** | parole "vinci", "guadagna", "click qui" | Filtraggio operatore |
| **Reply rate basso** | <1% risponde | Sender score scende |
| **Reportage al 4884** | utente segnala spam → operatore IT | Numero blacklistato |
| **Volume cold outbound** | nuovo account + 50 msg/h al primo giorno | Sospensione |

> ⚠️ **Mitigazioni quando Paolo configura Twilio**:
> 1. Warmup graduale (giorno 1: 5 SMS; giorno 2: 10; ... → 40 a regime)
> 2. Daily cap configurabile in `.env` (default 40)
> 3. STOP funziona davvero: webhook Twilio → `mark_opted_out`
> 4. No parole spam-trigger ("guadagna", "soldi", "clicca")
> 5. Identificazione chiara ("Paolo Vailati") nel messaggio
> 6. Sender ID alfanumerico **registrato AGCOM** appena possibile
>    (long code +39 OK per partire, ma soggetto a filtering operatore)

---

## 4. Come ti traccia il destinatario (e il Garante)

Il vero rischio reputazionale e legale viene dai destinatari. Se 3 persone
su 100 sporgono reclamo al Garante:

- Indagine + accesso a `outreach_log` se ti citano
- Ammenda 20.000-200.000€ a sentenza
- Ordine di cessazione

### 4.1 Base giuridica
Cold SMS commerciali a numeri di privati pubblicati su portali immobiliari
sono **borderline**. Le posizioni di Garante e Cassazione:

- ❌ "Bulk acquisition + cold SMS" → **vietato senza consenso** preventivo.
- 🟡 "Numero pubblicato in contesto pubblico per scopo specifico (es. vendere/affittare),
  contatto coerente con quello scopo" → tollerato come **legittimo interesse**
  (Art. 6(1)(f) GDPR), purché:
  1. Comunicazione singola, non massiva
  2. Linguaggio chiaro su chi sei
  3. Opt-out immediato
  4. Cessazione su richiesta

### 4.2 Cose da fare sempre

| Pratica | Stato nel codice |
|---|---|
| Identificazione esplicita ("Paolo Vailati") | ✅ nel template |
| Riferimento al canale di acquisizione | ⏳ aggiungibile ("annuncio su Idealista") |
| STOP per opt-out | ✅ in tutti i messaggi |
| Webhook STOP che marca opt-out in DB | ⏳ Step 7 quando arriva Twilio |
| Registro completo `outreach_log` | ✅ sempre, con `template_id` versionato |
| Cooldown 90gg per non insistere | ✅ `can_outreach()` |
| Documento privacy policy linkabile | ⏳ Paolo serve URL pubblica |

### 4.3 Cose da NON fare mai

- ❌ Inviare a numeri da elenchi acquistati / lead list
- ❌ Re-contattare chi ha detto STOP, neanche su altro canale
- ❌ Più di un canale (es. SMS + WhatsApp) sullo stesso target → segnala
- ❌ Template che non identifica il mittente (sembra phishing)
- ❌ Volume sproporzionato (60+ SMS/giorno = chiaramente massivo)

---

## 5. Risk matrix

| Rischio | Probabilità | Impatto | Mitigazione attuale | Gap |
|---|:-:|:-:|---|---|
| DataDome blocca tutto | 🟡 | 🔴 | curl_cffi impersonate + stateless | Proxy residenziale come fallback |
| Twilio sospende account | 🟡 | 🔴 | Warmup + opt-out + content | Da implementare al go-live |
| Numero +39 in blacklist | 🟡 | 🟠 | Volume basso (40/giorno) | Rotazione 2 numeri quando >30/giorno |
| Garante: reclamo singolo | 🟢 | 🟡 | Opt-out + registro | Privacy policy URL |
| Garante: reclamo multiplo | 🔴 (se >100 msg/giorno) | 🔴🔴 | — | **Capping volume hard** |
| IP del Mac in blacklist Idealista | 🟢 | 🟡 | Stateless + rate limit lato bot | Proxy se diventa quotidiano |
| Account portale (per form) banned | 🔴 (TOS) | 🟠 | — | Step 8 da evitare se possibile |

---

## 6. Mitigazioni implementate (e da implementare)

### 6.1 Già nel codice
- ✅ TLS impersonation `curl_cffi` per ogni portale
- ✅ Chiamate stateless (no Session) per evitare cookie tagging
- ✅ Sleep `1.5s` tra detail calls (`scripts/run_step4.py --sleep`)
- ✅ Sleep `3s` tra pagine in `cycle_idealista`
- ✅ Cooldown 90 giorni outreach
- ✅ ASCII-safe SMS (no UCS-2, evita raddoppio costo)
- ✅ Skip annunci già in DB (no chiamate API ridondanti)

### 6.2 Implementate in §7
- ➕ **Jitter** su sleep e cron (±20%)
- ➕ **User-Agent pool** rotation (5 UA realistic)
- ➕ **Circuit breaker**: 3 consecutivi 403 → pausa 30min
- ➕ **Retry con backoff** esponenziale su 429/5xx

### 6.3 Da implementare quando serve
- Proxy residenziale (Bright Data) — quando volume >500 req/giorno
- Pool numeri Twilio + rotazione — quando >30 SMS/giorno
- Webhook STOP (riceve SMS in arrivo) — al go-live Twilio
- Hashing IPs/UAs nel `outreach_log` per audit

---

## 7. Implementazione pratica (codice)

I prossimi commit aggiungono `src/anti_detect.py` con:

```python
@dataclass
class Backoff:
    """Retry con jitter + circuit breaker."""
    max_attempts: int = 3
    base_sleep: float = 1.5
    jitter_pct: float = 0.20         # ±20%
    cb_threshold: int = 3            # 403/429 consecutivi
    cb_pause_seconds: int = 1800     # 30 min

UAS_POOL = [
    # Safari iOS / macOS realistic UAs (matched a impersonate)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) ...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) Safari/...",
    ...
]
```

E hook il backoff in:
- `IdealistaScraper.fetch_*`
- `ImmobiliareScraper.fetch_list_html`
- `pipeline.cycle_*`

---

## 8. Decisioni esplicite (consapevoli)

| Decisione | Razionale |
|---|---|
| **No proxy** all'inizio | IP di Paolo da ISP retail è pulito. Aggiungeremo solo se DataDome diventa aggressivo o se passiamo su VPS. |
| **No browser headless** | curl_cffi + endpoint AJAX = stesso JSON di un browser, ma 1/100° del costo. CloakBrowser resta come fallback documentato. |
| **No form portale (Step 8 originale)** | Richiederebbe account burner + login + violazione TOS. Per Idealista il telefono è già esposto via API → form inutile. Per Immobiliare i privati sono <1%, non vale il rischio account. |
| **SMS solo, non WhatsApp** | WhatsApp Business API non permette cold + i servizi non ufficiali bannano il numero. SMS Twilio è legale con base giuridica corretta. |
| **Target solo `kind=private`** | Le agenzie già fanno gestione → non è il nostro cliente. Filtro implementato in `prepare_batch()`. |

---

## 9. Audit trail (cosa lasceremmo a un'ispezione)

Se Garante chiede "come dimostri il legittimo interesse?":

1. **`listings.url`**: URL pubblico dell'annuncio = prova della pubblicazione
2. **`outreach_log.message`**: testo identico inviato (template versionato)
3. **`outreach_log.queued_at` / `sent_at`**: timestamp esatto
4. **`outreach_log.responded_at`** + **`contacts.opted_out_at`**: rispetto opt-out
5. **`contacts.first_seen_at`**: quando il numero è entrato nel sistema
6. **Cap volume** documentato in `.env` (`DAILY_SMS_CAP=40`)

> 💡 **Best practice**: settimanalmente esportare `outreach_log` in un CSV
> archiviato su S3 con retention 36 mesi → audit-ready.

---

<p align="center"><em>Aggiornato: 2026-05-29 · Da rivedere a ogni cambio di vettore (Twilio go-live, proxy add, etc.)</em></p>
