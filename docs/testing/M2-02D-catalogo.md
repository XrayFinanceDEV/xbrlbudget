# M2-02D — catalogo fisso del dossier v4

**Decisione del proprietario, 2026-09-17 sera** (`.superpowers/sdd/2026-09-17-dossier-v4/m2-02d.md`):
il PDF non è più la proiezione generica dell'intero modello v2 — quello che stampava
`editorial_inventory.py` — ma un **catalogo fisso di pagine**, una per numero di pagina della v4
(`report-finale-anteprima-v4.pdf`, 33 pagine). Ciò che la v4 non mostra esce dal PDF (resta sul
web). Questa pagina spiega come aggiungere una pagina al catalogo; per i vincoli del proprietario
(colonne, rettifiche al minimo) e il catalogo completo pagina per pagina vedi
`m2-02d.md` nella stessa cartella SDD.

## Struttura

```
backend/app/renderers/typst/dossier_catalog/
  __init__.py     — registro dei gruppi (GROUPS), build_inventory(), expected_content_inventory(),
                     chart_declarations() — API pubblica, importata da editorial_plan.py e
                     editorial_notes_service.py
  shared.py       — helper di basso livello (formattazione, row/table/kpi, chart_view, select_periods,
                     appendix_table_rows, chunk...): riusabili da qualunque gruppo
  apertura.py     — copertina (v4 pag. 1), sintesi (pag. 2)
  dati.py         — fonti, rettifiche, chiusura, indicatori infrannuali (pag. 3-6) — REGISTRO VUOTO
  piano.py        — ipotesi, CE previsionale, SP previsionale, flussi (pag. 7-10) — solo «ce» implementata
  indicatori.py   — indicatori, liquidità, redditività, solidità, circolante, composizione,
                     break-even, diagnostica (pag. 11-18) — REGISTRO VUOTO
  allegati.py     — indice, A/B/C (prospetti completi), D/E/F/G, metodologia (pag. 19-33) —
                     indice e A/B/C implementati

backend/app/renderers/typst/templates/dossier-base/
  editorial.typ         — dispatcher: legge editorial-inventory.json, per ogni pagina fa
                           pagebreak() + intestazione + un blocco per item, dispatch per kind
  pagine/comuni.typ      — componenti condivisi (tabella, grafico, testo, nota, indice, intestazione
                           di pagina) — quello che OGGI serve, dimostrato da una pagina reale
  pagine/{apertura,dati,piano,indicatori,allegati}.typ — un file per gruppo, oggi per lo più
                           commenti/TODO: un gruppo scrive qui solo ciò che comuni.typ non copre
                           ancora (dumbbell, stacked, panel-grid — vedi indicatori.typ)
```

