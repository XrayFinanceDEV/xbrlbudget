# 02 — Perdita e fusione di voci durante lo spacchettamento

Il problema segnalato: "perdita di informazioni o voci durante lo spacchettamento, andando a volte ad unire due voci in una generale". L'audit ha individuato **10 punti** dove questo accade, con il rimedio per ciascuno. Ordinati per impatto.

---

## V1 — Plug residuo in sp09/sp16 (best-effort contrapposte): la massa non classificata perde identità

**Dove.** `importers/situazione_contabile_parser.py:3456-3468`: `res_a = iv_total − att_sum` → sp09 (liquidità); `res_p` → sp16 (debiti breve). Righe `:3474-3490`: variante senza totale dichiarato (ancora al lato maggiore, plugga l'altro — perdita di composizione ancora più probabile).

**Effetto.** Ogni conto non riconosciuto per descrizione finisce fuso in "liquidità" o "altri debiti". Il flag `_plug_residual`/`QUADRATURA MASCHERATA` esiste (bene), ma l'utente in Rettifiche non sa QUALI conti compongono il plug.

**Fix.**
1. **Tracciare la composizione del plug**: accumulare le righe non classificate (descrizione + importo + lato) in una lista `_plug_detail` sul dict risultato, propagarla nel result dell'import e mostrarla nel messaggio/warning (o in un campo dedicato consultabile da Rettifiche). Costo basso, beneficio alto: trasforma "plug 870.467" in "RISCONTI PASSIVI PLURIENNALI 4.238.122, F.DO SVAL.CREDITI 28.478, …".
2. **Ridurre il plug a monte** ampliando gli alias (V2) — il plug diventa l'eccezione, non la regola.

## V2 — Alias insufficienti in `data/iv_cee_tree.json` / classificatori per descrizione

**Dove.** `iv_cee_hierarchy.resolve()` (`:112`) è volutamente conservativo (None quando incerto). I classificatori hardcoded (`_classify_sp_attivo:489`, `_classify_sp_passivo:497`, `_debt_type:578`) coprono i pattern visti finora.

**Effetto.** Ogni descrizione fuori vocabolario → plug (V1) o bucket "altri". Casi concreti trovati: `RISCONTI PASSIVI PLURIENNALI`, `F.DO SVAL.CREDITI ENTRO 12 MESI`, `ANTICIPO X CANONI MACCHINARI` (misclassificato), caption abbreviate `F/AMM.*` (vedi 01-N1).

**Fix (processo, non one-shot).**
1. Strumento di raccolta: script `Test/_unclassified_report.py` che gira il corpus Test/ completo e produce la lista (descrizione, frequenza, importo medio, file) delle righe finite nel plug o in bucket generici. Da rilanciare dopo ogni batch di alias.
2. Alimentare `iv_cee_tree.json.aliases` con i pattern raccolti (una PR di soli dati, a basso rischio).
3. Regola di priorità nei classificatori: pattern di FUNZIONE (`ANTICIP`, `ACCONT`, `F.DO`, `FONDO SVAL`) battono pattern di CATEGORIA (`MACCHINARI`, `IMPIANTI`) — è l'errore di budget_210.

## V3 — Fusione debiti in "altri" (many-to-one)

**Dove.** `situazione_contabile_parser.py:3381-3382`: tag passivo inatteso → `add(bs,'sp16', amt)` aggregato → UI rende tutto come "Altri debiti". Il typed-split (`:3376-3380` + `_debt_type`) mitiga ma il fallback resta aggregante.

**Fix.** Quando `_debt_type` non risolve, emettere comunque `sp16g_altri` (typed esplicito) invece dell'aggregato nudo, e accodare la descrizione a `_plug_detail` (V1) così la voce originale resta ispezionabile. Valutare 2-3 tipi mancanti ricorrenti dal report V2 (es. acconti da clienti → sp16-acconti se il dato c'è).

## V4 — Route B: sottoconti scartati per design, senza recupero se il totale di voce è mal letto

**Dove.** Design documentato (`docs/import/IMPORT-ROUTING-TAXONOMY.md` §2/§4.4): in route B l'LLM ancora sui totali di voce, i sottoconti CoGe sono ignorati.

**Rischio.** Se il totale di voce è mal letto (OCR, riga spezzata), il dettaglio che permetterebbe di ricostruirlo è stato buttato.

**Fix (cross-check, non cambio di design).** Post-estrazione route B: ricostruire deterministicamente la somma dei sottoconti per le voci che hanno dettagli visibili e confrontarla col totale di voce estratto; se divergono oltre soglia (es. 1%), preferire la somma dei sottoconti o almeno flaggare la voce nel warning. Implementabile come passo in `pdf_extractor_llm` accanto ai validatori esistenti (`_validate_crediti` `:2427` fa già questo pattern per i crediti — generalizzarlo a immobilizzazioni e debiti).

