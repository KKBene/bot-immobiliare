# 📊 Sync Google Sheet

Il bot scrive automaticamente i nuovi annunci PRIVATI con telefono nel foglio Google del cliente.

**Foglio**: [Bot Affitti](https://docs.google.com/spreadsheets/d/1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc/edit)

## Cosa fa il sync

A ogni ciclo (3h) il bot:
1. Carica dal DB tutti i privati attivi con telefono
2. Confronta con il foglio (chiave = `URL`)
3. **APPEND** delle nuove righe (con `Contattato = "No"`)
4. **UPDATE** delle righe esistenti (preserva la colonna `Contattato`)

Colonne del foglio (tab `Privati`):

| Col | Nome | Riempita da |
|-----|------|-------------|
| A | URL | bot |
| B | Portale | bot |
| C | Inserzionista | bot |
| D | Telefono | bot |
| E | Zona | bot |
| F | Prezzo €/mese | bot |
| G | Spese €/mese | bot |
| H | Totale €/mese | bot |
| I | Mq | bot |
| J | Locali | bot |
| K | Indirizzo | bot |
| L | Visto il | bot |
| M | **Contattato** | **manuale (Paolo)** |

> ⚠️ La colonna **Contattato** è preservata in update: Paolo può scrivere "Sì"
> liberamente, il bot non la sovrascrive mai.

---

## 🥇 Setup Apps Script Webhook (3 minuti — più semplice)

Niente Google Cloud, niente Service Account. **Funziona con foglio "anyone can edit".**

1. Apri [il foglio](https://docs.google.com/spreadsheets/d/1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc/edit)
2. Menu **Estensioni → Apps Script**
3. Cancella il codice di default e incolla tutto il contenuto di [`docs/apps_script_webhook.js`](apps_script_webhook.js)
4. Salva (Ctrl+S / icona dischetto)
5. **Esegui** (▶︎) la funzione `doPost` una volta — Google chiede di autorizzare i permessi del tuo account, conferma
6. **Deploy** (in alto a destra) → **New deployment**:
   - **Tipo**: Web app
   - **Execute as**: Me (tua email)
   - **Who has access**: **Anyone**
   - Click Deploy
7. Si apre un popup con **Web app URL** tipo `https://script.google.com/macros/s/AKfy.../exec` → copiala
8. Setta i secret:
   - **`.env` locale**: `GOOGLE_SHEETS_WEBHOOK_URL=https://script.google.com/macros/s/AKfy.../exec`
   - **GitHub secrets**: `GOOGLE_SHEETS_WEBHOOK_URL` con lo stesso valore

Fatto. Il bot ora scrive nel foglio a ogni cycle.

## 🥈 Setup Service Account (alternativa più strutturata)

### 1. Crea il progetto + service account su Google Cloud

1. Vai su [console.cloud.google.com](https://console.cloud.google.com/)
2. **New Project** → nome: `bot-immobiliare` (o quello che vuoi)
3. Menu sinistra → **APIs & Services** → **Library**
4. Cerca e abilita:
   - ✅ **Google Sheets API**
   - ✅ **Google Drive API** (serve per opening del foglio)
5. **APIs & Services** → **Credentials** → **Create credentials** → **Service account**
6. Nome: `bot-immobiliare-sa` → **Create** → ruolo `Editor` → **Done**
7. Click sul service account appena creato → tab **Keys** → **Add Key** → **JSON**
8. Si scarica un file `bot-immobiliare-xxx.json` — è la **credential**

### 2. Condividi il foglio con il service account

1. Apri il JSON scaricato, copia il valore di `"client_email"` (è una mail tipo `bot-immobiliare-sa@bot-immobiliare.iam.gserviceaccount.com`)
2. Apri [il foglio](https://docs.google.com/spreadsheets/d/1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc/edit)
3. **Condividi** in alto a destra
4. Incolla l'email del service account, ruolo **Editor**, **Invia**

### 3. Setta i secret

**Locale (`.env`)**:
```
GOOGLE_SHEET_ID=1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc
GOOGLE_SHEETS_CREDENTIALS_FILE=/path/al/file/scaricato.json
```

**GitHub Actions** ([secrets/actions](https://github.com/KKBene/bot-immobiliare/settings/secrets/actions)):
- `GOOGLE_SHEET_ID` = `1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc`
- `GOOGLE_SHEETS_CREDENTIALS_JSON` = il **contenuto** del JSON in una sola riga
  (puoi copiarlo da cat <file>.json | tr -d '\n')

### 4. Test

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from src.db import client
from src.sheets import sync_private_listings, is_enabled
print('configured:', is_enabled())
if is_enabled():
    print(sync_private_listings(client()))
"
```

Dovrebbe stampare `added: N, updated: 0, skipped: 0` la prima volta.

## Hook pipeline

Il sync è chiamato automaticamente alla fine di ogni `run_cycle()` (vedi
`src/pipeline.py`). Se Google Sheet non è configurato, è no-op silenzioso.
