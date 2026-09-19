# M2-02B — integrazione: composizione contro la v4

**Worktree:** `XrayFinanceDEV/m2-02b-integrazione`, base `5fe62a6` (merge di S1
«pagina tipo, assi» + S2 «tabelle F/G, ipotesi, metodologia» dentro
`fix/quadratura-rettifiche`). Commit di questo giro:
`dfa2231` (correzioni al merge), `646cd73` (note compatte + etichette mai
codice campo + xfail M2-04 tolto), `0f96fd5` (`editorial-3`).

> **Nota 2026-09-18.** `editorial_inventory.py` non esiste più: il catalogo è stato spezzato nel
> pacchetto `backend/app/renderers/typst/dossier_catalog/`, dove la stessa informazione sta su più
> moduli e i suoi `_forecast_table` / `_statement_table`, citati qui sotto, **non hanno un
> successore uno-a-uno**. Le osservazioni di composizione restano valide; i due nomi si leggono
> come nomi storici, non come funzioni da aprire.

Riferimento visivo: `inbox/artifacts/2026-09-15-report-finale/report-finale-anteprima-v4.pdf`
(33 pagine, workflow bilancio). Bozza di collaudo:
`inbox/artifacts/2026-09-17-m2-02b/ambienta-bozza.pdf` (53 pagine, azienda
AMBIENTA reale, workflow infrannuale — più pagine della v4 perché porta anche
le sezioni 3–6, solo infrannuali).

## Che cosa ha rotto il merge, e come l'ho corretto

Le due metà (S1 su `editorial.typ`/`editorial_plan.py`, S2 su
`editorial_inventory.py`) non si erano mai viste, e nessuna delle due aveva
ancora M2-02C (`structure_series`), M2-04 (harness semantico) o M2-05
(endpoint PDF). Sulla suite completa (15 file) due rotture reali:

1. **`tests/test_typst_dossier_base.py`** — il test dell'importo troppo
   grande per la pagina mutava solo `ce01_ricavi_vendite`, senza aggiornare
   `structure_series.break_even.contribution_margin` che M2-02C ha legato
   alla stessa riga. La validazione del modello falliva prima di arrivare al
   `panic` di layout che il test vuole osservare
   (`RendererInputError` invece di `RendererCompileError`). Corretto
   allineando `contribution_margin` alla riga mutata.
2. **`backend/app/services/editorial_notes_service.py`** — `_page_context`
   non conosceva i marcatori `#parte:N` che una tabella periodica divisa in
   parti produce (S1, Allegati verticali oltre `part_size` periodi:
   `INDICATOR_PART_SIZE=4`, scenario startup a 5 anni). Una pagina
   autorizzata che li referenzia falliva con «Il contesto non corrisponde al
   contenuto della pagina», bloccando la preparazione dei commenti AI sullo
   startup a 5 anni. Corretto specchiando la stessa matematica di
   `expected_content_inventory`.

Un terzo giro di 5 fallimenti/34 errori visto durante lo sviluppo
(`RendererUnavailable`, hash del generatore) era autoinflitto: stavo
modificando `editorial_inventory.py` mentre una suite in background lo
importava — il guardiano dell'hash (`_GENERATOR_HASH`,
`editorial_plan.py:25`) ha fatto esattamente il suo lavoro. Non è una
regressione; la suite pulita rieseguita subito dopo era verde.

## Rilievo del coordinatore sulla bozza intermedia (prima della ricevuta)

Guardando `ambienta-bozza.pdf` a metà lavoro il coordinatore ha trovato tre
difetti che nessuna fixture esercita mai (il loro `label` è già un'etichetta
vera): sono stati aggiunti a questo giro, prima di chiudere.

### 1. Chiavi tecniche come etichetta di riga (misurato su AMBIENTA)

`report.forecast.years[].{income_statement,balance_sheet,cashflow}` e
`report.infrannual_closing.values[]` portano il **campo DB come `label`** sui
dati reali (il servizio a monte non gliene assegna uno). Su AMBIENTA
l'intero «Conto economico previsto», «Stato patrimoniale previsto» e
«Rendiconto finanziario previsto» stampavano `ce01_ricavi_vendite`,
`sp06c_crediti_collegate_breve`, `cashflow.operating.start.net_profit` come
etichetta — e «Valori di chiusura» pure, con `cashflow.base_year` stampato
come se fosse un importo («2.026»).

