# 🚀 Deploy

Architettura cloud: **3 servizi, tutti gratuiti**.

```
   ┌──────────────────┐       ┌──────────────────┐
   │  Streamlit Cloud │       │  GitHub Actions  │
   │  Dashboard 24/7  │       │  Cron 3h scrape  │
   │  HTTPS gratuito  │       │  6 run/giorno    │
   └────────┬─────────┘       └────────┬─────────┘
            │                          │
            └──────────┬───────────────┘
                       ▼
              ┌────────────────┐
              │    Supabase    │
              │   Postgres +   │
              │      Auth      │
              └────────────────┘
```

| Pezzo | Dove | Costo |
|---|---|---|
| Dashboard Streamlit | [share.streamlit.io](https://share.streamlit.io) | 0€ |
| Cron scrape ogni 3h | GitHub Actions (`.github/workflows/scrape-cycle.yml`) | 0€ (sotto soglia 2000 min/mese) |
| DB | Supabase (già configurato) | 0€ |
| Notifiche | Telegram Bot (@AFFITTI_MI_BOT) | 0€ |

---

## Step 1 — Crea il repo su GitHub

### Opzione A — Browser (più semplice)

1. Vai su [github.com/new](https://github.com/new)
2. **Repository name**: `bot-immobiliare` (o quello che preferisci)
3. **Private** (raccomandato — anche se i secret sono fuori dal repo)
4. NON aggiungere README, .gitignore, license (li abbiamo già)
5. Crea
6. Copia l'URL `git@github.com:<tuo-user>/bot-immobiliare.git`

### Opzione B — Con `gh` CLI

```bash
brew install gh
gh auth login
gh repo create bot-immobiliare --private --source=. --remote=origin --push
```

---

## Step 2 — Push del codice dal Mac

Sostituisci `<URL>` con l'URL del tuo repo (es. `git@github.com:paolo/bot-immobiliare.git`):

```bash
cd /Users/macbook/Desktop/Code/Paolo_Vailati/BOT_IMMOBILIARE

git init
git branch -m main
git add .
git status            # ⚠️ verifica che .env NON sia nella lista
git commit -m "Initial commit: scraper + DB + outreach + dashboard"
git remote add origin <URL>
git push -u origin main
```

> ⚠️ **Importante**: controlla il `git status` prima del commit. Il file `.env`
> deve essere ignorato. Se per errore appare nella lista, il `.gitignore` non
> sta funzionando — fermati e contattami.

---

## Step 3 — GitHub Actions: secrets per il cron

Nel repo GitHub appena creato:

1. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. Aggiungi questi 5 secret (uno alla volta):

| Nome | Valore |
|---|---|
| `SUPABASE_URL` | dal `.env` locale |
| `SUPABASE_SERVICE_KEY` | dal `.env` locale (`sb_secret_…`) |
| `SUPABASE_ANON_KEY` | dal `.env` locale (`sb_publishable_…`) |
| `TELEGRAM_BOT_TOKEN` | dal `.env` locale |
| `TELEGRAM_CHAT_ID` | dal `.env` locale |

3. **Settings** → **Actions** → **General** → conferma che "Allow all actions" sia attivo
4. **Actions** tab → **scrape-cycle** workflow → **Run workflow** (manualmente per test)
5. Dovresti vedere il run a verde dopo ~2-3 minuti

Da quel momento, il cron gira ogni 3h da solo.

---

## Step 4 — Streamlit Community Cloud

1. Vai su [share.streamlit.io](https://share.streamlit.io) → **Sign in with GitHub**
2. **New app**
3. Compila:
   - **Repository**: `<tuo-user>/bot-immobiliare`
   - **Branch**: `main`
   - **Main file path**: `dashboard/app.py`
   - **App URL (opzionale)**: `paolo-bot-immobiliare` → diventa `https://paolo-bot-immobiliare.streamlit.app`
4. **Advanced settings** → **Python version**: `3.12`
5. **Secrets**: clicca, e incolla questo (con i tuoi valori):

```toml
SUPABASE_URL = "https://<project-id>.supabase.co"        # dal .env
SUPABASE_SERVICE_KEY = "sb_secret_..."                    # dal .env
DASHBOARD_PASSWORD = "scegli-una-password-forte"
```

> ⚠️ **Imposta `DASHBOARD_PASSWORD`**. Senza, la dashboard è pubblicamente
> accessibile e chiunque conosca l'URL vede tutti i numeri raccolti.
> Per cambiarla, basta editare il valore in Secrets → l'app si riavvia.

6. **Deploy** → aspetta ~2-3 min
7. Visita l'URL e logga con la password che hai impostato

---

## Step 5 — Domain (opzionale)

Streamlit Cloud di base dà `nome-app.streamlit.app`. Per un dominio custom serve il piano Streamlit Teams (a pagamento). In alternativa:
- **Cloudflare Tunnel** dal tuo dominio → URL streamlit (gratis)
- **Vercel/Netlify redirect** (gratis ma è solo redirect)

Se ti interessa, dimmi quale e ti guido.

---

## Operazioni quotidiane

### Aggiornare il codice
```bash
git add .
git commit -m "msg"
git push
```
Streamlit Cloud auto-redeploya in ~30s. GitHub Actions usa il `main` aggiornato al prossimo cron.

### Forzare un re-scrape manuale
Vai su **GitHub → Actions → scrape-cycle → Run workflow**. Risultato in DB + dashboard entro 3 minuti.

### Vedere i log
- **Cron**: GitHub → Actions → scegli un run
- **Dashboard**: Streamlit Cloud → manage → logs

### Cambiare password dashboard
Streamlit Cloud → app → Settings → Secrets → modifica `DASHBOARD_PASSWORD`. Auto-reload.
