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
// Colonne MODIFICATE A MANO da Paolo: non sovrascriverle mai in update.
// Il bot le scrive solo per le righe NUOVE (primo append).
const USER_EDITED_COLS = ['Contattato'];
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
    return sheet;
  }
  // Esiste già: verifico se l'header corrisponde esattamente a `columns`.
  const lastCol = sheet.getLastColumn();
  const currentHeader = lastCol > 0
    ? sheet.getRange(1, 1, 1, lastCol).getValues()[0]
    : [];

  if (currentHeader.length === 0 || currentHeader.every(c => !c)) {
    // Header vuoto → riempi
    sheet.getRange(1, 1, 1, columns.length).setValues([columns]);
    sheet.getRange(1, 1, 1, columns.length)
         .setFontWeight('bold').setBackground('#E8F5E9');
    sheet.setFrozenRows(1);
    return sheet;
  }

  // Se l'header esistente è DIVERSO dal nuovo schema (più, meno o ordine
  // differente) → migrate. PRESERVA i dati esistenti grazie al match by name.
  if (!headersMatch(currentHeader, columns)) {
    migrateHeader(sheet, currentHeader, columns);
  }
  return sheet;
}

function headersMatch(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (String(a[i]).trim().toLowerCase() !== String(b[i]).trim().toLowerCase()) {
      return false;
    }
  }
  return true;
}

/**
 * Riallinea l'header al nuovo schema preservando i dati esistenti
 * (match by name, case-insensitive). Gestisce ESTENSIONE, RIDUZIONE
 * e RIORDINO senza mai manipolare il numero di colonne fisico del
 * foglio (più stabile, no edge case insertColumns/deleteColumns).
 *
 * Le colonne presenti in vecchio ma NON in nuovo vengono SCARTATE.
 * Le colonne presenti in nuovo ma NON in vecchio sono lasciate vuote.
 *
 * Le eventuali colonne fisiche in eccesso vengono solo svuotate
 * (clearContent), così il foglio rimane stabile e non perde
 * formattazione/frozenRows.
 */
function migrateHeader(sheet, currentHeader, newColumns) {
  const lastRow = sheet.getLastRow();
  const numDataRows = Math.max(0, lastRow - 1);
  const oldColCount = currentHeader.length;

  // mapping vecchio → posizione nel nuovo (-1 se non c'è = colonna scartata)
  const oldIdxToNewIdx = {};
  currentHeader.forEach(function(h, oldIdx) {
    var matchIdx = -1;
    for (var i = 0; i < newColumns.length; i++) {
      if (String(newColumns[i]).toLowerCase().trim() === String(h).toLowerCase().trim()) {
        matchIdx = i; break;
      }
    }
    if (matchIdx >= 0) oldIdxToNewIdx[oldIdx] = matchIdx;
  });

  // Carica i dati esistenti
  var oldData = [];
  if (numDataRows > 0 && oldColCount > 0) {
    oldData = sheet.getRange(2, 1, numDataRows, oldColCount).getValues();
  }

  // Costruisco i nuovi dati riallineati
  var newData = oldData.map(function(oldRow) {
    var newRow = new Array(newColumns.length).fill('');
    for (var oldIdx in oldIdxToNewIdx) {
      newRow[oldIdxToNewIdx[oldIdx]] = oldRow[Number(oldIdx)];
    }
    return newRow;
  });

  // STRATEGIA SAFE: clearContents (no clear formatting o struttura)
  // Poi riscrivo header + dati. Le colonne fisiche in eccesso (se ce ne
  // sono) restano vuote, non vengono cancellate fisicamente. È OK.
  sheet.clearContents();

  // Header
  sheet.getRange(1, 1, 1, newColumns.length).setValues([newColumns]);
  sheet.getRange(1, 1, 1, newColumns.length)
       .setFontWeight('bold').setBackground('#E8F5E9');
  sheet.setFrozenRows(1);

  // Dati
  if (newData.length > 0) {
    sheet.getRange(2, 1, newData.length, newColumns.length).setValues(newData);
  }
}

function upsertRows(sheet, columns, rows) {
  const urlColIdx = columns.indexOf(URL_COL_NAME);
  if (urlColIdx < 0) {
    return { error: 'Missing URL column' };
  }
  // Indici delle colonne che NON vanno sovrascritte in update
  const protectedIdx = USER_EDITED_COLS
    .map(name => columns.indexOf(name))
    .filter(i => i >= 0);

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
  const contattatoIdx = columns.indexOf('Contattato');
  const statusIdx = columns.indexOf('Status');

  rows.forEach(row => {
    const url = row[urlColIdx];
    if (!url) { skipped++; return; }

    const existingRowNum = urlToRow.get(String(url));
    if (existingRowNum) {
      // UPDATE: preserva i valori esistenti delle colonne user-edited
      const updateRow = row.slice();
      const existingRow = existing[existingRowNum - 2];
      protectedIdx.forEach(i => {
        updateRow[i] = existingRow[i]; // preserva quello che l'utente ha scritto
      });
      sheet.getRange(existingRowNum, 1, 1, columns.length).setValues([updateRow]);
      updated++;
    } else {
      // APPEND: default "No" per Contattato; lascia Status dal payload
      const newRow = row.slice();
      if (contattatoIdx >= 0 && !newRow[contattatoIdx]) newRow[contattatoIdx] = 'No';
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