Corretto in `editorial_inventory.py` (`_resolve_field_label`,
`_detailed_labels`, `_FORECAST_LABEL_OVERRIDES`, `_FORECAST_LABEL_EXCLUDED`):
ogni riga risolve l'etichetta **prima** da `report.detailed_statements`
(nome e gerarchia veri, la stessa fonte degli Allegati A/B/C), **poi** da una
mappa esplicita per le voci che gli Allegati aggregano invece di
spacchettare — i sette sotto-conti di `sp02`, i cinque di `sp03`, i due di
`sp01` (fonte: `docs/taxonomy/SCHEMA_ENHANCEMENTS.md`), le tre aggregate
`sp12_riserve`/`sp16_debiti_breve`/`sp17_debiti_lungo` (fonte:
`database/models.py`), e i saldi netti del rendiconto mai persistiti come
colonna (`cashflow.financing.own_funds.net` e simili, etichettati con la
stessa convenzione «Voce — Sotto-voce» delle righe sorelle già presenti) —
**poi** dal `label` del modello se è già uno vero (così le fixture esistenti,
che lo sono, restano invariate). Un codice che non risolve in nessuno dei tre
solleva `ValueError` invece di stampare il codice: un campo nuovo, domani,
si scopre alla generazione, non a schermo. Due campi puramente anagrafici
(`cashflow.base_year`, `cashflow.year`) non entrano più in tabella.

Stesso difetto, forma più piccola, nell'Allegato E: le voci "Pregresso"
componevano l'etichetta con la chiave Python del piano
(`f"Pregresso {plan_name}"` → «Pregresso crediti_commerciali»); ora
`_PREGRESSO_PLAN_LABELS`/`_PREGRESSO_FIELD_LABELS` la scrivono con lo spazio
(«Pregresso crediti commerciali», «… — acconto»).

**Non corretto, dichiarato:** un override manuale di Allegato E
(«Override CE `ce02_override`», «Indicizzazione SP `sp16g`») porta ancora il
nome di colonna scelto dall'utente. A differenza dei codici sopra — un
insieme piccolo e finito, fisso nello schema — questo è un campo qualunque
fra 32 colonne `ce*_override` e un insieme `sp` aperto: nessuna mappa finita
lo coprirebbe onestamente. Escluso per prefisso (non per valore) dal nuovo
controllo del harness, con un commento che lo nomina come gap noto e
separato, non compreso in questo giro.

### 2. «Valori di chiusura»: nota ripetuta per riga

