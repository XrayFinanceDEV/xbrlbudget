# Report Business plan (PDF)

Il report di `/report`: dal 2026-09-24 l'unico, perché il dossier Typst è staccato dall'interfaccia (rotte e codice
restano, per un prodotto successivo più avanzato). Riproduce il layout del business plan preparato dal
committente (`BUSINESS PLAN RIVISITATO.pdf`, fuori da git) con i numeri del motore.

**Dove sta:** `backend/app/renderers/business_plan/` (ReportLab + matplotlib), servizio
`services/business_plan_pdf_service.py`, rotta `POST /companies/{id}/scenarios/{sid}/business-plan/pdf`
(`{"document_state": "draft"|"final"}`), pulsanti su `/report`. Il «finale» chiede `readiness.status == "ready"`: i
testi AI mancanti del dossier (`narrative_missing`) sono solo `info` e non lo bloccano più.

**Da dove vengono i numeri:** solo da `FinalReportModelV2`, via `data.from_report`. Il report somma e sottrae righe
già presenti (costi operativi = costi della produzione − ammortamenti; debiti finanziari = PFN + liquidità) e non
ricalcola indicatori. DSCR = (MOL − imposte) / (oneri finanziari + quota capitale delle rate dei piani) — non è più
un proxy (lotto 2 fix rilievi, 2026-09-26). Decisione del proprietario 2026-09-26 (F2): sugli anni di piano la quota
capitale viene da `ForecastYear.engine_meta['rimborsi_piano']` del motore — le sole rate di uno scadenziamento vero
(contratti bancari, pregresso bancario su piano anni, altri finanziatori), mai il rimborso di uno scoperto, di un
fido o dello sweep di cassa (che un rendiconto-derivato mischiava nella stessa riga: uno scenario con crescita
−40/+80/0 e scoperto concesso faceva crollare il DSCR da 3,29× a 0,90× solo per il rimborso dello scoperto, senza
alcuna rata contrattuale in più). `None` con `rimborsi_piano_non_disponibile` quando l'anno non ha `rimborsi_piano`
dichiarato (nessun `engine_meta` persistito, o un motore più vecchio di questa correzione). Sulla colonna
base/storica la quota resta quella di prima (`calculations/report_indicators._dscr_capital_quota`): la diminuzione
netta del debito finanziario dell'anno, da `financing.third_party_funds.decreases` del rendiconto dettagliato;
`None` quando il periodo non ha un rendiconto (prima colonna storica, periodi infrannuale `observed`/`adjusted`) o
quando `erogazioni_incoerenti` è vero — mai una cifra ricostruita al suo posto.

Il punto di pareggio (SEZIONE 4, "Costi fissi e variabili · break even point") sugli anni di piano viene da
`ForecastYear.engine_meta['pareggio']`, non da una ripartizione fissa 60/40 costi fissi/variabili; `None` con
`engine_meta_missing` o `pareggio_non_definito` quando il motore stesso non li ha definiti (ce05/ce06 sotto
override). Decisione del proprietario 2026-09-26 (F5): la colonna base/storica applica ORA la STESSA regola del
motore (`calculations.projection_common.punto_di_pareggio`, un'unica implementazione condivisa) al CE di base, con
le quote fisso/variabile di ce05/ce06 del PRIMO anno di piano — così le due colonne sono confrontabili con la
stessa aritmetica, senza il finto risanamento che il testo raccontava come «negativo nell'anno base ... positivo
dal primo anno di piano» quando la vecchia ripartizione 60/40 blended sulle cinque voci operative canoniche
divergeva dalla regola vera del motore. Senza ipotesi di piano salvate: resta il 60/40 di default, dichiarato,
applicato però solo a ce05/ce06 (mai più spalmato anche su ce07/ce08/ce12, che il motore tratta come interamente
fissi).

**Rendiconto (SEZIONE 5 "Flussi di cassa", ALLEGATO C "Rendiconto finanziario completo"):** quando l'anno dichiara
le proprie erogazioni
(`ForecastYear.engine_meta['erogazioni']`: prestiti nuovi, altri finanziatori, tiraggio fidi e scoperto generato),
la riga "mezzi di terzi" si separa in erogazioni e rimborsi invece di mostrare il solo netto; un flag interno,
`erogazioni_incoerenti`, segnala quando le erogazioni note non bastano a spiegare l'aumento di debito e fa
ripiegare sulla riga netta di sempre. Un anno senza `engine_meta` (scenari generati prima del lotto 2, o
promossi dall'infrannuale) si comporta come prima: nessuna separazione.

**Avviso di previsionale vecchio (A01-bis):** oltre a `forecast_stale` (ipotesi salvate dopo l'ultima
generazione), il "finale" si blocca anche con `engine_version_stale` — un `ForecastYear` generato da una versione
precedente di `calculations/forecast_engine.ENGINE_VERSION` — mai per l'infrannuale. In intestazione compare solo
la forma corta «BOZZA · da rigenerare» (la frase intera per esteso troncherebbe il nome dell'azienda); le frasi
intere della spec stanno in copertina, una per riga (`BusinessPlanData.avvisi`, `data.py`). `engine_meta` assente,
o senza la chiave `engine_version`, non genera alcun avviso.

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
