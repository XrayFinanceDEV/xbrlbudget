# 01 — Netting immobilizzazioni ↔ fondi ammortamento (sez-contrapposte)

Contesto: su route C, dopo la scelta del candidato (CoGe-LLM vs deterministico), `net_contra_accounts` (`importers/situazione_contabile_parser.py:2882`, chiamato da `pdf_importer.py:492-499`) ri-scansiona le pagine SP, classifica i fondi (immat/mat/svalutazioni/IVA), e **sovrascrive** `sp02_immob_immateriali`/`sp03_immob_materiali` con `anchor − fondi`. Due gate: netted > 1% del totale dichiarato E attivo scansionato ≈ dichiarato (0,5%). L'ancora dichiarata viene poi ridotta della massa nettata (i totali stampati sono LORDI).

I fix del 13-14/07 (non committati) hanno già risolto 343/348/405/210-split. L'audit del 14/07 su `Test/sez-contrapposte` trova **4 problemi residui**, in ordine di gravità.

---

## N1 — budget_395 (AGRIMIX): split immat/mat dei fondi perso — BUG SILENTE ⚠️ PRIORITÀ MASSIMA

**Sintomo.** Il file quadra (plug 0, nessun warning) ma:
- sp02 = 151.380,48 (lordo — dovrebbe essere **39.783,68**)
- sp03 = 1.750.893,35 (over-nettato — dovrebbe essere **1.862.490,15**)

Il documento ha: immat lorde `03` = 151.380,48 con `04 F/AMM IMMOB. IMMAT.` = 111.596,80; mat lorde `06` = 4.611.095,08 con `07 F/AMM IMMOB. MATERIALI` = 2.748.604,93. L'estrattore deterministico produce i netti GIUSTI; è `net_contra_accounts` a rovinarli.

**Causa radice (doppia).**
1. Le foglie dei fondi immateriali sono stampate con caption **abbreviate** ("F/AMM.LIC. D'USO SOF. A TEM. IND", "F/AMM.ALT. COS. AD UT. PLU. AMM", "F/AMM. LAV. STR. SU BENI DI TERZ", "F/AMM.COSTI IMPIANTO") che non matchano nessuna keyword di `_FONDO_IMMAT_KW` (`situazione_contabile_parser.py:2512`) → `_fondo_is_immat` (`:2520`) le bucketizza tutte come **materiali**.
2. La riga aggregata che risolverebbe tutto ("`04 F/AMM IMMOBILIZZAZIONI IMMAT.` 111.596,80") viene **eliminata da `_dedup_parent_child`** (`:2597` — i figli sommano al padre, quindi il padre è rimosso) PRIMA che `_reduce_fondi`/`_agg_or_sum` (`:2683-2707`) possano usarla come sub-aggregato immateriale → `fondi_immat = 0` e l'intera massa 2.860.201,73 netta sp03.

**Fix (come).** In `net_contra_accounts` / `_contra_classify`:
1. **Catturare gli aggregati PRE-dedup**: prima di chiamare `_dedup_parent_child`, salvare le righe che `_is_fondo_immat_aggregate` / `_is_fondo_aggregate` riconoscono come aggregati (es. "F/AMM IMMOBILIZZAZIONI IMMAT.", "F/AMM IMMOBILIZZAZIONI MATERIALI" — aggiungere pattern `F/AMM` accanto a `F.DO AMM`/`FONDI AMMORTAMENTO`). Se un aggregato immat esiste, usarlo come `fondi_immat` con autorità, e derivare `fondi_mat = totale_fondi − fondi_immat`.
2. **Bucketizzazione per gerarchia di codice** come fallback: se le foglie hanno codici figli di un mastro il cui caption è classificabile (es. tutte le `04.xxxx` sotto "04 F/AMM IMMOB. IMMAT."), ereditare il bucket dal padre invece che dalla descrizione della foglia. Questo rende lo split robusto a QUALSIASI abbreviazione futura, senza inseguire keyword.
3. Solo come terza linea: estendere `_FONDO_IMMAT_KW` con i token abbreviati ricorrenti (`SOF` software, `COSTI IMPIANTO`, `LAV. STR` lavori straordinari su beni di terzi, `UT. PLU` utilità pluriennale). Da solo NON basta — le abbreviazioni sono arbitrarie per gestionale.