Sotto ogni riga della tabella «Valori di chiusura al …» compariva ancora
«n.d.: valore automatico non dichiarato» — la colonna di coda inline, non
raggruppata come le ipotesi. Tolta la colonna «Indisponibilità»; una nuova
funzione `_grouped_reasons_text` (senza asse di periodi: questa tabella non
ne ha uno, `observed`/`comparable`/`automatic`/`override` sono stati, non
anni) raggruppa le righe che condividono lo stesso stato mancante in una
frase sola — «Automatico non dichiarato: Riserve, Sovrapprezzo azioni,
…» — stampata come nota piccola sotto la tabella. La tabella non usa più
`_periodic_table` (quel wrapper riservava l'ultima colonna alla nota per
riga, che non c'è più): sei colonne di valore rendono bene nel ramo generico
di `data-table`.

Stesso trattamento anche per un difetto gemello, minore, trovato per
sicurezza nello stesso giro: `_statement_table` (Allegati A/B/C) ripeteva la
stessa motivazione una volta per periodo nella colonna di coda di una riga
(«campo non previsto dal modello» × 7 per la riga «Trattamento di quiescenza
e simili» su AMBIENTA); ora la dice una volta per riga con `dict.fromkeys`.

### 3. Test che lo dimostra

Due test di mutazione senza compilare Typst
(`tests/test_editorial_inventory.py`,
`test_forecast_line_without_a_resolvable_label_raises_instead_of_leaking_the_code`
e l'equivalente per `infrannual_closing`): una riga con `label == code` non
risolvibile né da `detailed_statements` né dalla mappa né dal modello stesso
fa sollevare `build_inventory`, dimostrando che il meccanismo blocca il
difetto invece di limitarsi a non stamparlo nelle fixture attuali (che non
lo esercitano mai). Più un controllo indipendente a livello di testo PDF
(`tests/pdf_semantic/__init__.py:assert_no_field_code_style_labels`,
`tests/test_pdf_semantic_dossier.py:test_no_field_code_style_labels_leak_into_the_dossier`),
regex `\b[a-z][a-z0-9]*(?:[_.][a-z0-9]+)+\b` con eccezioni finite e motivate
(le colonne «Codice»/«Identificativo» dei diagnostici, `n.d` come lo legge
`pdftotext`) — non gira mai rosso sulle fixture (il loro `label` è già
vero), è la difesa indipendente del harness, non la prova di mutazione.

## Suite eseguite

```
PYTHONPATH=backend TYPST_TEST_BINARY=tools/typst/bin/typst \
  /home/peter/DEV/budget/backend/venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_typst_editorial_plan.py tests/test_typst_dossier_base.py \
  tests/test_typst_layout_probe.py tests/test_typst_charts.py \
  tests/test_typst_base_plan.py tests/test_typst_runtime.py \
  tests/test_editorial_inventory.py tests/test_typst_m2_02b_tabelle.py \
  tests/test_editorial_notes_endpoint.py tests/test_editorial_notes_service.py \
  tests/test_editorial_note_context.py tests/test_final_report_pdf_endpoint.py \
  tests/test_pdf_semantic_dossier.py tests/test_final_report_v2.py \
  tests/test_typst_note_fit.py
```

**328 passed, 1 skipped, in 249,02 s** (esecuzione pulita, nessuna modifica
concorrente — la run precedente, inquinata dalle mie stesse modifiche a
`editorial_inventory.py` a metà corsa, aveva mostrato 34 errori/2 falliti
tutti spiegati dal guardiano dell'hash, non da un difetto: rieseguita e
verde). Riconfermato dopo il commit finale, insieme a `test_typst_toolchain.py
tests/test_deployment_docs.py` nella stessa esecuzione: **371 passed, 1
skipped, in 285,28 s** (328 + 43, nessuna regressione). Scomposizione
rilevante:

- `tests/test_pdf_semantic_dossier.py`: **30 passed** (era 24 passed + 3
  xfailed prima di questo giro — tolto l'xfail su
  `test_no_forbidden_technical_strings_leak_into_the_dossier`, che passava
  già da solo dopo il merge di S1+S2 (XPASS strict); aggiunti i 3
  `test_no_field_code_style_labels_leak_into_the_dossier`, uno per workflow).
- `tests/test_editorial_inventory.py`: **12 passed** (10 + 2 nuovi test di
  mutazione).
- `tests/test_typst_m2_02b_tabelle.py`: **12 passed**, riscritti per il nuovo
  formato compatto (kind `note`, niente titolo, testo raggruppato per
  intervallo invece che per anno).

```
PYTHONPATH=backend TYPST_TEST_BINARY=tools/typst/bin/typst \
  /home/peter/DEV/budget/backend/venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_typst_toolchain.py tests/test_deployment_docs.py
```

**43 passed in 7,61 s** (punto 4, invariati da questo giro — verificati
comunque, nessuna assunzione sulla stringa `editorial-2`/`editorial-3` in
quei due file).

Matrice tre workflow × orizzonti 1/3/5 anni (punto 5): coperta da
`test_full_real_composition_has_exact_pages_appendix_rows_and_slots`
(`tests/test_typst_editorial_plan.py`, `@pytest.mark.parametrize` su
workflow × years), dentro la suite da 328; nessun test dedicato aggiuntivo
necessario.

## Export di prova AMBIENTA (azienda 575, scenario 18)

DB reale **mai aperto in scrittura**: copiato in
`/tmp/.../scratchpad/ambienta-copia.db`, `DATABASE_PATH` puntato lì prima di
importare qualunque modulo che legge il DB (va impostato **prima**
dell'import di `database.db`, altrimenti la cache del modulo lega l'engine al
percorso di default — mi è capitato lavorando, vedi «Rischi»). Piano
editoriale preparato via `editorial_notes_service.prepare` (azione reale,
non uno stub: scrive sulla copia), PDF renderizzato via
`final_report_pdf_service.render_pdf`. Salvato in
`inbox/artifacts/2026-09-17-m2-02b/ambienta-bozza.pdf` — **53 pagine**,
workflow infrannuale, generato in circa 3 s (preparazione piano + render).

Pagine guardate (Read su PNG `pdftoppm -r 60`): copertina (1), sintesi (2–4),
dati di partenza (5–13), conto economico previsionale (17–20), stato
patrimoniale previsionale (21–23), flussi (24–27), indicatori (28–38),
indice e Allegati A–C (39–50), Tabella F/G (51–52), metodologia (53).

## Pagina per pagina contro la v4

| v4 | Contenuto v4 | Corrispondente AMBIENTA | Esito |
|---|---|---|---|
| 2 · Sintesi | occhiello+titolo+sottotitolo+KPI+grafico+tabella+commento, **una pagina** | pag. 2 (testata+narrativa reale) **poi** pag. 3 (KPI+grafico+tabella) | **Diverge**: con un commento narrativo reale (non segnaposto) prima del primo grafico, la sezione si spacca su due pagine fisiche — vedi «Non corretto» sotto |
| 8 · CE previsionale | KPI+grafico (evoluzione margini) + **tabella di sintesi** (9 righe: Ricavi/Costi operativi/EBITDA/…/Risultato netto) | pag. 17–18 (testata+narrativa+**tabella dettagliata da 21 righe**, non una sintesi), poi pag. 19–20 (grafici propri con KPI+tabella) | **Diverge nella struttura**: il dettaglio completo compare sulla pagina di sezione invece di una sintesi; i grafici della sezione (Incidenze economiche, Incidenza oneri) sono corretti e completi |
| 9 · SP previsionale | stessa struttura, tabella di sintesi 10 righe | pag. 21–23, stessa divergenza di 8: tabella completa (86 righe) invece di sintesi | **Diverge nella struttura**, stesso motivo di 8 |
| 10 · Flussi | KPI+grafico+sintesi | pag. 24 (rendiconto completo 47 righe) + pag. 26 (grafico KPI+tabella «Flussi di cassa e cassa finale») | **Diverge nella struttura**, stesso motivo |
| 11 · Indicatori del piano | KPI+grafico+tabella 4 righe, **una pagina** | pag. 28–29, stessa composizione, **una pagina** | **Corrisponde** |
| 20 · Allegato A parte 1/2 | prospetto completo, € migliaia, etichette italiane | pag. 40–41 (Allegato A), etichette italiane identiche, **€ interi** (scostamento voluto, deciso dal proprietario 2026-09-16) | **Corrisponde**, salvo l'unità (dichiarata) |
| 30 · Tabella F (indicatori pratica) | colonna «Indicatore», unità nella cella (`7,57×`), nota di indisponibilità in fondo | pag. 51 (qui confrontata con Tabella G, stesso impianto): colonna «Indicatore», unità **fra parentesi nell'etichetta** (`(volte)`), nota raggruppata in fondo | **Corrisponde nell'impianto**, diverge nella collocazione dell'unità (dichiarata, vedi sotto) |
| 33 · Metodologia | tabella compatta Indicatore\|Metodologia, convenzione una volta come testo prima | pag. 53, stessa composizione esatta | **Corrisponde** |

## Che cosa corrisponde alla v4

- Pagina tipo delle sezioni «Indicatori» (KPI colonna sinistra 55 mm +
  grafico destra, tabella di sintesi sotto, tutto su una pagina quando non
  precede un blocco narrativo lungo): pag. 19, 28–36.
- Titoli, sottotitoli, etichette tutte in italiano; nessun metadato tecnico
  (`historical:`, `forecast:`, `practice.`, `synthetic_`, `Unità: ratio`) —
  verificato dal test M2-04 ora verde, non più xfail.
- Allegati A/B/C con etichette e gerarchia identiche alla v4, divisi in parti
  verticali quando i periodi eccedono `PERIOD_PART_SIZE`.
- Tabelle F/G compatte, senza colonna «Unità» separata, senza motivazione per
  riga.
- Metodologia e convenzioni: tabella compatta, «Famiglia»/«Soglie» non
  stampati, convenzione scritta una volta.
- Assi in euro interi sotto i 10.000 €, € migliaia sopra, mai `×10^3`.
- Nessun riquadro «n.d.» a pagina intera, nessun grafico senza serie.
- Nessun codice campo o chiave Python come etichetta di riga (questo giro).

## Che cosa ancora differisce dalla v4 (dichiarato, non corretto qui)

1. **Unità in parentesi nell'etichetta, non nella cella** (Tabelle F/G):
   scelta esplicitamente ammessa dal piano come alternativa a un formattatore
   di unità nel template (`tests/test_typst_m2_02b_tabelle.py`, commento di
   S2). Non un difetto, uno scostamento deciso.
2. **Pagine 16–17 della v4 (composizioni, pareggio) assenti.** I dati
   (`report.structure_series`, da M2-02C) sono nel modello dal merge
   base — `editorial_inventory.py` non li referenzia in nessun punto
   (verificato: `grep structure_series` non trova nulla). Implementarli è un
   task a parte con la sua stima, non incluso in questo giro di
   integrazione: nessuna riga aggiunta all'indice, nessun riquadro vuoto —
   restano semplicemente assenti, come voluto dal piano finché mancano i
   dati (qui ci sono, manca la resa).
3. **Le pagine di sezione con più elementi prima del primo grafico
   spaccano su due pagine fisiche invece di una.** `editorial.typ` fa
   `pagebreak(weak: true)` prima di ogni grafico con indice > 0 nella lista
   degli item della sezione: se la sezione ha già un blocco narrativo reale
   (non segnaposto — quelli sono filtrati dal rilievo 2) o una tabella prima
   del grafico, quest'ultimo va comunque a una pagina propria. Sulle fixture
   di test la narrativa è sempre segnaposto (filtrata, rilievo 2) o assente,
   quindi nessun test la esercita; su AMBIENTA, con narrativa reale salvata,
   si vede: pag. 2 (testata+narrativa) e pag. 3 (KPI+grafico+tabella) invece
   di una sola pagina come v4 pag. 2. Non corretto in questo giro: la
   condizione «quando va in una pagina sola» dipende da quanto è lunga la
   narrativa, e serve una misura (`measure`), non un `if index > 0`
   incondizionato — rischio di introdurre un nuovo panic di overflow su
   testo lungo se affrontato senza tempo per verificarlo su tutte e tre le
   fixture più AMBIENTA.
4. **Le pagine di sezione con tabella previsionale (CE/SP/Flussi) mostrano
   il dettaglio completo, non una tabella di sintesi come v4 pag. 8–10.**
   `_forecast_table` (via `income_statement_forecast`/
   `balance_sheet_forecast`/`cashflow_sustainability`) mette la stessa
   tabella completa che finisce anche nell'Allegato corrispondente:
   corretta e non duplicata per contenuto, ma non è la sintesi a 9–10 righe
   che la v4 mostra sulla pagina di sezione (Ricavi/Costi operativi/EBITDA/…
   per il CE; Immobilizzazioni nette/Rimanenze/…/Totale attivo per lo SP).
   Costruire quella sintesi richiede scegliere quali subtotali del prospetto
   la rappresentano — non un dato che manca, ma una selezione che va decisa,
   non improvvisata in coda a questo giro.
5. **Tick duplicati su un grafico con tutti i valori a zero (o identici).**
   Riportato dal coordinatore prima di questo giro sulle anteprime S1/S2;
   letto nel codice (`charts.typ`, non modificato da me): con `lo == hi` il
   padding è fisso a ±1 unità di scala, e l'arrotondamento a zero decimali
   di un importo può portare due dei cinque tick (a ±0,5 dal centro) allo
   stesso intero stampato. Non ho trovato un grafico realmente a zero/valori
   identici su AMBIENTA per confermarlo dal vivo in questo giro; resta
   dichiarato, non verificato qui, non corretto (file non nel mio commit).

## Rischi residui

- `DATABASE_PATH` va impostato **prima** di qualunque `import` che tocchi
  `database.db` (anche indiretto, es. `from database.models import ...`):
  una volta importato il modulo lega l'engine al path visto in quel momento,
  e riassegnare la variabile d'ambiente dopo non ha alcun effetto nello
  stesso processo. Mi ha dato un `OperationalError: no such table` misto fra
  verifica sulle fixture e verifica su AMBIENTA nello stesso script; separati
  in processi distinti.
- Il gap #3 (narrativa reale + grafico → due pagine) è probabile che si
  presenti su **qualunque** scenario con un commento AI salvato prima di
  M2-02B: non è specifico di AMBIENTA. Vale la pena tracciarlo come task a
  parte prima che qualcuno lo scopra sul PDF finale di un cliente.
- L'override di Allegato E con nome di colonna grezzo (`ce02_override`,
  `sp16g`) resta un'etichetta leggibile solo per chi conosce lo schema: non
  blocca la generazione (a differenza del difetto principale corretto qui),
  ma è comunque un nome tecnico a schermo.
- Non ho verificato pagina per pagina l'intero documento AMBIENTA (53
  pagine): ho guardato le pagine indicate dal coordinatore più quelle del
  confronto v4 richiesto. Un difetto isolato su una pagina non ispezionata
  resta possibile.
