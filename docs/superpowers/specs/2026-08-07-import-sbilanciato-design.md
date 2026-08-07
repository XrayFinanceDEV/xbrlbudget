# Import sbilanciato + chiusura dello sbilancio in Rettifiche

Data: 2026-08-07
Stato: approvato

## Problema

`docs/examples/budget_664_31-05-26 facchinetti.pdf` ha fallito l'import per l'utente. Il
tracking degli upload (`uploaded_files` id=3) registra:

```
PDFImportError: Il bilancio non quadra oppure il documento non contiene dettaglio
sufficiente per ricostruire Attivo, Passivo e Patrimonio netto.
```

Lo stesso file, stesso codice, importa correttamente: 5 esecuzioni su 5 riuscite
(4 via `tests/_import_probe.py`, 1 via `POST /import/pdf?...&period_months=5`), sempre con
`attivo=3.901.425,60`, `sbilancio=0,00`, `sp13=154.335,67`.

### Causa radice

Il file è rotta **B** (`macro_subcategory = "B3/XBRL esteso AGO"`): estrazione IV-CEE via
Claude Haiku, quindi **non deterministica**. Il log dei tentativi mostra la somma
`sp11..sp18` prodotta dall'LLM scostarsi dal `totale_passivo` dichiarato di
40,00 / 224,98 / 727,00 / 107.000,00 € a seconda del tentativo.
`pdf_mapper.validate_balance` tollera **1,00 €** (`pdf_mapper.py:174`), quindi quando tutti i
retry escono fuori tolleranza si arriva a `pdf_importer.py:1103` e l'import fallisce del tutto.

Non è un bug deterministico da correggere in un punto: è varianza del modello su un
documento al limite. La conseguenza per l'utente è però totale — perde l'intero import.

### Causa radice secondaria (stesso gate, effetto diverso)

Lo stesso criterio viene applicato all'anno precedente in `pdf_importer.py:1332`
(`fresh_prior_balances = mapper.validate_balance(prior_bs_data) and _prior_q.quadra`): un
anno di raffronto che non quadra viene **scartato**, non salvato. È il motivo per cui l'API
ha risposto `prior_year_imported: false` su questo file (scarto di 40,00 € sul 2025) e per cui
il wizard infrannuale ha poi preteso un caricamento separato dello storico.

## Vincolo scoperto in fase di analisi

**Rettifiche, così com'è, non può chiudere uno scarto Attivo≠Passivo.**

Ogni rettifica passa da `PROPOSAL_RULES` e applica due delta in partita doppia. Una
scrittura in partita doppia sposta i due lati della stessa quantità: lo scarto resta
identico, per costruzione. L'unica cosa che oggi chiude uno scarto è `reconcileSubfields`
(`frontend/app/infrannuale/page.tsx:2821`), che si ferma a **5 €**.

Quindi rilassare il solo gate di backend non basta: l'utente atterrerebbe su una scheda
Rettifiche perennemente `SBILANCIATO`, con
`intra_year_engine._validate_forecast_source` che blocca la proiezione a
`abs(sbilancio) > 0.01` — bloccato, senza via d'uscita.

Il lavoro è quindi doppio: rilassare il gate **e** dare a Rettifiche una registrazione a
partita singola.

## Decisioni

| Domanda | Scelta |
|---|---|
| Quali fallimenti diventano "importa con avviso"? | **Solo i bilanci sbilanciati.** Estrazione vuota, formato non supportato e OCR inaffidabile restano errori duri: non c'è nulla da rettificare. |
| Come chiude l'utente lo scarto? | **Bottone "Chiudi sbilancio" nel banner quadratura**, che apre un dialog e genera UNA rettifica a partita singola, tracciata nel journal. |

Scartata: alzare la soglia dell'auto-plug di `reconcileSubfields`. Nasconderebbe in cassa un
errore di estrazione da 107.000 € senza che l'utente lo veda, contro il principio del
progetto *diagnose, never fabricate*.

## A. Backend — lo sbilancio non blocca il salvataggio

### A1. Punto `validate_balance` (`importers/pdf_importer.py:1032-1107`)

Riordinare il blocco perché le diagnosi irrecuperabili girino per prime e restino errori;
tutto il resto cade in un percorso soft.

