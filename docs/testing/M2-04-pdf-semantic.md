# M2-04 — harness PDF semantico

Nuovi file soltanto: `tests/pdf_semantic/__init__.py` (helper generici, model-agnostic) e
`tests/test_pdf_semantic_dossier.py` (wiring sul modello v2 + i test). Nessun template,
renderer, inventario, fixture o test esistente toccato. Riusa la costruzione di piano/note
di `tests/test_typst_editorial_plan.py` (`fixture_report`, `prepare_editorial_report`,
`verify_editorial_layout`, `with_notes`) importandola, senza copiarla.

## Perché poppler e non PyMuPDF

Il renderer valida già il proprio output con `fitz` (`app.renderers.typst.runtime.validate_pdf`).
Un secondo controllo costruito sulla stessa libreria non sarebbe un oracolo indipendente: un bug
condiviso fra renderer e validatore ingannerebbe entrambi. L'harness legge invece con
`pdftotext`/`pdffonts`/`pdfinfo` (poppler-utils, già presenti sul sistema: `/usr/bin/pdftotext`,
`pdffonts`, `pdfinfo`, versione 24.02.0) — il testo che un umano o uno screen reader otterrebbero
dal PDF, non i metadata di layout che Typst misura internamente.

## Che cosa verifica

- `%PDF-` in testa, non cifrato, titolo `pdfinfo` = `report.document.title`, pagine `pdfinfo` =
  pagine del piano editoriale, font tutti incorporati (`pdffonts`, colonna `emb`), sia su `draft`
  sia su `final`.
- Titolo neutro in copertina.
- Ogni riga di CE/SP/rendiconto (`detailed_statements`) è sulla pagina fisica che il piano
  editoriale le assegna (etichetta presente), e per le righe applicabili di tipo
  `detail`/`subtotal`/`total` anche il valore, formattato **esattamente** come il template
  (euro interi, arrotondamento al mezzo euro, separatore delle migliaia): la formula è la
  trascrizione in Python di `chart-format.typ`'s `display-value(value, "eur", places: 0)`,
  la stessa usata da `editorial.typ`'s `cell()` per ogni cella con `unit == "eur"`. Per ogni
  prospetto si controlla anche che il numero di righe del modello coincida con il numero di
  marcatori `row:...` che il piano porta (`assert_appendix_row_count_matches_plan`).
- La nota assegnata a ogni pagina fisica compare su quella pagina, letta con
  `pdftotext -f N -l N` come richiesto dal brief.
- Watermark di bozza (`BOZZA`) su ogni pagina in `draft`, assente in `final`.
- Sezioni condizionali: il testo `«Il confronto non annualizza gli importi infrannuali...»`
  (unico al workflow infrannuale, guardato da `workflow_type == "infrannuale"` in
  `editorial_inventory.build_inventory`, non da `infrannual_closing is not None`) compare solo
  nel workflow infrannuale; idem `infrannual_closing is not None` e la sezione `infrannual_closing`
  nel piano.
- Nessuna stringa tecnica vietata (`historical:`, `forecast:`, `practice.`, `synthetic_`,
  `Unità: ratio`) — vedi sotto, xfail dichiarato.

Tre fixture v2 (`bilancio`, `infrannuale`, `startup`), orizzonte 2027-2029, compilate una sola
volta per workflow (fixture `dossier`, `scope='module'`, parametrizzata): ogni test la riusa,
niente ricompilazioni.

## Scoperte fatte costruendo l'harness (non bug del template, limiti dell'estrazione testo)

