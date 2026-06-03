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

## 🎯 Raccomandazione

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
