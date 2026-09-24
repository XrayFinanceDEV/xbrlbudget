# Report Business plan (PDF)

Secondo report PDF della pratica, accanto al dossier Typst. Riproduce il layout del business plan preparato dal
committente (`BUSINESS PLAN RIVISITATO.pdf`, fuori da git) con i numeri del motore.

**Dove sta:** `backend/app/renderers/business_plan/` (ReportLab + matplotlib), servizio
`services/business_plan_pdf_service.py`, rotta `POST /companies/{id}/scenarios/{sid}/business-plan/pdf`
(`{"document_state": "draft"|"final"}`), selettore «Modello» su `/report`.

**Da dove vengono i numeri:** solo da `FinalReportModelV2`, via `data.from_report`. Il report somma e sottrae righe
già presenti (costi operativi = costi della produzione − ammortamenti; debiti finanziari = PFN + liquidità) e non
ricalcola indicatori. DSCR proxy = (EBITDA − imposte) / oneri finanziari.

**Testi:** `narrative.py`, regole deterministiche con soglie in `SOGLIE`. Nessun LLM. Per cambiare una frase si
cambia una regola o una soglia, e il test `tests/test_bp_narrative.py` ne fissa il comportamento su AMBIENTA.

**Banco di prova:**
- `tests/test_bp_banco.py` confronta riquadro per riquadro le sezioni 2, 4 e 5 (numeri del committente, in
  `tests/fixtures/business_plan/banco_ambienta.json`) con le pagine 4, 6 e 7 del suo PDF. Tolleranze: 8 pt su y0,
  3 pt sull'altezza, 2 pt su x. Si allarga uno spazio, mai una tolleranza.
- `tools/business_plan/confronta.py` affianca tutte le pagine di AMBIENTA al riferimento, per la verifica con la vision.
- Il PDF del committente va copiato in `tests/.banco-business-plan/riferimento.pdf` (gitignored); senza, il banco si salta.

**Trappole:**
- matplotlib solo con `Figure` e `FigureCanvasAgg`, mai `pyplot`, e nessuna modifica di `rcParams`: FastAPI esegue la
  rotta in un threadpool.
- L'indice della copertina nasce da due passate di `doc.build`: la copertina deve avere altezza fissa, o la seconda
  passata sposta le pagine (lo verifica un `assert` in `render_business_plan`).
- Un valore assente è `None` fino alla stampa (`n.d.`), mai zero.


**Il Word (.docx):** «Scarica Word» chiama `POST …/business-plan/docx`, stesso corpo e stessi errori della rotta PDF.
Non è un secondo renderer: `backend/app/renderers/docx_export.py` traduce in `python-docx` gli stessi flowable che le
sezioni danno al PDF, quindi un testo corretto nel codice cambia PDF e Word insieme. Testi e tabelle sono
modificabili, i grafici sono i PNG del PDF (`layout.chart` li conserva in `Image.png`), copertina e intestazioni
vengono da `cover_lines` e `page_texts`, le stesse funzioni che usa il PDF. L'indice non ha numeri di pagina (in
Word si spostano alla prima correzione). I commenti corretti nel Word restano nel file: l'app non li rilegge.
Trappole:
- un flowable che il traduttore non conosce solleva `TypeError`: una primitiva nuova in `layout.py` va insegnata
  anche a `docx_export.translate`, o il Word di quella sezione si rompe. `tests/test_docx_report.py` confronta ogni
  riga di testo del PDF col Word, su AMBIENTA e sugli scenari fuori dal banco;
- `python-docx` sta in `backend/requirements.txt` di proposito: nel venv arrivava solo con docling, codice morto;
- Word non incorpora Lato: sul PC senza il font usa il suo ripiego, e il documento resta corretto.
