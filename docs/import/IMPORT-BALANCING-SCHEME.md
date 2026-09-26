# Schema generale di estrazione e quadratura (per rotta)

> Scopo: un UNICO schema a **livelli di dettaglio crescenti**, valido per ogni bilancio
> importabile (presente e futuro), che NON contiene regole per-singolo-file. Ogni file
> entra dalla sua **rotta** (L0) e viene quadrato risalendo i livelli L1→L5.
> Documento di accompagnamento a `IMPORT-ROUTING-TAXONOMY.md` (che copre il routing).
> Le sezioni storiche su estrazione e quadratura vanno lette insieme alla
> [serie corrente](REGOLE-IMPORT-00-INDICE.md). I pass CE↔SP e IV-CEE qui sotto
> descrivono il comportamento attuale, senza i vecchi plug.

## L0 — Rotta (macro-area)  ·  `bilancio_classifier.classify_bilancio`
Determinata PRIMA dell'estrazione, sul testo delle prime 14 pagine. Invariata.

| Rotta | Cosa | Estrazione |
|---|---|---|
| **A/B** IV-CEE | schema di legge (con o senza sottoconti) | LLM IV-CEE (`extract_pdf_with_llm`) |
| **C** verifica/situazione contabile | elenco conti CoGe Dare/Avere o Saldo | **LLM CoGe** (`extract_trial_balance_with_llm`) → deterministico (fallback) |
| **OTHER** | `.xbrl` nativo | parser XBRL |
| **UNSUPPORTED** | solo CE / non-bilancio | **errore onesto**, mai un plug silenzioso |

Regola onestà L0 (nuova): un documento con contenuto economico ma **senza alcun marker
patrimoniale** (`ce_present and not sp_present`) è solo-CE → UNSUPPORTED, non un finto
"bilancio non quadra". (Es. un export del solo Conto Economico con un "TOTALE A PAREGGIO"
che è il pareggio del CE = totale ricavi.)

Regola onestà al gate finale (`pdf_importer._is_aggregated_summary`): al fallimento di
`validate_balance`, un documento SENZA sottostruttura IV-CEE (niente romani, niente "esigibili
entro/oltre", niente codici conto) — un riepilogo over-aggregato / generato da AI, NON uno schema
art. 2424/2425 (budget_133/135/137/150) — solleva un chiaro **"Formato non supportato"** invece del
criptico "does not balance". Gated sul fallimento del bilancio, quindi non può mai riclassificare un
file che importa.

## L1 — Pareggio (identità di base)
`Attivo == Passivo + PN`. Il **risultato d'esercizio** (sp13) è il *gap* quando non è
stampato esplicitamente. Nelle verifiche CoGe questo è imposto da
`_balance_trial_via_result` (sp13 assorbe la differenza).

> **TRAPPOLA**: forzare il pareggio via sp13 NON garantisce la correttezza. Se l'estrattore
> perde dei conti su un lato, il pareggio regge ma sp13 diventa un **utile/perdita finto**.
> "Quadra" ≠ "corretto". → serve L2.

## L2 — Riconciliazione ai totali DICHIARATI (anti-masking) ★ livello chiave
Ogni verifica stampa i propri **totali di controllo**: `TOTALE A PAREGGIO`, `TOTALE
ATTIVITA'/PASSIVITA'`, e di norma un `UTILE/PERDITA D'ESERCIZIO` esplicito. Sono la verità.

- `_declared_control_totals(file_path)` li legge (robusto a header lettera-spaziati e numeri
  italiani).
- `_reconcile_trial_to_declared()`: confronta `sp13` col **risultato dichiarato** e registra
  gli scarti diagnostici. Non sposta massa in `sp16`/`sp09` e non forza `sp13`. Può recuperare
  un `sp13` omesso solo quando risultato stampato, CE e gap dello SP concordano entro 2 €.
- `check_quadratura` legge `_plug_residual` e alza `masked=True` (>1% del totale) →
  warning "QUADRATURA MASCHERATA … correggere in Rettifiche".

L'incompletezza di composizione è dichiarata; la riconciliazione non garantisce il pareggio.

## L2-bis — Diagnostica CE ↔ SP (PDF)
`enforce_ce_sp_identity` è chiamato nel percorso PDF, dopo l'estrazione e prima della
validazione. Confronta l'utile ricostruito dal CE con `sp13`; oltre la tolleranza
`max(2 €; 0,1% di |sp13|)` espone `_ce_sp_difference` e un warning. Se è disponibile un
risultato stampato, espone anche gli scarti di CE e SP rispetto a quel valore. I parametri
`prefer` e `declared` restano nella firma per compatibilità, ma **non modificano** CE, SP,
`ce04`, `ce12` o riserve. Il percorso XBRL nativo usa il proprio `check_quadratura` e non
chiama questa funzione.

## L3 — Segno e lato
La **colonna è verità** per il lato (Dare/Avere); non spostare un conto per il nome. Costi
positivi, ricavi in Avere. (Prompt CoGe SP/CE.)

## L4 — Lordo→netto (conti di rettifica)
`F.do ammortamento` / `F.do svalutazione crediti` si **nettano** dall'attivo lordo (mai a
passivo/fondi rischi), anche quando sono stampati in colonna passivo (presentazione lorda).
Il `TOTALE ATTIVITA'` dichiarato è allora **lordo**.