**Un `PageSpec` è un dict**, non una classe: `{"id", "title", "family", "subtitle", "kpis", "items"}`.
`id` è l'identificativo di catalogo (`"sintesi"`, `"ce"`, `"allegato-A-1"`, ...), `family` è
l'occhiello (`"Sintesi"`, `"Piano e risultati"`, `"Allegati"` — stampato in maiuscolo da Typst),
`title` è il titolo neutro di pagina, `subtitle` la nota di metodo (v4: sottotitolo statico, mai un
numero), `kpis` una lista di dict KPI (vedi sotto), `items` una lista di **blocchi** (`kind`:
`"table"` · `"chart"` · `"text"` · `"note"` · `"index"` · `"cover"`, quest'ultimo solo in copertina).

**Un gruppo con registro vuoto** espone `def build(report): return []` — nessuna pagina compare,
l'indice non la elenca, nessun riquadro vuoto. Non serve altro: `__init__.py` concatena
`group.build(report)` per ogni gruppo di `GROUPS`, in ordine fisso.

## Perché ogni pagina è ESATTAMENTE una pagina fisica

Il vecchio `editorial_inventory.py` produceva **sezioni**: un gruppo di blocchi che Typst
impaginava con la propria logica (un `pagebreak()` all'inizio della sezione, poi flusso
automatico — vedi «Perché il redesign», sotto). Il catalogo fisso rovescia questo: **ogni voce del
catalogo Python è già esattamente il contenuto che deve stare su UNA pagina fisica**, curato a
mano dal gruppo che la costruisce (KPI + un grafico + una tabella di sintesi, non il prospetto
completo). `editorial.typ` fa un solo `pagebreak()` per voce del catalogo, mai un secondo
pagebreak "debole" a metà pagina — quel trucco esisteva nel vecchio dispatcher proprio perché le
sezioni potevano contenere più di un grafico o testo+grafico, e serviva a impedire che si
sovrapponessero. Con il catalogo fisso quella necessità sparisce per costruzione.

**L'unica eccezione dichiarata** sono gli Allegati A/B/C: un prospetto completo (fino a 86 righe)
non sta su una pagina, quindi `allegati.py` lo **spacca in più voci di catalogo** (`allegato-A-1`,
`allegato-A-2`, ...) usando `shared.chunk()` con `APPENDIX_ROWS_PER_PART = 24` righe a parte — ogni
parte è una voce di catalogo a sé, con la propria intestazione di pagina («ALLEGATI · 05», «ALLEGATI
· 06», ...), esattamente come mostra la v4 (pagine 20-27, «1/2», «2/2», ...). Non è il vecchio
meccanismo di divisione **per colonne** (`value_start`/`part_size`/`#parte:N`, che esisteva perché
l'inventario generico mostrava fino a sette periodi affiancati): il vincolo delle 5 colonne di
valore lo rende inutile per questa fase — se un gruppo futuro (Tabella F/G, `INDICATOR_PART_SIZE`)
avesse di nuovo bisogno di dividere per colonne, lo scrive da sé prendendo `data-table` in
`comuni.typ` a modello (il commento lì lo dice esplicitamente).

## Come si aggiunge una pagina — esempio: la pagina CE (già fatta, `piano.py`)

1. **Guarda la v4.** `pdftotext -f 8 -l 8 -layout report-finale-anteprima-v4.pdf -` (pagina, non
   indice di catalogo) per il testo esatto; `pdftoppm -f 8 -l 8 -r 60 -png ... /tmp/p8` + `Read` sul
   PNG per il layout. Leggi anche `build-dossier-preview.py` (il generatore della v4): la chiamata
   `add('ce', ...)` mostra KPI, grafico e tabella esatti — i NUMERI sono dimostrativi, la
   **struttura** no.
2. **Scegli le fonti nel modello v2**, mai un calcolo nuovo. Per «ce»:
   - KPI: `shared.kpi_forecast`/`shared.kpi_indicator` (valori dell'ultimo anno di piano).
   - Grafico: `shared.indicator_chart(report, id, title, unit, periods, [indicator_ids])` — se il
     grafico è di **importi** (non indicatori), usa `shared.statement_chart(report, statement_id,
     id, title, unit, periods, [(code, etichetta), ...])`, che legge righe di `detailed_statements`.
   - Tabella di sintesi: righe canoniche note (`production_value`, `ebitda`, `net_profit`, ...) lette
     con `shared.statement_row`/`shared.values_for_periods` — MAI il prospetto completo (quello
     sta solo negli Allegati).
   - Periodi: `shared.forecast_periods(statement)` per «solo anni di piano» (CE/SP/Flussi);
     `shared.select_periods(periods)` per «chiusura/storico + anni di piano, max 5» (Allegati,
     pagine con un'ancora storica).
3. **Un valore che il modello non dà si omette**, mai un «n.d.» in colonna KPI: ogni `kpi_*` di
   `shared.py` ritorna `None` quando manca, e i costruttori di pagina filtrano `if kpi is not None`.
   Un grafico senza alcuna serie con un valore **non si costruisce affatto** (`shared.chart_block`
   ritorna `None` se il grafico è `None`): la pagina resta con KPI + tabella, senza un riquadro vuoto.
4. **Componi il dict di pagina** nel file del gruppo (`piano.py::_ce`) e aggiungilo alla lista che
   `build(report)` ritorna, nell'ordine v4.
5. **Verifica il vincolo delle 5 colonne** prima di committare: `len(item["columns"]) - 1 <= 5`
   (c'è un test dedicato, `test_dossier_catalog.py::test_no_table_exceeds_five_value_columns`, e uno
   sul PDF vero, `test_pdf_semantic_dossier.py::test_no_table_exceeds_five_value_columns`).
6. **Lato Typst**: se la pagina usa solo tabella/grafico/testo/nota/indice, **non serve scrivere
   Typst**: `comuni.typ` già dispatcha ogni `kind`. Scrivi nel file del gruppo (`pagine/piano.typ`)
   solo un componente che `comuni.typ` non offre ancora (dumbbell, stacked, panel-grid — vedi la
   nota in `pagine/indicatori.typ` per l'elenco di ciò che manca e a quale pagina v4 serve).
7. **Test**: aggiungi un caso in `tests/test_dossier_catalog.py` (Python puro, veloce: forma del
   dict, colonne, valori esatti) e verifica che i test già esistenti su compilazione reale
   (`test_typst_editorial_plan.py`, `test_pdf_semantic_dossier.py`) restino verdi — quelli non
   sanno nulla della tua pagina specifica, controllano invarianti generali (copertura degli
   Allegati, note per pagina, nessuna stringa tecnica, watermark).

## Id di contenuto (marker)

`expected_content_inventory` (in `dossier_catalog/__init__.py`) genera, per ogni blocco:
- `kind: "cover"` → `["cover"]` (uno per documento, solo sulla copertina)
- `kind` in `("chart", "text", "note", "index")` → `[item["id"]]`
- `kind == "table"` → `["heading:" + item["id"], *(row["id"] for row in item["rows"])]`

**Ogni id deve essere univoco nell'intero documento**: due pagine non possono mai dichiarare lo
stesso `item["id"]` (la generazione solleva `ValueError: duplicate editorial content id`). Per le
tabelle degli Allegati, l'id di riga è `f"row:{statement.id}:{row.id}"` (nota: `row.id` è già
prefissato dal proprio statement nel modello — `"income_statement:ce01_ricavi_vendite"` — quindi
il marker finale ha il prefisso due volte, `"row:income_statement:income_statement:..."`: non è un
refuso, è la stessa convenzione che aveva `editorial_inventory.py`, e `editorial_plan.py` la
riconosce esattamente così per ricostruire quali righe stanno su quale pagina fisica).

## Grafici: costruiti una volta, mai ricercati per id

Un grafico non è più necessariamente una voce di `report.chart_series` (le 6 serie canoniche v1 +
le 10 aggiunte dal dossier): può essere una composizione di pagina, come «Evoluzione dei margini»
sul CE previsionale (`practice.ebitda_margin` + `analytical.profitability.ros`, limitati agli anni
di piano). Per questo `chart_declarations(report)` (in `dossier_catalog/__init__.py`) mappa
`content_id -> item` dal catalogo stesso, e sia `editorial_plan.py` (verifica ciò che Typst ha
disegnato) sia `editorial_notes_service._page_context` (contesto per il commento AI) leggono da lì
— mai un secondo lookup in `report.chart_series`, che darebbe `KeyError` su un grafico di pagina.

## Hash del generatore

`editorial_plan.py::_GENERATOR_HASH` lega l'identità del layout all'**intero pacchetto**
`dossier_catalog/` (ogni file `.py` al suo interno, in ordine), non più a un solo file: modificare
`allegati.py` invalida i piani già misurati esattamente come modificare `shared.py`. Se aggiungi un
nuovo file al pacchetto non devi fare nulla: `_GENERATOR_FILES` lo trova da sé (`glob('*.py')` alla
prima importazione del modulo — un worker già avviato non lo vede finché non riparte, come già per
`uvicorn --reload` sui moduli condivisi).

## Cosa NON esiste più (rimosso con `editorial_inventory.py`, non "morto")

- Il dump generico dell'intero modello (assunzioni annidate riga per riga, catalogo indicatori a
  blocchi, tabelle di confronto dei periodi, «Calcoli previsionali canonici»): quelle pagine non
  esistono ancora nel catalogo v4 (dati.py, indicatori.py) e chi le implementa le riscrive da capo
  sul modello v2 attuale, **non** le recupera da git blame come fossero ancora valide — in
  particolare `_resolve_field_label`/`_FORECAST_LABEL_OVERRIDES` (la risoluzione dell'etichetta di
  una riga di `report.forecast.years[].income_statement`, con fallback e `raise` se il codice non
  risolve) non serve più alle pagine di questa fase: leggono `DetailedStatementRow.label`
  direttamente, sempre un'etichetta italiana vera.
- La divisione delle tabelle per colonne (`value_start`/`part_size`/`#parte:N`) — vedi sopra.

## Prova su dati reali (AMBIENTA)

Procedura (DB reale **mai aperto in scrittura**):
```python
import os
os.environ["DATABASE_PATH"] = "/percorso/copia.db"   # PRIMA di ogni import di database.db
# ... service.prepare(db, company_id, scenario_id, PrepareEditorialRequest(...))
# ... final_report_pdf_service.render_pdf(db, company_id, scenario_id)
```
Azienda 575 (AMBIENTA), scenario 18 (budget, workflow infrannuale) → 12 pagine: copertina,
sintesi, CE previsionale, indice allegati, Allegato A (2 parti), B (4 parti), C (2 parti). PDF di
prova: `inbox/artifacts/2026-09-17-m2-02d/ambienta-fase1.pdf` (fuori da git — percorso assoluto).

## Cosa manca ancora (dichiarato, non un buco silenzioso)

- **dati.py e indicatori.py**: registro vuoto. Il catalogo v4 le prevede alle pagine 3-6 e 11-18.
- **Allegato D/E/F/G, metodologia**: non implementati in `allegati.py`.
- **Pagina 2 (sintesi), blocco «Decisioni e punti da presidiare»**: nella v4 è un elenco a due
  colonne (elementi favorevoli / verifiche prioritarie) sotto il grafico. Il modello v2 non ha un
  campo per questo (non è "readiness.reasons": quelli sono diagnostiche, non punti di forza) — la
  pagina lo omette invece di inventarlo. Se un campo del genere arriva al modello, va aggiunto qui.
- **CE previsionale, riga "Ricavi"**: è `production_value` (Totale Valore della Produzione), non
  `ce01_ricavi_vendite`, perché deve tornare esattamente con "Costi operativi" ed "EBITDA" nella
  stessa tabella (altrimenti Ricavi − Costi ≠ EBITDA a vista, come se il prospetto non quadrasse).
  Il KPI "ricavi" in cima alla pagina resta invece sui ricavi delle vendite (con i soliti fallback
  di `shared.kpi_revenue_now`) — le due cifre possono differire, di proposito: chi implementa SP/
  Flussi tenga presente questa scelta come precedente, non la riscopra da capo.
- **Grafico "Evoluzione dei margini"**: usa `practice.ebitda_margin` + `analytical.profitability.ros`
  (un margine operativo reale, non ribattezzato "EBIT margin": nessun indicatore con quel nome
  esatto esiste nel catalogo — l'etichetta stampata è quella vera dell'indicatore, non inventata).