Restano `PDFImportError` (in quest'ordine):

1. `is_scanned or _ocr_source` — i totali stessi possono essere letti male dall'OCR.
   Messaggio attuale invariato.
2. `balance_sheet_data.get('totale_attivo', 0) == 0` — estrazione vuota, non c'è nulla da
   rettificare. **Controllo nuovo ed esplicito**: oggi è dentro `validate_balance` check 1 e
   ricade nel messaggio generico.
3. `not is_trial_balance and _is_aggregated_summary(sample_text)` — prima
   `_summary_internal_contradiction(sample_text)` se presente, poi *"Formato non supportato"*.
   Manca lo schema IV-CEE, non la quadratura.

Diventano import-con-avviso (tutto il resto):

- `attivo != passivo` (check 2 di `validate_balance`);
- aggregati che non ricostruiscono i totali dichiarati (check 3 e 4) — **i due casi che hanno
  colpito questo file**;
- *"Il bilancio sorgente non quadra prima dell'importazione: Totale Attivo X != Totale
  Passivo Y"*.

Il messaggio di errore attuale è la migliore diagnosi disponibile e non va perso: diventa il
testo del warning, preceduto da `BILANCIO SBILANCIATO: ` e chiuso da *"Il bilancio è stato
importato così com'è: correggilo in Rettifiche prima di calcolare la proiezione."*

### A2. Punto `check_quadratura` (`importers/pdf_importer.py:1135-1150`)

Resta duro **solo** per `_qd.is_empty`. Sbilancio, mismatch CE↔SP e plug mascherato
(`masked`) diventano warning con lo stesso prefisso. Questo allinea finalmente il codice a
quanto CLAUDE.md già afferma per la rotta C (*"Trial-balance import is never hard-blocked"*),
che oggi non è vero perché `quadra` richiede `not masked`.

Il blocco `except Exception as _qd_err: raise PDFImportError(...)` resta invariato: se il
calcolo della quadratura esplode, non sappiamo cosa stiamo salvando.

### A3. `validation_status`

Terzo valore `"unbalanced"` quando l'identità aritmetica non regge, così la UI distingue
*"dettagli da rivedere"* da *"non quadra"* senza fare string-matching sui warning:

```python
if not arithmetic_balanced:   status = "unbalanced"
elif _forecastable:           status = "verified"
else:                         status = "review_required"
```

`validation_status` è una colonna `String` libera: nessuna migrazione.

`forecastable` **non cambia**: va già a `false` da solo, perché
`semantic_valid = quadra and hierarchy_consistent and plug <= tol`
(`iv_cee_hierarchy.py:538`).

La stessa espressione a tre vie va replicata in `backend/app/api/v1/financial_years.py:511`.
Altrimenti la prima rettifica salvata degrada lo stato a `review_required` pur restando il
bilancio sbilanciato, perdendo il segnale.

### A4. Anno precedente (`importers/pdf_importer.py:1332`)

Regola nuova, che sostituisce lo scarto incondizionato:

| Fresh prior | Esiste già un record | Azione |
|---|---|---|
| quadra | sì | sostituisci (comportamento attuale) |
| quadra | no | importa (comportamento attuale) |
| **sbilanciato** | **sì** | **conserva l'esistente** — non degradare un record buono |
| **sbilanciato** | **no** | **importa sbilanciato** con warning e `validation_status="unbalanced"` |
| vuoto (`_prior_q.is_empty` o `not prior_has_data`) | — | non importare (comportamento attuale) |

Il warning `ANNO PRECEDENTE NON IMPORTATO [...]` resta solo per i casi in cui davvero non si
importa; nel caso nuovo diventa `ANNO PRECEDENTE SBILANCIATO [...]`.

### A5. Reti di sicurezza a valle — nessuna modifica

`intra_year_engine._validate_forecast_source` blocca già su `abs(result.sbilancio) > 0.01`
(`calculations/intra_year_engine.py:353`): la proiezione resta rifiutata finché l'utente non
corregge. `assumptions_service.bulk_upsert_assumptions` restituisce HTTP 200 con
`forecast_generated: false` — i chiamanti lo controllano già.

## B. Frontend — "Chiudi sbilancio" in Rettifiche

Il banner quadratura esiste già e mostra già `SBILANCIATO`
(`frontend/app/infrannuale/page.tsx:1936-1952`).

- Quando `!isBalanced`, il banner espone un `Button size="sm" variant="outline"`
  **"Chiudi sbilancio"**.
- Apre un dialog con:
  - **Importo**: precompilato a `totalAttivo − totalPassivo`, **non editabile**. Lo scarto è
    quello, non è un'opinione.
  - **Imputa a**: `Select` con i bucket "altri" che `reconcileSubfields` usa già come plug, così
    `recalcAggregates` ricalcola correttamente il padre —
    `sp09_disponibilita_liquide`, `sp06g_crediti_altri_breve`, `sp05e_acconti`,
    `sp16g_altri_debiti_breve`, `sp17g_altri_debiti_lungo`, `sp12e_altre_riserve`.
  - **Default per segno**: scarto positivo (l'attivo eccede) → `sp09_disponibilita_liquide`;
    scarto negativo → `sp16g_altri_debiti_breve`.
  - Nota esplicita: *"Registrazione a partita singola: chiude lo scarto di estrazione, non è
    una scrittura contabile."*
- Conferma → **una** `RettificaEntry` a partita singola: entra nel journal, conta sul cap di
  20 (`RETTIFICHE_MAX`), è cancellabile come le altre.
- Il pannello journal la rende con `— (correzione di quadratura)` al posto della riga di
  contropartita.

### Schema

`backend/app/schemas/adjustments.py`:

```python
counterpart_field: Optional[str] = None
counterpart_label: Optional[str] = None
counterpart_delta: float = 0.0
```

Retro-compatibile in lettura: i log esistenti hanno tutti e tre i campi valorizzati.

### Salvataggio — nessuna modifica al backend

`PUT /adjustments` (`financial_years.py:437-454`) rifiuta solo i salvataggi che
**peggiorano** lo sbilancio, e consente esplicitamente di lavorare su un record già
sbilanciato all'import. Una chiusura che riduce lo scarto passa già così com'è.

## C. Frontend — rendere visibile l'import sbilanciato

`handleImport` in `frontend/app/infrannuale/page.tsx:2992` ignora oggi `result.warnings` e
`result.validation_status` e mostra un `toast.success` liscio. Su
`validation_status === "unbalanced"` deve mostrare un `toast.warning` con la ragione e il
rimando a Rettifiche. Stesso trattamento nella pagina `/import`.

## D. Test

Nuovo `tests/test_unbalanced_import.py`:

- un BS con scarto di 40 € si salva, con `forecastable is False`,
  `validation_status == "unbalanced"` e il warning `BILANCIO SBILANCIATO:` presente;
- `totale_attivo == 0` continua ad alzare `PDFImportError`;
- un riepilogo aggregato continua ad alzare `PDFImportError` con *"Formato non supportato"*;
- anno precedente sbilanciato **senza** record esistente → importato con
  `validation_status="unbalanced"`;
- anno precedente sbilanciato **con** record esistente → l'esistente è conservato intatto.

Test unitario frontend per la voce di journal a partita singola (delta singolo applicato,
aggregati ricalcolati, cancellazione che lo inverte).

### Baseline di regressione — nota onesta

`tests/fixtures/import_baseline.json` contiene 19 entry, tutte in errore, e **11 di esse
registrano un bug del probe già corretto** (`AttributeError: 'str' object has no attribute
'close'`): la fixture è stale, indipendentemente da questa modifica.

Delle rimanenti, **4 passeranno da errore a import-con-avviso** per effetto di questa
modifica: `budget_365`, `budget_342` (*"Documento non importabile automaticamente: i totali
Attivo e Passivo..."*) e `budget_405`, `budget_367` (*"Importazione non salvata: il bilancio
estratto non supera i controlli contabili"*).

Il corpus `Test/` non è presente in locale e `tests/test_import_baseline.py` skippa i file
assenti, quindi nulla si romperà. La fixture va però rigenerata con
`scripts/refresh_import_baseline.py` quando il corpus è disponibile. Segnalato, non dato per
fatto.

## Cosa questa modifica NON fa

Non rende deterministico l'import di questo file. La causa vera resta la varianza di Haiku
sulla rotta B. Con questa modifica il tentativo sfortunato non fallisce più, ma consegna
all'utente un bilancio con un buco da chiudere a mano (40 € nel caso benigno, 107.000 € nel
caso peggiore osservato nei retry). Ridurre la varianza a monte è un lavoro separato.