## L5 — Aggregazione ai conti di legge
Sottoconti CoGe → voce di legge (sp01–18 / ce01–20). Layout **mastro + figli puntati**:
si prende il **subtotale del mastro UNA volta** e si ignorano i figli (non sommare entrambi:
doppio conteggio; non sommare solo i figli: si perde la riga "altri"/arrotondamento).

## L5-bis — Reconciler deterministici delle sotto-righe (route A/B) ★
Lo schema IV-CEE pulito stampa ogni sotto-riga di legge, ma il LLM cattura solo gli AGGREGATI.
Due pass deterministici post-LLM (text-path, sia single- sia dual-year) in `pdf_extractor_llm.py`
ri-leggono le righe esplicite, **gated su un totale di controllo stampato** (anti-masking):
- `_reconcile_pn_detail` — righe romane **A.II–A.X → sp12a..h** (specs `_PN_DETAIL_SPECS`), ricalcola
  `sp12_riserve` come somma **ALGEBRICA** → recupera la riserva NEGATIVA `A.VIII` ("Utili/perdite
  portati a nuovo") che altrimenti gonfia il PN e viene mascherata in cassa. Applicato solo se
  `sp11 + Σsp12* + sp13` riconcilia al "Totale patrimonio netto" (`_PN_TOTAL_SPECS`).
- `_reconcile_personale_detail` — **B.9 a/b/c/e → ce08b/c/a/d** (gated su "Totale costi per il
  personale"); la riga CE "c) trattamento di fine rapporto" è distinta dalla riga SP fondo TFR via
  lookahead `(?!\s+di\s+lavoro)`.
- Copertura formati gestionali (2026-06-25): prefisso `A.` opzionale, separatore `)`/`-` **o solo
  spazio** (`IV   Riserva legale`). `pdf_importer._create_income_statement` ora persiste ce08b/c/d.
- No-op senza le righe esplicite o se il gate non riconcilia → zero regressione.

## L5-ter — Reti di sicurezza di routing (route C, deterministico) ★
In `situazione_contabile_parser.py`, additive (scattano solo su risultato altrimenti vuoto/mascherato):
- **Empty→best-effort**: un sub-parser strutturato che torna vuoto su un file fisicamente a 2 colonne
  (`is_contrapposte_file`) viene ritentato con `extract_contrapposte_best_effort`.
- **Verifica PER SEGNO** (`is_bilancio_verifica_segno` + `parse_bilancio_verifica_segno`): stesso conto
  sui due lati, classificato per NATURA (mai per colonna), auto-valida att==pas o solleva `ValueError`.
- **Rescue dotted-hierarchical** (`is_dotted_hierarchical` + `_hier_reconstruct`): famiglia "BILANCIO
  4 SEZIONI" Sistemi/DEPI; àncora sui mastri livello-1 in ordine documento, netta i fondi a qualsiasi
  profondità (`_is_fondo_amm`), tiene il risultato solo se gross-attivo e SP-gap riconciliano entro 0.5%.
- **`_be_split`** sceglie il gutter che BILANCIA le righe con descrizione su entrambi i lati (non il gap
  più largo, che tagliava la colonna passivo → masking).

## Completezza (estrazione CoGe)  ·  `extract_trial_balance_with_llm`
Il LLM, su liste lunghe, **droppa conti in modo non deterministico** (provato: file
byte-identici 343/348 — uno completo, uno corto). Mitigazioni generali:
1. Il **totale dichiarato** è iniettato nel prompt SP come ancora di completezza.
2. Il pass SP è **ritentato** fino a `_COGE_SP_MAX_ATTEMPTS=3`, tenendo la pescata col
   `_plug_residual` minore; stop anticipato quando il residuo è < 2% del totale.
3. Prompt SP: regole esplicite di *completezza* e *mastro+figli*.

## Pipeline per route (dove si applica ciascuna quadratura)
Per il PDF la riconciliazione ai totali e il confronto CE↔SP precedono la validazione;
gli scarti restano visibili e non vengono chiusi con un plug:

**Route C (verifica / situazione contabile)**
1. Estrai i candidati CoGe-LLM e deterministico; scegli con la graduatoria corrente di completezza e validazione.
2. `_reconcile_trial_to_declared` sul candidato scelto → scarti diagnostici; recupero di `sp13` solo con tre conferme indipendenti.
3. `enforce_ce_sp_identity(prefer="sp13", declared=…)` → misura CE↔SP senza allineare i prospetti.
4. `validate_balance` (gate Attivo=Passivo).

**Route A/B (IV-CEE)**
1. `_llm_extract` (single-year corrente + dual-year per il precedente).
2. `reconcile_ivcee_balance` → copia invariata e scarti diagnostici verso pareggio e totali dichiarati.
3. `enforce_ce_sp_identity(prefer="sp13", declared=…)` → misura CE↔SP senza correzione contabile.
4. `validate_balance`.

**OTHER / XBRL nativo** (`.xbrl`/`.xml`): importer XBRL dedicato (`xbrl_parser_enhanced.import_to_database`).
Il parser verifica pareggio e identità CE↔SP con `check_quadratura`; non chiama
`enforce_ce_sp_identity` e non crea una voce per pareggiare lo scarto.
CE-only / non-bilancio → errore onesto.

## Verifica
`Test/_full_diagnostic.py Test/june_sample --llm` misura per-file rotta, validate_balance,
quadra/masked/vuoto e plug. La baseline pre-modifica è in `Test/_analysis/diag_june_llm.json`.
CE↔SP per route: `Test/_ce_sp_ivcee2.py` (IV-CEE) e `Test/_repro_real2.py` (C + IV-CEE end-to-end).