## V5 — Reconciler PN/personale no-op quando il gate non riconcilia

**Dove.** `_reconcile_pn_detail` (`pdf_extractor_llm.py:1619`) e `_reconcile_personale_detail` (`:1653`): recuperano riserve negative A.VIII e split salari/oneri/TFR, ma SOLO se il totale di controllo stampato riconcilia (anti-masking, giusto).

**Effetto.** Su file dove il totale stampato non è leggibile (riga spezzata, OCR), la riserva negativa resta persa → PN gonfiato → mascherato in cassa (classe LIO 2025).

**Fix.** Quando il gate fallisce, non applicare (corretto) ma **loggare il fallimento del gate** nel result (`_pn_reconcile_gate_failed=True` + valori letti), così i casi diventano visibili nel corpus invece di silenziosi. Poi valutare un secondo anchor: "Totale patrimonio netto" ricostruito da `attivo − passività` quando il pareggio è affidabile.

## V6 — Colonna LLM malformata: una colonna intera può azzerarsi

**Dove.** `pdf_extractor_llm.py` ~`:85-142` (`_coerce_year_blob`): ripara colonne serializzate come stringa; se il retry di parsing fallisce, la colonna va persa.

**Fix.** Se `_coerce_year_blob` fallisce definitivamente su `current_year`, fallire l'estrazione (retry della chiamata LLM una volta) invece di proseguire con la colonna azzerata — oggi il rischio è importare un anno VUOTO che poi pare "quadrato a zero" (mitigato da `is_empty` in `check_quadratura`, ma meglio non arrivarci). Su `prior_year`: proseguire senza anno precedente (già gestito).

## V7 — Windowing pagine SP/CE: troncamenti

**Dove.** `find_section_pages` (`pdf_extractor_llm.py:234`) + `SP_END_KEYWORDS`. Già indurito (broad end-anchors, zeroed-leading-section guard).

**Fix residuo.** Telemetria: loggare sempre `(sp_pages, ce_pages, amount_mass_per_page)` nel result import per diagnosi rapida dei prossimi casi; nessun cambio di logica finché non emergono nuovi troncamenti.

## V8 — `_reconcile_trial_to_declared` sposta massa su un totale dichiarato potenzialmente mal letto

**Dove.** `pdf_extractor_llm.py:2235` (plug verso il dichiarato, righe 2302-2318 accumulano in `_plug_residual`).

**Fix.** Validare il totale dichiarato con un secondo segnale prima di usarlo come ancora: coerenza tra pareggio/attivo/passivo letti (`_declared_control_totals` ne legge fino a 3 — se 2 su 3 concordano, ok; se il dichiarato è singolo e diverge > 20% dalla somma estratta, NON ancorare e lasciare il fallimento onesto). Collegato a 01-N2 (arbitraggio utile/perdita).

## V9 — `_strip_result`: righe risultato rimosse per pattern ambiguo

**Dove.** `situazione_contabile_parser.py:3340-3348`: righe con "ESERCIZIO"+"UTILE/PERDITA/RISULTATO" tolte dai lati e sommate al risultato.

**Rischio.** Descrizioni tipo "UTILI ESERCIZI PRECEDENTI" o "PERDITE ESERCIZI PRECEDENTI PORTATE A NUOVO" potrebbero matchare → riserve scambiate per risultato d'esercizio.

**Fix.** Escludere esplicitamente i pattern `PRECEDENT`/`PORTAT.* A NUOVO`/`PREGRESS` dallo strip (→ sp12g), e aggiungere test con quelle descrizioni. Verificare nel corpus se il caso si è già presentato (grep sugli output del report V2).

## V10 — `_reduce_debts` distorce lo split tipizzato

**Dove.** `situazione_contabile_parser.py:2855`: dopo il netting rimuove l'eccesso passivo dai bucket debiti **in ordine fisso**.

**Fix.** Rimozione **proporzionale** alla dimensione dei bucket (o con priorità: prima il bucket dove il fondo era stato erroneamente classificato, se noto dallo scan), così lo split fornitori/banche/tributari resta rappresentativo. Test: file con fondi in passivo e debiti tipizzati (budget_343/348 hanno il caso).

---

## Nota sul TODO esplicito

`importers/pdf_importer.py:814` — `"format": "micro"  # TODO: Detect format from PDF`: il formato bilancio è hardcoded. Fix banale (il classifier ha già i segnali per Ordinario/Abbreviato/Micro) ma a bassa priorità: il campo oggi è informativo.