**Guardia anti-regressione (fondamentale).** Aggiungere in coda a `net_contra_accounts` un **sanity check sul risultato**: se il candidato aveva già sp02/sp03 coerenti con `anchor − fondi_scan` per ENTRAMBI i bucket entro tolleranza, e l'overlay li cambierebbe spostando massa da un bucket all'altro **senza cambiare la somma**, preferire la versione con lo split confermato dagli aggregati stampati; se nessun aggregato è disponibile e lo split per-foglia è incerto (foglie non classificate > X% della massa fondi), **non applicare lo split** e limitarsi al netting della somma proporzionale ai valori già presenti nel candidato — che in questo file erano giusti.

**Verifica.** `tests/test_contra_netting.py`: nuovo caso budget_395 con attesi sp02=39.783,68 / sp03=1.862.490,15; regression su 343/348/405/210/211 (`tests/run_contra_regression.py`).

---

## N2 — budget_211 (Gustopronto): sp13 = utile invece di perdita (plug 111.401)

**Sintomo.** Netting corretto (sp02=182.260, sp03=122.967,10), ma il file dichiara **PERDITA D'ESERCIZIO 90.819,92** (pareggio 1.713.937,42 = attivo 1.623.117,50 + perdita; CE conferma: costi 1.301.420,37 − ricavi 1.210.600,45) mentre l'import produce sp13 = **+20.581,27** → plug 111.401,19 in sp09 e CE gonfiato da `enforce_ce_sp_identity`.

