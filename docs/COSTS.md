# 💰 Analisi costi infrastruttura

## Volume reale del sistema (misurato 2026-06-03)

Media ultimi 7 giorni:
- **Idealista**: 66 nuovi annunci/giorno (3 privati)
- **Immobiliare**: 57 nuovi annunci/giorno (8 privati)

A regime (cron ogni 3h, 8 cycle/giorno):

| Portale | Req/cycle | Req/mese | Banda |
|---|:-:|:-:|:-:|
| Idealista (listing + 2 API call per nuovo) | ~20 | **~4.700** | ~75 MB |
| Immobiliare (listing + enrich detail solo privati) | ~4 | **~1.000** | ~160 MB |
| **TOTALE** | ~24 | **~5.700** | ~235 MB |

> 💡 Volume **molto basso** (sotto i 200 req/giorno) → permette di usare anche tier piccoli dei servizi paid.

---

## 🏆 Stima costi Bright Data Web Unlocker

L'utente ha configurato un account Bright Data (`customer hl_ff05e3c6`) con $2 di credito.

| Pricing tier | $/1k req | Costo mese (5.7k req) | Note |
|---|:-:|:-:|---|
| Web Unlocker standard | $1.50 | **~$9** | siti "facili" |
| Web Unlocker DataDome premium | $3.00 | **~$17** | nostro caso |

**Con $2 di credito iniziali**:
- Scenario standard: ~1.300 req (≈ 7 giorni di traffico)
- Scenario premium: ~670 req (≈ 3.5 giorni di traffico)

Sufficiente per validare la pipeline e capire se serve fare scale-up.

---

## 📋 Confronto di tutte le opzioni considerate

### A) Self-hosted runner (zero costo ma fragile)

| Soluzione | Costo | Pro | Contro |
|---|:-:|---|---|
| GitHub Actions cloud (status quo) | 0€ | gratuito | IP cloud → 403 Immobiliare |
| Self-hosted runner su Mac di Paolo | 0€ | IP residenziale IT | Mac deve restare acceso, scalabilità zero |
| Self-hosted runner su Raspberry Pi 5 | 80€ una tantum + ~1€/mese | hardware tuo, IP casa | dipende dalla tua linea, manutenzione |

### B) VPS proprio

| Soluzione | Costo/mese | Pro | Contro |
|---|:-:|---|---|
| Hetzner CX22 datacenter | 4.50€ | controllo totale | IP datacenter → DataDome blocca |
| Aruba VPS Smart | 3€ | server IT | IP datacenter, perf modesta |
| Hetzner + Bright Data residential proxy | 4.50€ + ~$15 = ~€18 | IP residenziale rotation | setup complesso |
| VPS con IP italiano ISP (PrivateRouter, Vapor) | 8-15€ | residenziale dedicato | provider piccoli, rischio outage |

### C) Servizi anti-bot managed (consigliato per noi)

| Servizio | Piano starter | Req anti-bot incluse | Costo/req DataDome |
|---|:-:|:-:|:-:|
| **Bright Data Web Unlocker** (pay-as-you-go) | $0 base, pay-per-request | illimitate | **$1.5–3 / 1k** |
| Scrapfly Discovery | $30/mese | ~8.000 anti-scraping | ~$3.75 / 1k |
| ScrapingBee Freelance | $49/mese | ~4.000 premium | ~$12 / 1k |
| ScraperAPI Hobby | $49/mese | ~20.000 premium | ~$2.5 / 1k |
| ZenRows Developer | $69/mese | ~25.000 antibot | ~$2.8 / 1k |

> **Bright Data Web Unlocker** è il più conveniente sul nostro volume (~$9-17/mese effettivi, pay-per-use).

### D) Proxy puri (senza captcha solving — DIY)

Più economici ma richiedono che il nostro codice gestisca i 403:

