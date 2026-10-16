# Passaggio di consegne — import PDF "tutto su snello", 2026-10-16

Lavoro **non committato** sul branch `fix/import-pdf-strada-corta-2026-10-16` (base `b141809`).
Questa cartella contiene tutto ciò che serve per finirlo: le copie dei sei subagenti con i loro
diff, gli strumenti di misura e i risultati di riferimento. La cartella temporanea della sessione
non serve più.

## 1. Obiettivo e vincoli (dal proprietario)

- **Tutti i PDF sul percorso snello**: prima i lettori a regole (zero chiamate di modello), solo
  dopo il modello.
- **Regole generali**, valide per ogni gestionale, mai legate a un file, a una ragione sociale o a
  un importo. Il **totale stampato decide**: meglio un rifiuto che un numero sbagliato che quadra.
- **Mai Anthropic** (Haiku, Sonnet), nemmeno come ripiego: se gx10 manca o fallisce, la fase si
  salta e si segnala. **gx10 (Qwen) e MinerU sono ammessi** perché locali.
- Mai commit, merge o push senza un sì esplicito.

## 2. Fatto (nel working tree, non committato)

| Area | File | Cosa |
|---|---|---|
| Snello di default | `importers/pdf_importer.py` (`_motore_snello`) | `IMPORT_MOTORE` assente = snello; `classico` (o un altro valore) = importatore di prima |
| Niente Anthropic | `importers/llm_provider.py` | `anthropic_consentito()` (solo con `ANTHROPIC_CONSENTITO=1`), `chiave_anthropic()` (vuota senza consenso), `vieta_anthropic(fase)` / `AnthropicVietato`; provider di default = gx10 |
| | `backend/app/main.py` | la chiave Anthropic va in `os.environ` solo con consenso, altrimenti viene tolta |
| | `pdf_extractor_llm.py`, `macro_analysis.py`, `detail_enrichment.py`, `ledger_evidence.py`, `vision_rescue.py`, `struttura_documento/mappa.py` | lettura della chiave via `chiave_anthropic()`; `vieta_anthropic()` prima di ogni `anthropic.Anthropic(...)` |
| | `pdf_importer.py` (`_modello_non_disponibile`) | il messaggio all'utente dice la verità: «richiederebbe Anthropic, non consentito» oppure «gx10 non configurato» |
| Struttura su gx10 | `struttura_documento/mappa.py` (`mappa_pagina_gx10`) | la mappa vision dello snello usa gx10 senza consenso Anthropic |
| Più lettori nello snello | `import_snello/deterministico.py` | `tentativo()` = lettori di sempre, poi `_prova_fonti` (prove incrociate deterministiche) e `_prova_schema_generico`, **dopo**, quindi i file già adottati non cambiano |
| | `source_reconciliation.py` | `extract_deterministic_source_candidates` (come `extract_source_candidates` senza il ledger, che chiama un modello) |
| | `import_snello/__init__.py` | `_MODO_DA_PARSER`: `schema_legge_generico`, `fonti_legge`, `fonti_ago` |
| Lettore generico | `importers/schema_legge_generico.py` (nuovo) | schema di legge di qualunque gestionale → cuore di `xbrl_reso_parser`; oggi adotta solo 597 |
| | `importers/xbrl_reso_parser.py` | estratto `estrai_da_righe` (cuore comune); `eredita_dal_padre`; tolleranza `_TOLLERANZA`/`_diversi` (0 per il reso XBRL, 5 € solo per documenti a importi interi nel generico) |
| Situazioni contabili | `importers/situazione_contabile_parser.py` | fuse le regole dei subagenti E ed F (sotto), regressione 0 su 31 |
| Test | `tests/conftest.py` (nuovo) | la suite gira con `ANTHROPIC_CONSENTITO=1` e `IMPORT_MOTORE=classico` (i test descrivono quel comportamento) |
| | `tests/test_default_snello_senza_anthropic.py` (nuovo) | 8 test sui default nuovi |
| | `tests/test_snello_innesto.py` | il riferimento «interruttore non snello» è ora `classico` |
| | `tests/_ground_truth_sez_contrapposte.json` | 405: ora `quadra: true`, `plug_max: 1` (sp02/sp03 di riferimento invariati) |

