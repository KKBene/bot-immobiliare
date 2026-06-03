# 🏠 Self-hosted GitHub Actions Runner

> Come far girare il cron del bot dal **tuo Mac** (IP residenziale italiano)
> invece che dal runner cloud di GitHub (IP cloud blacklistato da DataDome
> per Immobiliare).

## Perché serve

**Diagnosi 2026-06-03**: il runner cloud di GitHub Actions ha IP in
blacklist DataDome → Immobiliare ritorna 403 al cycle remoto. Idealista
continua a funzionare. Risultato: 0 nuovi annunci Immobiliare per 24h+.

**Soluzione gratuita**: GitHub permette runner "self-hosted" su qualsiasi
macchina. Il tuo Mac di casa ha un IP residenziale italiano (TIM/Vodafone
/Wind/etc.) che **DataDome non blocca** perché è "umano".

| | Cloud runner (ora) | Self-hosted runner (proposto) |
|---|---|---|
| Costo | 0 | 0 |
| IP | Azure/AWS US/EU (blacklist) | TIM/Vodafone IT (clean) |
| Mac sempre acceso? | non richiesto | **richiesto** (anche con coperchio chiuso) |
| Setup | nulla | 5 minuti |
| Manutenzione | nulla | minima (eventuali aggiornamenti annuali) |

## Setup (5 minuti)

### 1. Verifica che il Mac resti sveglio

Apri "Risparmio Energia" e configura:
- ☑️ "Impedisci al Mac di andare in stop quando lo schermo è spento"
- ☑️ "Avvia automaticamente dopo un'interruzione di corrente"
- ☑️ Se è un MacBook con coperchio chiuso, collega un monitor esterno
  oppure usa Amphetamine / Caffeine per tenerlo sveglio

Alternativa: aggiungi nelle Impostazioni Sistema → Risparmio Energia:
```bash
sudo pmset -a sleep 0
sudo pmset -a disksleep 0
```

### 2. Crea il runner

1. Vai su [github.com/KKBene/bot-immobiliare/settings/actions/runners](https://github.com/KKBene/bot-immobiliare/settings/actions/runners)
2. **New self-hosted runner** → **macOS** → **ARM64** (per M1/M2/M3/M4) o **x64** (per Intel Mac)
3. GitHub mostra i comandi: copiali

Esempio (Apple Silicon):
```bash
mkdir -p ~/Desktop/Code/Paolo_Vailati/actions-runner && cd $_
curl -o actions-runner-osx-arm64.tar.gz -L \
  https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-osx-arm64-X.Y.Z.tar.gz
tar xzf ./actions-runner-osx-arm64.tar.gz

# Token mostrato da GitHub: valido per 1h, è un secret one-shot
./config.sh --url https://github.com/KKBene/bot-immobiliare --token TOKEN_QUI \
            --name "macbook-paolo" --labels "macbook,it-residential" \
            --runnergroup default --work _work --unattended

# Test interattivo
./run.sh
```

Apri Settings → Runners su GitHub: dovresti vedere `macbook-paolo` come
**Idle**.

### 3. Installa come servizio (sempre attivo)

```bash
cd ~/Desktop/Code/Paolo_Vailati/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

Lo script crea un LaunchDaemon che riavvia il runner anche dopo reboot.
Verifica con: `sudo ./svc.sh status` (deve dire "running").

### 4. Cambia il workflow per usarlo

In `.github/workflows/scrape-cycle.yml`:

```yaml
jobs:
  cycle:
    # PRIMA: runs-on: ubuntu-latest
    runs-on: [self-hosted, macbook]
```

Push e fatto. Al prossimo cron (ogni 3h) il job partirà sul Mac.

### 5. Verifica

- Su GitHub Actions, fai partire il workflow manualmente: "Run workflow"
- Sul Mac, monitora il runner: `tail -f ~/actions-runner/_diag/Runner_*.log`
- Verifica in dashboard ⚙️ Sistema che **immobiliare** abbia nuovi `last_seen_at`

## Strategia ibrida (consigliata)

Lascia **entrambi**:
- **Cloud runner** (`ubuntu-latest`) per il cron principale: continua a fare Idealista
- **Self-hosted runner** chiamato esplicitamente solo per Immobiliare in cycle separato

Workflow split:
```yaml
jobs:
  idealista:
    runs-on: ubuntu-latest
    steps: [...]
  immobiliare:
    runs-on: [self-hosted, macbook]
    steps: [...]
```

Vantaggio: se il Mac va offline temporaneamente, almeno Idealista non si blocca.

## Alternative se non hai un Mac sempre acceso

| Opzione | Costo | Pro | Contro |
|---|---|---|---|
| **Hetzner CX11** + tunneling WireGuard verso IP italiano | 4€/mese + 0€ tunnel | IP dedicato | Setup complesso |
| **Aruba VPS Smart** | 3€/mese | IP italiano | Performance moderata |
| **ScrapingBee free tier** (proxy DataDome-aware) | 0 (1000 req/mese) | Zero setup | Quota stretta: ~30 giorni di sole-Immobiliare |
| **OPSC Cron job** + endpoint hostato su Render free | 0 | Tutto cloud | Render addormenta dopo 15min, IP cloud comunque |
| **Mullvad VPN container** | 5€/mese (no free) | IP residenziale rotation | Workflow Actions complicato |

## Sicurezza self-hosted

⚠️ **Mai usare self-hosted runner con repo PUBBLICO** — chiunque potrebbe
proporre un workflow malevolo via PR. Il tuo repo è `private` ✅, sei al sicuro.

Best practice:
- Non installare il runner come root
- Usa l'account utente normale del Mac
- Non condividere il runner con altri repo non fidati

## Troubleshooting

| Sintomo | Fix |
|---|---|
| "macbook-paolo offline" su GitHub | `sudo ./svc.sh start` |
| Workflow resta in "Queued" | Verifica labels: il workflow `runs-on: [self-hosted, macbook]` deve matchare quelle del runner |
| Workflow fallisce con "python3 not found" | Aggiungi step `actions/setup-python@v5` come nel workflow attuale (lavora anche su macOS) |
| DataDome blocca anche da Mac | Sei stato troppo aggressivo — aumenta jitter, riduci freq cron, riprova in 30min |