| Servizio | Costo | Note |
|---|:-:|---|
| Bright Data datacenter rotating | $0.5/GB | IP cloud, DataDome lo riconosce |
| Bright Data residential | $7/GB | ~140k req nostro size → ~$10/mese |
| Bright Data ISP static | $15/GB | premium quality |
| Oxylabs residential | $10/GB | simile a Bright |
| Smartproxy residential | $8/GB | discreto |

Per il nostro volume (~250MB/mese) costerebbero ~$2-4/mese, MA richiede gestione retry sul nostro codice e rischio di 403 maggiore vs Web Unlocker.

---

## 🆓 Onesta sui free tier "puri"

Per il nostro volume (1000 req DataDome/mese) **nessun free tier puro basta**:

| Servizio | Free credits | Req DataDome incluse | % del fabbisogno |
|---|---|:-:|:-:|
| Scrapfly free | 1000 cr (one-shot) | 40 | 4% |
| ScrapingBee free | 1000 cr (one-shot) | 40 | 4% |
| ScraperAPI free | 5000 req (7 giorni) | 250 | 25% |
| ZenRows free | 1000 cr (mensile) | 40 | 4% |
| **Combo di 4 in rotation** | — | ~120/mese | ~12% |
| Apify $5 mensile | 5000 req | 0 con anti-bot (proxy datacenter blacklist) | 0% |
| Tor / Cloudflare Workers / Oracle Cloud Free / Fly.io | illim. | 0 (IP cloud blacklist) | 0% |

**Conclusione**: per coprire 1000 req/mese DataDome serve **almeno un servizio paid OR self-hosted runner** sul Mac/RPi (IP residenziale).

## 🎯 Raccomandazione

### 🥇 Migliore rapporto p/q: **Scrapfly Discovery $30/mese**

Motivazione del primato (verificato al 2026-06-03):

| Criterio | Scrapfly | Bright Data PAYG | ScraperAPI | ScrapingBee | Apify |
|---|:-:|:-:|:-:|:-:|:-:|
| Costo mese reale (1000 req DataDome) | **$30** | ~$10 | $49 | $49 | $5 (ma DataDome ❌) |
| Free credits per testare | 1000 cr (subito) | $5 (verifica) | 5k req trial 7gg | 1000 one-shot | $5 mensile |
| Prefund richiesto? | **no** | sì ($25-50) | no | no | no |
| Cancellabile in 1 click? | **sì** | sì | sì | sì | sì |
| Setup (minuti) | **3** | 10 (prefund flow) | 5 | 5 | 5 |
| Margine sul volume nostro | 8× | illim. | 10× | 4× | ❌ (DataDome) |
| SDK Python | **eccellente** | buono | buono | discreto | buono |
| Dashboard consumi | **chiara** | buona | discreta | discreta | ricca |
| Probabilità bypass DataDome | >95% | >95% | >90% | >90% | <30% |

**Perché vince Scrapfly sui prezzi più bassi (Bright Data)**:
- Niente prefund: parti con $0
- 1000 free credits = ~40 chiamate DataDome → puoi testare il flow REALE prima di pagare un centesimo
- Costo $30 fisso prevedibile (no sorprese bolletta)
- Pagamento mensile con carta, cancellabile

**Bright Data conviene SE**:
- Ti consolidano sopra i 3000 req/mese DataDome
- Paghi il prefund di $25-50 una tantum
- A regime: ~$10/mese vs $30 Scrapfly

### 🏗️ Implementazione

Già nel codice: [`src/proxy.py`](../src/proxy.py) supporta **entrambi** in rotation:
1. Se `SCRAPFLY_API_KEY` settato → usa Scrapfly
2. Altrimenti se `BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE` → usa Bright Data
3. Altrimenti curl_cffi diretto (free, ma 403-prone)

Quindi puoi:
- **Mese 1**: usare il free trial Scrapfly (1000 credits) + curl_cffi fallback
- **Mese 2+**: attivare Scrapfly Discovery $30/mese
- **Eventuale switch a Bright Data**: setti solo le env, zero cambio codice