### Regole fuse nel parser delle situazioni contabili (E + F)
- **E-R1** separatore delle colonne: le parole entro 2 pt dalla colonna dei codici di destra
  appartengono a quella (620/621: i ricavi finivano tra i costi).
- **E-R2** il token `TOTALE` chiude il conto in corso (piè di pagina, budget_612).
- **E-R4** «utile/perdita in corso di formazione» = risultato del periodo.
- **E-R5** descrizioni dell'attivo: `SPESE+PLURIENN`, `DA AMMORTIZZ`, `DISAGG` → sp02; `CONTENITOR` → sp03.
- **Divisione della pagina SP+CE** (`_be_split_sp_ce_page`, unione di E-R3 e F-3): si divide al
  titolo «CONTO ECONOMICO» a inizio riga se sopra lo SP ha chiuso **oppure** c'è il titolo
  «STATO/SITUAZIONE PATRIMONIALE» a inizio riga.
- **F-1** sinonimi CE solo come ultima risorsa (`_classify_ce_sinonimo`): LAVORO NON, MANO
  D'OPERA, COSTI DI FABBRICA, PROMOZIONALI, CENTRO ELETTRONICO, VENDITE, PROFITTI VARI…
- **F-2** fondo immateriale orfano: le «spese manut./riparaz./ammodern.» all'attivo vanno da sp06 a sp02.
- **F-4** `_passivo_parts` scende nei figli quando un mastro del passivo è un fondo, un cespite o
  una testa di crediti, e i figli lo ricostruiscono al centesimo.
- **F-5** lato costi/ricavi della ricostruzione gerarchica deciso dal conteggio delle descrizioni.

## 3. Numeri

- Misura su `Test/`: 249 PDF, **161 unici**.
- Prima: 96 adottati a regole dallo snello. Dopo le prove incrociate e il generico (597): **106**,
  con 0 valori cambiati e 0 chiamate di rete (`risultati/baseline.jsonl` contro `risultati/dopo_v1.jsonl`).
- Le regole sulle situazioni contabili aggiungono 229, 243, 367, 405, 588, 696, 697, 702, 703 →
  **~115 attesi, misura completa NON rifatta**.
- Test: la suite di riferimento **prima** delle modifiche al provider aveva **38 fallimenti
  preesistenti** (25 toolchain Typst, 7 grafici Typst, `test_vision_rescue::…ricavo_sconosciuto…`, altri
  d'ambiente: `risultati/fail_baseline.txt`). Dopo le modifiche è stata rifatta solo sui moduli
  toccati: 0 fallimenti nuovi. **La suite completa va rifatta.**

## 4. Da finire, in ordine

### 4.1 Fondere i quattro lettori generici → `importers/schema_legge_generico.py`
Le quattro copie partono tutte dal file attuale del repository; ogni `copie/gen_X.diff` si applica
e lo riproduce esattamente (verificato).

| Copia | Adotta (dei 31) | Regole chiave |
|---|---|---|
| `gen_A` | 585 586 413 597 341 257 265 115 683 | `\)(?=[A-Za-z])` (parentesi attaccata), `_totali_senza_didascalia`, `_totale_di`, `_radici_dettaglio` (dettaglio su due piani), sezione con totale sul titolo, lettera ripetuta = dettaglio, trattino a capo, `_totali_di_sezione_ce`, `_imposte_come_totale`, `_segni_come_contributo` (seconda lettura coi costi stampati negativi) |
| `gen_B` | 597 298 171 314 253 297 sangae6 | `_scadenza_in_coda` (debito «oltre» → sp17), `_testate_ripetute`, didascalia a sandwich, `_togli_dettaglio_conti` generalizzata (`_scompone`, `_corsa_dettaglio`: mastri OPPURE foglie, segno opposto), `_tolleranza_dettaglio`, `_togli_scadenze_di_testa`, `_scadenze_con_totale`, `_ce_a_segno_algebrico`, risultato nel PN senza IX |
| `gen_C` | 597 382 | `_RE_CODICE_VOCE` (codice voce TeamSystem), titolo di sezione con lettera, totale con codice e parentesi, `_RE_FORMULA_PRIMA_IMPOSTE`, a capo dalla geometria (0,7 dell'interlinea), colonne del documento intero, colonna interna = stesso esercizio, riga di soli importi = totale del gruppo |
| `gen_D` | 585 586 594 597 638 315 341 253 | `_TRABOCCATO` (`****`), `_margine_ripetuto`, colonna che prosegue, `_parziali`, nomi dei totali, perdita ripianata ≠ utile, raggruppamento intatto, sotto-lettera numerata, numerazione che non torna indietro, `_compone` (dettaglio con segni), totale senza didascalia, titolo a zero, `_sezioni_vuote`, formula ≠ codice conto, anni di colonna |
| `gen_M` (fusione **parziale**, interrotta) | 14: 585 586 594 597 638 315 298 341 171 257 265 253 683 297 | base gen_D + parte di A/B/C. **Mancano 382, 413, 115, sangae6** (rifiuti in `risultati/` qui sopra non salvati: rilanciare `prova_copia.py copie/gen_M.py`) |

**Obiettivo dell'unione**: 585 586 594 597 638 315 341 253 257 265 413 115 683 298 171 297 sangae6
382 (18). **Rifiuti giusti da mantenere**: 289 e 695 (attivo ≠ passivo stampati), 665
(totale stampato 0 contro una riga da 2.293), 672 e 161 (simulazioni che si contraddicono),
355 (tutto a zero), 150, 133, 135, 137, 138 (artefatti AI), 152 (altro formato: schema etichette),
**314** (vedi B-13).

**Come fondere**: dove due copie risolvono lo stesso problema, tenere **una** sola implementazione,
la più generale. Casi noti:
- righe di soli importi: A-2, C-9, D-11, B-6;
- colonna interna / parziali: C-8, D-4;
- segno dei costi: A-12, B-11;
- «Totale attivo circolante» ≠ «Totale attivo»;
- raggruppamento «c), d), e)»;
- numerazione che torna indietro.