1. **`-layout` rompe un'etichetta andata a capo vicino a una colonna numerica.** Misurato su
   `"2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti"`: con `-layout`
   la seconda riga avvolta (`finiti`) viene ricollocata *dopo* i valori numerici della riga
   (`0 0 0`), spezzando la contiguità del testo. `-raw` (ordine del content stream, cioè
   l'ordine di disegno di Typst: etichetta, poi nota di contesto, poi valori) la mantiene intatta.
   L'harness usa `-raw` per copertina, righe degli Allegati, marcatore infrannuale e watermark;
   `-f N -l N` per la nota di pagina è rimasto `-raw` di default nello stesso helper
   (`page_text_range`, `mode='raw'`).
2. **Zero-width space dopo `_ + / .` in ogni cella senza unità dichiarata.** `editorial.typ`'s
   `cell()` inserisce `​` dopo questi quattro caratteri per permettere l'andata a capo di ID
   tecnici lunghi — e lo fa anche sull'etichetta (colonna `Voce`, `unit=None`). `normalize()`
   rimuove i caratteri invisibili prima del confronto.
3. **Un'andata a capo esattamente su uno di quei quattro caratteri, senza uno spazio reale
   accanto, produce uno spazio *fantasma* dopo la normalizzazione.** Misurato su
   `"plus/​"` + ritorno a capo + `"minusvalenze"` (nessuno spazio reale in origine):
   `.split()`/`.join(" ")` la trasforma in `"plus/ minusvalenze"`, diverso dall'etichetta pulita
   `"...plus/minusvalenze"`. Fix: `normalize()` rimuove anche lo spazio che segue uno dei quattro
   caratteri, su **entrambi** i lati del confronto — innocuo sul testo genuino (una frase con
   `". "` normale collassa allo stesso modo su etichetta e pagina), risolve i punti di
   andata-a-capo ambigui.
4. **Etichette di prospetto coi due spazi iniziali d'indentazione** (`CLAUDE.md`, «I due spazi
   iniziali di un'etichetta... sono comportamento»): l'indentazione è resa da Typst come layout,
   non come spazi letterali nel testo estratto. `assert_text_present`/`assert_text_absent`
   normalizzano anche il *needle*, non solo la pagina, altrimenti un'etichetta come
   `"  materie prime"` non sarebbe mai verificabile.

Nessuna di queste è una scoperta sul template: sono limiti/comportamenti di
`pdftotext` che l'harness doveva conoscere per non produrre falsi negativi sistematici.

## xfail dichiarato

`test_no_forbidden_technical_strings_leak_into_the_dossier`, `xfail(strict=True)`, motivo
`"M2-02B"`. Confermato a mano sul PDF corrente (`pdftotext -raw` sull'intero documento, fixture
`infrannuale` 2027-2029): righe come `ID: historical:2025`, `Base: forecast`,
`practice.dscr`/`practice.ebitda_margin` nel catalogo indicatori, `Unità: ratio`,
`synthetic_fixture` nella tabella dei periodi delle fonti. Diventerà verde — e l'xfail va tolto
nello stesso commit — quando M2-02B pulisce `editorial_inventory.py`/`editorial.typ` per non
stampare più ID tecnici e unità grezze nei blocchi narrativi e nel catalogo. La logica del check
è stata verificata separatamente su testo pulito e su testo con un token vietato: si comporta
correttamente in entrambi i casi, l'xfail riflette lo stato del template, non un bug del test.

## Prova di mutazione

`test_harness_fails_when_a_row_or_a_note_is_missing_from_the_rendered_text` muta **in memoria**
una copia del report già compilato (mai il template, mai il PDF, che restano quelli compilati
una sola volta dalla fixture di modulo) e dimostra che le stesse funzioni usate dai test del
percorso verde sollevano `AssertionError`:

1. **Riga rietichettata** (`mutated_row.label = 'RIGA CHE IL TEMPLATE NON STAMPA PIÙ'` su una
   copia profonda di `income_statement`): la pagina reale porta ancora l'etichetta originale,
   quindi cercare la nuova etichetta fallisce — simula una riga che il template ha smesso di
   stampare correttamente.
2. **Riga tolta dall'elenco del modello** (`ce01_ricavi_vendite` rimossa da una copia della
   lista `rows`): `assert_appendix_row_count_matches_plan` confronta il numero di righe dichiarate
   dal modello con il numero di marcatori `row:...` che il piano/PDF portano davvero, e fallisce
   sullo scarto.
3. **Nota di pagina cambiata** (`mutated_note.text = 'NOTA CHE NON COMPARE SU QUESTA PAGINA'` su
   una copia della nota di pagina 1): la pagina reale porta ancora il testo originale.

Eseguito anche fuori da `pytest.raises`, per riportare qui il messaggio esatto (fixture
`bilancio`, 2027-2029, pagina 33):

```
--- MUTATION 1: relabelled row ---
OK: row:income_statement:income_statement:ce01_ricavi_vendite on page 33:
    'RIGA CHE IL TEMPLATE NON STAMPA PIÙ' not found
--- MUTATION 2: dropped row from model row list ---
OK: income_statement: model declares 46 appendix row(s), the editorial plan carries 47
--- MUTATION 3: changed note text ---
OK: note on physical page 1: 'NOTA CHE NON COMPARE SU QUESTA PAGINA' not found
```

Sono le stesse funzioni (`assert_text_present`, `assert_appendix_row_count_matches_plan`) usate
dai test del percorso verde: la sensibilità non è dimostrata su un doppione, sull'harness vero.

## Skip pulito

Verificato puntando `TYPST_TEST_BINARY` a un percorso inesistente: 27 test saltati (nessun
errore, nessun fallimento) — la fixture `probe` controlla binario Typst, `/usr/bin/bwrap` e i tre
binari poppler prima di compilare qualunque cosa.

## Esecuzione e durata

```
PYTHONPATH=backend TYPST_TEST_BINARY=tools/typst/bin/typst \
  .../backend/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pdf_semantic_dossier.py
```

`24 passed, 3 xfailed` in **31-33 secondi** (compilazioni reali con `bwrap`, quattro invocazioni
del compilatore per workflow: measure×2 in `prepare`/`verify`, render `draft`, render `final` —
dodici in tutto sui tre workflow). Binario Typst copiato in locale da
`/home/peter/DEV/budget/tools/typst/bin/typst` (stesso sha256 `29273eaa...` pinnato in
`tools/typst/manifest.json`), non committato (gitignored).

## Rischi residui

- Il confronto testo-per-testo su `pdftotext` è, per costruzione, più permissivo di un confronto
  visivo: non verifica posizione, colore o dimensione — solo che il contenuto testuale corretto
  sia leggibile sulla pagina giusta. È il compromesso esplicito del brief (indipendente
  dall'impaginazione), non una lacuna dell'harness.
- `normalize()` rimuove lo spazio dopo `_ + / .` su **entrambi** i lati del confronto: teoricamente
  potrebbe far coincidere due etichette realmente diverse solo se differiscono esclusivamente per
  uno spazio proprio dopo uno di quei quattro caratteri — scenario non osservato nel corpus delle
  tre fixture, ma degno di nota per chi estenda l'harness.
- Il controllo watermark/font/riga è stato misurato solo sulle fixture sintetiche dei tre
  workflow con orizzonte 2027-2029; il brief non richiede la matrice workflow × orizzonte (a
  differenza di M2-02B) e non è stata eseguita qui per contenere la durata della suite.
- Quando M2-02B sostituisce il template, l'xfail deve sparire nello stesso commit che lo rende
  verde: se resta con `strict=True` e il test inizia a passare, la suite fallisce da sola
  (comportamento voluto, non un rischio da mitigare).