### Strategia ibrida 3 livelli (cost-optimized)

```
┌─────────────────────────────────────────────────────────────────┐
│ TIER 1 — Cloud free (Idealista, fino a quando funziona)         │
│   GitHub Actions ubuntu-latest                                  │
│   Costo: 0€/mese                                                │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ Idealista 403?
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ TIER 2 — Bright Data Web Unlocker on/off (sempre attivo per     │
│   Immobiliare, attivabile per Idealista se DataDome cambia)     │
│   Costo: ~$9-17/mese pay-per-use, scala con il traffico         │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ Bright Data troppo costoso?
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ TIER 3 — Fallback Raspberry Pi a casa                           │
│   Una tantum: 80€  ·  Ricorrente: ~1€/mese elettricità          │
└─────────────────────────────────────────────────────────────────┘
```

Già implementato: smart_get usa Bright Data se `BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE` sono settati, altrimenti fallback automatico a curl_cffi diretto. Lo switch è zero-touch.

### Budget di partenza consigliato

- **Mese 1**: usa i **$2 di credito Bright Data esistenti** + GitHub Actions free → costo 0
- **Mese 2-3**: se i lead Immobiliare giustificano, ricarica $20 → ~2 mesi di copertura totale
- **Mese 4+**: a regime ~$15/mese sostenibile se il bot porta clienti

### ROI atteso

Con 8 nuovi privati Immobiliare + 3 Idealista al giorno = **~330 lead/mese**.

Anche con tasso di conversione conservativo:
- 330 lead × 5% risposta = 16 risposte/mese
- 16 risposte × 10% conversione = 1.6 clienti/mese

Un cliente Paolo Vailati di gestione affitti medio-termine ha valore medio annuo significativo. **Il break-even è 1 cliente ogni 4-6 mesi** rispetto a un costo proxy di ~$15/mese × 12 = $180/anno.

---

## 🔧 Setup Scrapfly (3 minuti)

1. Vai su [scrapfly.io](https://scrapfly.io) → **Sign up** (con email Google o GitHub)
2. **Account → API Key** (in alto a destra del dashboard) — copia la `scp-live-...` key
3. Aggiungila a:
   - **`.env` locale** → `SCRAPFLY_API_KEY=scp-live-xxxxxxxxxxxx`
   - **GitHub Actions secrets** → [github.com/KKBene/bot-immobiliare/settings/secrets/actions](https://github.com/KKBene/bot-immobiliare/settings/secrets/actions) → nuovo secret `SCRAPFLY_API_KEY`
4. Lancio cycle locale di test: `python scripts/run_cycle.py --max-pages 5`
5. Sulla dashboard Scrapfly vedi i crediti consumati in tempo reale

Il free tier ti dà ~40 chiamate DataDome → sufficiente per verificare che Immobiliare risponda 200 invece di 403. Se ok, upgrade a Discovery $30/mese in 1 click.

## 🔧 Setup Bright Data (5 minuti)

1. [brightdata.com/cp/zones](https://brightdata.com/cp/zones) → **Add zone**
2. Tipo: **Web Unlocker** (preset DataDome-aware)
3. Nome: a scelta (es. `web_unlocker_aste`)
4. Country: **Italy** (per IP italiano)
5. Salva e copia il nome zone
6. Aggiungilo a:
   - **`.env` locale** → `BRIGHTDATA_ZONE=nome_zone`
   - **GitHub Actions secrets** → `BRIGHTDATA_API_KEY` e `BRIGHTDATA_ZONE`
   - **Streamlit Cloud secrets** (non serve, la dashboard non scrappa)

Da quel momento il bot routa automaticamente via Bright Data. Se la zone non funziona o esauriscono i crediti, **fallback automatico** a curl_cffi diretto (gratis, ma soggetto a 403).

## Monitoraggio costi

Dashboard Bright Data → Usage → vedi req consumate / credito residuo. Imposta alert email a $5 residuo come safety net.