Per ogni file adottato confrontare i valori bs/ce con la copia che lo adottava: devono coincidere.

**Escludere B-13** («colonna corrente tutta a zero → usa la seconda colonna»): salverebbe i numeri
di un anno sotto l'anno scelto dall'utente. Deve restare un rifiuto.

**Due proposte di D sul cuore `xbrl_reso_parser.py`**, da valutare: toccano anche il lettore XBRL,
che oggi adotta 43 file. Da applicare solo se la misura su quei 43 non cambia.
- `_RESTO_RAGGRUPPAMENTO["CE.C.16"] = "ce14"` (resto di un raggruppamento «b), c)» sotto 16).
- In `_controlli_documento` il controllo `stampato_utile` solo se `"imposte" in stampati` (638 anno precedente).

**Ancora da fare nel generico**: dopo `estrai_da_righe` rinominare il marcatore `_source_xbrl_reso`
in `_source_schema_legge_generico`, perché oggi il generico eredita quello del reso XBRL.

### 4.2 Misura completa, regressioni e suite
```bash
cd C:\DEV\xbrlbudget-main\xbrlbudget
PY=backend/.venv/Scripts/python.exe
H=docs/import/handoff-2026-10-16
# snello deterministico su tutti i 161 (scrive in $H/strumenti/<nome>.jsonl)
$PY -I $H/strumenti/snello_driver.py dopo_v2.jsonl
# confronto: PERSI e VALORI CAMBIATI devono essere vuoti (o motivati: vedi 4.3)
$PY -I $H/strumenti/confronta.py $H/risultati/baseline.jsonl $H/strumenti/dopo_v2.jsonl
# lettore generico su una copia, sui 31 schemi di legge
$PY -I $H/strumenti/prova_copia.py <copia.py> [id ...]
$PY -I $H/strumenti/vedi_copia.py <copia.py> <id>          # righe come le vede il lettore
$PY -I $H/strumenti/righe_dump.py "<pdf>" [pagine]           # righe fisiche del PDF
# parser situazioni contabili su una copia + regressione sui 31 che chiudono
$PY -I $H/strumenti/prova_sc_copia.py <copia.py> <id ...>
$PY -I $H/strumenti/prova_sc_copia.py <copia.py> --regressione
# suite completa (~11 min, 3.238 test); confrontare con risultati/fail_baseline.txt
env -u ANTHROPIC_API_KEY -u GX10_API_KEY $PY -m pytest -p no:cacheprovider tests -q -rf
```
Tutti gli script bloccano la rete (socket) e tolgono le chiavi: nessuna chiamata possibile.

