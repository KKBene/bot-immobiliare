#!/bin/bash
# Installa un cron locale via launchd che esegue il cycle ogni 3 ore.
#
# Vantaggio rispetto a GitHub Actions:
#   - IP residenziale italiano (TIM/Vodafone/Wind) → DataDome non blocca
#   - Costo zero (Mac già acceso per uso normale)
#
# Vantaggio rispetto al self-hosted GitHub runner:
#   - Setup più semplice (1 file plist, no token, no service GitHub)
#   - Niente configurazione GitHub
#
# Requisiti:
#   - Mac di Paolo accesso (anche con coperchio chiuso se setup come sotto)
#   - .env configurato e funzionante (./scripts/run_cycle.py funziona a mano)
#
# Uso:
#   bash scripts/install_local_cron.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="/Users/macbook/Desktop/Code/.venv/bin/python3"
LABEL="com.paolovailati.bot_immobiliare.cycle"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

# Genera plist
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${REPO_DIR}/scripts/run_cycle.py</string>
        <string>--max-pages</string>
        <string>15</string>
        <string>--stale-hours</string>
        <string>48</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>

    <!-- Ogni 3 ore (StartCalendarInterval con Hour ripetuto) -->
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>17</integer></dict>
    </array>

    <!-- Output e errori a file (rotation manuale, vedi logs/) -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/cron.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/cron.err.log</string>

    <!-- Riavvia automaticamente se crasha -->
    <key>RunAtLoad</key>
    <false/>

    <!-- Eredita variabili ambiente standard del Mac (PATH, ecc.)
         NB: .env viene caricato dal Python via python-dotenv -->
</dict>
</plist>
EOF

echo "✓ Plist creato in: $PLIST_PATH"

# Disattiva eventuale versione precedente
if launchctl list "$LABEL" >/dev/null 2>&1; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "✓ Versione precedente disattivata"
fi

# Carica il job
launchctl load "$PLIST_PATH"
echo "✓ launchd job caricato"
echo ""
echo "=== Verifica ==="
launchctl list | grep "$LABEL" || echo "  (non in lista — controlla i log: $LOG_DIR)"
echo ""
echo "Il bot girerà ogni 3 ore alle 00:17, 03:17, 06:17, ... (UTC del Mac)"
echo ""
echo "Per testare SUBITO manualmente:"
echo "  launchctl start $LABEL"
echo ""
echo "Per vedere i log:"
echo "  tail -f $LOG_DIR/cron.out.log"
echo "  tail -f $LOG_DIR/cron.err.log"
echo ""
echo "Per disinstallare:"
echo "  launchctl unload $PLIST_PATH"
echo "  rm $PLIST_PATH"
echo ""
echo "⚠️  Verifica che il Mac NON vada in stop al di sotto:"
echo "  Sistema → Risparmio energia → 'impedisci stop quando display spento' ON"
echo "  oppure: sudo pmset -a sleep 0  (anche più aggressivo)"
