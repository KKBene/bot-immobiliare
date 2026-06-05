/**
 * Apps Script Web App per il foglio "Bot Affitti".
 *
 * SETUP (3 minuti):
 *   1. Apri il foglio https://docs.google.com/spreadsheets/d/1gyQB5ftUTxoTeyzIVFTfeNMxN8ROmdG8BU0Wi5PgLhc/
 *   2. Menu Estensioni → Apps Script
 *   3. Cancella il codice di default e incolla questo file intero
 *   4. Salva (icona dischetto)
 *   5. Click "Esegui" (▶︎) sulla funzione doPost — autorizza permessi
 *   6. Click "Deploy" (in alto a destra) → "New deployment"
 *      - Tipo: "Web app"
 *      - Description: "BOT_IMMOBILIARE webhook"
 *      - Execute as: "Me (la tua email)"
 *      - Who has access: "Anyone"  ← IMPORTANTE
 *      - Deploy
 *   7. Copia la URL del Web App (es. https://script.google.com/macros/s/AKfy.../exec)
 *   8. Aggiungila a:
 *      - .env locale: GOOGLE_SHEETS_WEBHOOK_URL=...
 *      - GitHub secrets: GOOGLE_SHEETS_WEBHOOK_URL=...
 *
 * Comportamento:
 *   - Riceve POST JSON { columns: [...], rows: [[...], ...] }
 *   - Foglio "Privati": crea se non esiste con header
 *   - Per ogni riga IN INPUT:
 *       * Se URL esiste già nel foglio → UPDATE delle altre colonne
 *         PRESERVANDO la colonna "Contattato"
 *       * Se URL nuovo → APPEND con Contattato = "No"
 *   - Risposta: JSON { added, updated, skipped }
 */

const TAB_NAME = 'Privati';
const CONTATTATO_COL_NAME = 'Contattato';
const URL_COL_NAME = 'URL';

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const columns = payload.columns;
    const rows = payload.rows || [];
    if (!columns || !Array.isArray(rows)) {
      return jsonResponse({ error: 'payload must have {columns, rows}' });
    }

    const sheet = getOrCreateSheet(columns);
    const result = upsertRows(sheet, columns, rows);
    return jsonResponse(result);
  } catch (err) {
    return jsonResponse({ error: String(err) });
  }
}

function doGet(e) {
  return jsonResponse({
    ok: true,
    message: 'BOT_IMMOBILIARE webhook is alive. Use POST to sync rows.',
  });
}

function getOrCreateSheet(columns) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(TAB_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(TAB_NAME);
    sheet.appendRow(columns);
    const headerRange = sheet.getRange(1, 1, 1, columns.length);
    headerRange.setFontWeight('bold').setBackground('#E8F5E9');
    sheet.setFrozenRows(1);
  } else {
    // Verifica header (case-insensitive)
    const firstRow = sheet.getRange(1, 1, 1, columns.length).getValues()[0];
    const headerMissing = firstRow.every(c => !c);
    if (headerMissing) {
      sheet.getRange(1, 1, 1, columns.length).setValues([columns]);
    }
  }
  return sheet;
}

function upsertRows(sheet, columns, rows) {
  const urlColIdx = columns.indexOf(URL_COL_NAME);
  const contattatoColIdx = columns.indexOf(CONTATTATO_COL_NAME);
  if (urlColIdx < 0 || contattatoColIdx < 0) {
    return { error: 'Missing URL or Contattato column' };
  }

  const lastRow = sheet.getLastRow();
  let existing = [];
  if (lastRow >= 2) {
    existing = sheet.getRange(2, 1, lastRow - 1, columns.length).getValues();
  }
  const urlToRow = new Map(); // url → row number (1-indexed)
  existing.forEach((row, idx) => {
    const url = row[urlColIdx];
    if (url) urlToRow.set(String(url), idx + 2);
  });

  let added = 0, updated = 0, skipped = 0;
  const newRows = [];

  rows.forEach(row => {
    const url = row[urlColIdx];
    if (!url) { skipped++; return; }

    const existingRowNum = urlToRow.get(String(url));
    if (existingRowNum) {
      // UPDATE: tutte le colonne TRANNE Contattato
      const updateRow = row.slice();
      const existingRow = existing[existingRowNum - 2];
      updateRow[contattatoColIdx] = existingRow[contattatoColIdx]; // preserve
      sheet.getRange(existingRowNum, 1, 1, columns.length).setValues([updateRow]);
      updated++;
    } else {
      // APPEND: Contattato default "No"
      const newRow = row.slice();
      if (!newRow[contattatoColIdx]) newRow[contattatoColIdx] = 'No';
      newRows.push(newRow);
      added++;
    }
  });

  if (newRows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, newRows.length, columns.length)
         .setValues(newRows);
  }

  return { added: added, updated: updated, skipped: skipped };
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