### 4.3 Decisioni del proprietario (proposte pronte, non applicate)
1. **338**: «ATTREZZATURE INDUSTR.E COMMERCIALI» (241.128,49) è contata due volte, come debito
   fornitori (sp16d) e come cespite non nettato (sp03). La regola F-4 applicata anche a
   `classify_passivo` corregge: attivo 3.558.373,54 = stampato 5.018.120,08 − fondi 1.363.182,56 −
   fondo svalutazione crediti 96.563,98. Diff in `copie/sc_F_338.diff`. Cambia un file oggi «OK».
2. **Sinonimi CE ovunque**, non solo come ultima risorsa: correggono 9 file oggi OK (188, 213, 215,
   210, 249, 281, 337, 373, 374).
   - «MERCI C/VENDITE», «CONTO VENDITE», «VENDITE PRODOTTI» oggi vanno in ce04 invece di ce01:
     213 e 215 hanno ce01 a 12k invece di 1,1M.
   - La pubblicità va in ce12 invece di ce06.
   - 210: «SPESE MANUTENZ.STRAORDINARIA» va in sp06 invece di sp02.
   - Non c'è un diff pronto: va rifatto partendo da F-1 senza la condizione «solo ultima risorsa».
3. **Clamp silenzioso in `build_iv_cee`** (`max(0, gross − depr)`): un fondo più grande del suo lordo
   viene azzerato senza avviso. Dichiararlo come `_unclassified_mass`, come `build_sp_from_vision`.
4. **Commenti AI dei report** (`backend/app/services/ai_comments_service.py`,
   `editorial_notes_service.py`): leggono la chiave dalle impostazioni e usano ancora Anthropic.
   Spegnerli o portarli su gx10?
5. **Conti disegnati come grafica** (618, 619, 620, 621, 624: mastri e importi vettoriali, verificati
   con `get_drawings`): dal testo non si recuperano; serve il passaggio da MinerU (locale).
6. **Produzione**: con questi default, un server Jenkins che non configura gx10 non ripiega più su
   Haiku. Gli import che servirebbero al modello falliscono con il messaggio di
   `_modello_non_disponibile`. Configurare `PDF_LLM_PROVIDER_*`/`GX10_*` (già documentato in
   `docs/deployment/PRODUCTION_CONFIG.md`) oppure `ANTHROPIC_CONSENTITO=1`.

### 4.4 Documentazione da riallineare dopo il merge
- CLAUDE.md: «Percorso snello (`IMPORT_MOTORE=snello`)» e «PDF = PyMuPDF + LLM (Anthropic by
  default…)»: ora snello e gx10 sono i default.
- `docs/deployment/PRODUCTION_CONFIG.md` §«Percorso snello» (`STRUTTURA_MODEL`: la struttura non è
  più solo Anthropic), README (tabella env), `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §10.
- `docs/import/IMPORT-PDF-STRADA-LUNGA.md`: aggiungere la misura e le famiglie risolte.
- `C:\DEV\xbrlbudget-main\avvia-backend.ps1` (fuori dal repo): niente da cambiare. I default
  coincidono già: le `PDF_LLM_PROVIDER_*=gx10` sono ridondanti ma innocue.

## 5. Avvertenze operative
- Nel tool Bash gli heredoc con `\\b` diventano un backspace (`\x08`) nei file Python: modificare con
  l'editor, non con sostituzioni da script.
- `uvicorn --reload` non ricarica `importers/`: dopo ogni modifica va riavviato il backend.
- I `.jsonl` in `risultati/` sono le fotografie per il confronto: `baseline.jsonl` = snello
  deterministico **prima** di qualunque modifica; `dopo_v1.jsonl` = dopo prove incrociate e generico
  (597), **prima** del merge E+F; `regole_risultati.jsonl` = analisi «strada corta/lunga» del vecchio
  importatore.

## 6. Contenuto della cartella
- `copie/`: gen_A–D e gen_M (lettore generico) con i diff; `sc_E.diff` e `sc_F.diff` (già applicati
  al parser delle situazioni contabili); `sc_F_338.diff` (proposta 4.3.1).
- `strumenti/`: script di misura e di prova (vedi 4.2).
- `risultati/`: fotografie jsonl, `pytest_baseline.txt` e `fail_baseline.txt` (suite prima delle
  modifiche ai provider), `run_A_final.txt`.