**Causa radice.** `_declared_control_totals` (`importers/pdf_extractor_llm.py:2160`, marker a `:2226`) legge anche il conto PATRIMONIALE "450.00090 RISULTATO D'ESERCIZIO 20.581,27" (risultato dell'esercizio PRECEDENTE, fermo in PN) tramite il marker generico `"risultato d'esercizio"`, e `_reconcile_trial_to_declared` (`:2269-2272`) fa vincere quel valore sulla perdita esplicita. È lo stesso failure mode che il parser per-segno evita con `_skip_declared_reconcile=True`; qui il file passa dal best-effort che non lo setta.

**Fix (come).** In `_reconcile_trial_to_declared` / `_declared_control_totals`:
1. Quando sono presenti SIA una riga "UTILE/PERDITA D'ESERCIZIO" esplicita SIA un generico "RISULTATO D'ESERCIZIO", **arbitrare col gap contabile**: il candidato giusto è quello per cui `attivo + (perdita) == pareggio dichiarato` (o `pareggio − attivo` combacia col segno). In budget_211 la perdita riconcilia ESATTAMENTE — l'arbitro è deterministico.
2. Secondo segnale d'arbitraggio: il risultato ricostruito dal CE (`_net_profit_from_ce`, `iv_cee_hierarchy.py:322`). Se CE dice −90.820 e uno dei due candidati coincide, vince quello.
3. Non rimuovere il marker "risultato d'esercizio" (serve su altri layout): declassarlo a candidato di ULTIMA scelta quando esiste un candidato che riconcilia col gap.

**Verifica.** Import budget_211 → sp13 = −90.819,92, plug → ~0, CE non alterato da `enforce_ce_sp_identity`. Regression: i file dove il marker "risultato d'esercizio" era il SOLO segnale devono continuare a funzionare (cercare nel corpus Test/ i file route C con quel marker).

---

## N3 — budget_210: l'overwrite `anchor − fondi` scarta massa misclassificata (plug 39.024)

**Sintomo.** Netting corretto (sp02=169.996,00 — include il f.do svalutazione marchi 33.340; sp03=100.363,91), ma resta un plug mascherato di 39.024 in sp09.

**Causa radice.** "108.00148 ANTICIPO X CANONI MACCHINARI" 39.000 (+24 di arrotondamenti) viene classificato in sp03 da `_classify_sp_attivo` (keyword "MACCHINARI") — ma è un **anticipo**, va nei crediti (sp06/sp07) o acconti su immobilizzazioni. L'overwrite `sp02/sp03 := anchor − fondi` (`situazione_contabile_parser.py:2999-3006`) butta via la massa extra parcheggiata in sp03 **senza ribucarla altrove** → il reconcile la re-inietta come plug in sp09.

**Fix (come).** Due interventi complementari:
1. **Classificatore**: in `_classify_sp_attivo` (`:489`) dare precedenza ai pattern `ANTICIP`/`ACCONT` sui pattern di categoria immobilizzazioni ("MACCHINARI", "IMPIANTI", "ATTREZZAT"…): `ANTICIPO A FORNITORI`/`ANTICIPI X`/`ACCONTI` → crediti (sp06g) o, se il contesto è immobilizzazioni ("immobilizzazioni in corso e acconti"), sp03 legittimamente — distinguere con la presenza di "CANONI"/"FORNITOR" → credito.
2. **Semantica di overwrite conservativa**: in `net_contra_accounts`, quando `candidato.sp0X > anchor_sp0X`, la differenza (massa extra che l'overlay sta per scartare) NON deve sparire: **ribucarla in sp06g/altri crediti** (o mantenerla dove il classificatore del candidato l'aveva messa, se diverso da sp02/sp03) e loggarla. Così l'overwrite corregge il netting senza distruggere massa, e il plug scende a ~0 anche se il classificatore sbaglia.

**Verifica.** budget_210 → plug ≤ 24 € (solo arrotondamenti), sp02/sp03 invariati rispetto a oggi (già corretti), 39.000 in crediti. Test in `tests/test_contra_netting.py`.

---

## N4 — budget_405: residuo attivo non classificato 870.467 (11%, non è colpa del netting)

**Sintomo.** Netting ESATTO (sp02=0,61; sp03=5.756.144,64) ma `QUADRATURA MASCHERATA` con plug 870.467.

**Causa radice.** Il best-effort non classifica alcune masse; tra le identificate:
- `F.DO SVAL.CREDITI ENTRO 12 MESI` 28.478,16 (fondo svalutazione crediti in presentazione lorda → va nettato sui crediti, come già avviene per i fondi ammortamento)
- `RISCONTI PASSIVI PLURIENNALI` 4.238.122,10 (→ sp18/ratei e risconti passivi; l'alias "PLURIENNALI" non è riconosciuto)

**Fix (come).**
1. Aggiungere alias in `data/iv_cee_tree.json` (nodo ratei/risconti passivi: `RISCONTI PASSIVI PLURIENNALI`, `RISCONTI PLURIENNALI`) e/o regola in `_classify_sp_passivo` (`situazione_contabile_parser.py:497`).
2. Estendere il netting crediti: `F.DO SVAL.CREDITI`/`FONDO SVALUTAZIONE CREDITI` con qualificatori temporali ("ENTRO 12 MESI", "OLTRE") → nettare su sp06/sp07 rispettivamente (oggi `_contra_classify` gestisce la svalutazione crediti solo nella forma base).
3. Dopo i due fix, rilanciare: il plug residuo dirà se c'è altra massa non classificata (iterare finché plug < 1%).

**Verifica.** budget_405 → plug sotto soglia masking (idealmente < 1%); nessuna regressione su 343/348.

---

## N5 — budget_131 (Oprandi): parser DEPI non legge il layout a 3 colonne saldo

Non è un problema di netting (il documento non ha fondi), ma sta nella stessa cartella ed è il caso peggiore di **sotto-estrazione**: attivo estratto 230.205,93 vs 355.878,76 reale (plug 54,6% in produzione; l'harness lo dava "SI" perché non fa il reconcile).

**Causa.** Layout DEPI `XX/YYYY` con **3 colonne di saldo** (30/04/26, 30/04/25, 30/04/24) + colonne %: il sub-parser DEPI (`parse_entries_contrapposte_depi`, `:1643`) assume una colonna saldo sola → righe perse e valori mischiati tra esercizi (sp02=0 invece di 8.069,50; sp03=8.992,37 invece di 126.595,70).

**Fix (come).** In `parse_entries_contrapposte_depi`:
1. Rilevare l'intestazione multi-data (regex su ≥2 date `\d{2}/\d{2}/\d{2,4}` nella riga header) e determinare la colonna target = data più recente (o quella coerente con `fiscal_year` passato all'import).
2. Estrarre i saldi per **coordinata x della colonna** (come già fanno i parser contrapposte-8digit e per-segno), non per posizione ordinale dei numeri nella riga — le colonne % altrimenti inquinano il parsing.
3. Bonus: la 2ª colonna è l'esercizio precedente → può popolare `prior_bs_data` (oggi route C è single-year).

**Verifica.** budget_131 → attivo 355.878,76, sp02=8.069,50, sp03=126.595,70, plug ~0. Regression sugli altri DEPI del corpus (memoria: budget_281 flat-DEPI, 131 stesso, XX/YYYY).

---

## N6 — budget_337: text layer corrotto — approccio corretto (il fix vision è stato revertato)

**Storia.** Il 14/07 era stato tentato detector `_text_layer_is_corrupted` + fallback vision + override overlay: **revertato lo stesso giorno** perché rompeva la quadratura (l'override ALZA l'attivo mentre il modello netting lo ABBASSA). Su disco non c'è nulla — corretto così.

**Approccio giusto (da implementare).** Il problema reale in produzione è che il **CoGe-LLM netta gli ammortamenti di CE** (conti 826xxx, "AMM.TO …") **sulle immobilizzazioni SP**. Intervento su `extract_trial_balance_with_llm` (`importers/pdf_extractor_llm.py:2000`):
1. **Prompt** (`TRIAL_BALANCE_SP_SYSTEM_PROMPT`): esplicitare che i conti di ammortamento di COMPETENZA (CE, es. 82xxxx "AMMORTAMENTO/AMM.TO") NON sono fondi e non vanno sottratti dalle immobilizzazioni; solo i conti FONDO (patrimoniali) nettano.
2. **Post-processing deterministico**: cross-check — se l'output LLM ha sp02/sp03 inferiori a quelli ricostruibili dal testo (immobilizzazioni − soli conti FONDO), correggere con i valori deterministici. `net_contra_accounts` già fornisce lo scan; basta applicarlo anche quando il vincitore è il CoGe-LLM (già avviene) MA con gli anchor lordi corretti.
3. Il caso "text layer corrotto" resta un fallimento onesto: senza chiave API il deterministico estrae il 10% e fallisce dichiaratamente; con chiave la via vision è già usata per gli scansionati. Un eventuale detector di corruzione (rapporto token garbled) può instradare a vision, ma va testato che NON re-introduca il conflitto override/netting: la via vision deve produrre l'estrazione COMPLETA, non un patch parziale sull'estrazione testuale.

**Verifica.** budget_337 → immateriali 3.239 (non 680) via percorso LLM/vision; nessun cambiamento sui file con text layer sano.

---

## Ordine consigliato

N1 (silente, valori sbagliati senza warning) → N2 (segno del risultato) → N3 (plug 39k) → N4 (alias) → N5 (parser DEPI multi-colonna) → N6 (LLM/vision).

Prima di tutto: **committare i fix non committati** (vedi 05-ROADMAP.md, T0) — N1..N4 si costruiscono sopra quel diff.
