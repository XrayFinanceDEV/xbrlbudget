# Diagnosi budget_615 — AGO "Situazione Contabile" contrapposte NON ruotata

File: `tests/debug/budget_615_2024 Lavori di meccanica generale.pdf`
sha256: `911d2c32e30b900e867f4dd6b8288be31b1f4e6122f0e73ce9fff8b0a93b3659`
Esito attuale: **HTTP 422** — `Balance FAILED: Assets=2398853.0 != Liabilities=2114387.0 (difference: 284466.0)`

> Il file **non è nel corpus** (nessuna voce nel `manifest.json`): non è mai stato coperto
> dall'audit 214 file / PASS 77.

## 1. Il documento è CORRETTO e quadra

Letto dal rendering (pag. 3 SP, pag. 8 CE):

| | |
|---|---|
| TOTALE ATTIVITA' | 2.828.226,30 |
| TOTALE PASSIVITA' | 2.694.521,04 |
| UTILE D'ESERCIZIO | 133.705,26 |
| TOTALE A PAREGGIO | 2.828.226,30 |
| TOTALE COSTI / RICAVI | 1.323.220,24 / 1.456.925,50 |

`2.694.521,04 + 133.705,26 = 2.828.226,30` — quadra alla virgola.
`1.456.925,50 − 1.323.220,24 = 133.705,26` — CE↔SP coerente.

## 2. Il layer di testo è parzialmente distrutto (export AGO 06.07.00)

Due corruzioni **distinte**:

1. **Ammontari con glifi `_` interlacciati** — `_4_.08_0_,_9_0_` = 4.080,90.
   118 su ~177 ammontari. Sono le righe di **dettaglio** (blu, sottolineate): la
   sottolineatura è disegnata come glifi `_` (stesso font CIDFont+F2, stessa size,
   stesso colore dei numeri → **non discriminabili per font**; si sovrappongono:
   avanzamento ~1,94pt con larghezza 3,65pt).
2. **Righe in grassetto / barra grigia disegnate come VETTORI, non testo.**
   Nella banda dove si vedono "CONTO ECONOMICO / COSTI / RICAVI" il layer di testo
   contiene **due caratteri spazio**. Idem per `TOTALE ATTIVITA'`, `TOTALE PASSIVITA'`,
   l'importo del pareggio SP, e **2 mastri di pag. 3**:
   `37065010 Altri debiti (OE) 2.000,00` + `39000005 Ratei e risconti passivi 53.536,60`
   = **55.536,60** (i loro dettagli, invece, SONO nel testo).

Verifiche: `low.find("conto economico") == -1`, `find("totale attivita") == -1`,
`find("totale passivita") == -1`.

## 3. Ricostruzione per COORDINATE: i MASTRI sono già puliti

Leggendo le righe con codice mastro a 8 cifre (split colonne per **x**, `_` rimossi):

| Sezione | Somma mastri | Dichiarato | Esito |
|---|---|---|---|
| SP attivo | 2.828.226,30 | 2.828.226,30 | **esatto** |
| SP passivo | 2.638.984,44 | 2.694.521,04 | −55.536,60 (i 2 mastri vettoriali) |
| CE costi | 1.323.220,24 | 1.323.220,24 | **esatto** |
| CE ricavi | 1.456.925,50 | 1.456.925,50 | **esatto** |

I **dettagli** invece NON sono un sostituto (somma 1.025.732,26 vs 2.828.226,30).
=> **La riparazione degli `_` NON è il fix**: i mastri sono già leggibili.
`_c8_parse_side` già scarta i token `_` (`t.startswith('_')`).

## 4. CAUSA RADICE (deterministico): asse di split sbagliato

`parse_entries_contrapposte_8digit` divide le colonne per **y**, assumendo la pagina
**ruotata** ("left column = higher coordinate on the split axis (rotated page)").

budget_615 è landscape **NON ruotata** (`rotation=0`, 841×595):
`ATTIVITA'` x=156,12 y=90,74 — `PASSIVITA'` x=574,55 y=**90,74** (stessa y!).

```
mid = (ly + ry_)/2 = (90.74 + 90.74)/2 = 90.74
left  = _c8_parse_side(words, mid, 1e9)   -> TUTTO sotto l'header (ENTRAMBE le colonne)
right = _c8_parse_side(words, -1e9, mid)  -> NULLA
```
→ log osservato: `totale_attivo=382558.51, totale_passivo=0` (3 entries).

## 5. Difetti concatenati

1. **Asse di split** (sopra) → parser deterministico inutilizzabile.
2. **Pagine senza header saltate**: sezione e gutter sono ricavati dagli header
   `ATTIVITA'`/`PASSIVITA'` su **ogni** pagina; essendo vettoriali tranne a pag. 2,
   le pagine 1 e 3 (che contengono la maggior parte dei dati) fanno `continue`.
3. **Totali di footer illeggibili** (vettoriali) → `declared_attivo/passivo = 0` →
   nessuna Entry utile → `sp13 = 0`.
4. **`_text_layer_is_garbled()` non rileva questa classe**: è tarata sulla firma
   budget_337 (`3.239 , 12`, spazio prima della virgola) → **0 match** qui.
   Quindi niente flag "TESTO PDF CORROTTO" e i totali dichiarati NON vengono soppressi.
5. **Il pareggio del CE ancora l'SP**: `_declared_control_totals` →
   `attivo=None, passivo=None, pareggio=1.456.925,50` (il pareggio **del CE**, pag. 8).
   Il fix SP-scoped di `05924ab` taglia su `"conto economico"`, ma quell'header è
   vettoriale → `find()` = -1 → fallback al testo intero → prende il totale del CE.
6. **Scan contra** non trova fondi (0) → nessun netting, nessuna riduzione dell'ancora.
7. **Selezione candidati**: logica corretta su ancora sbagliata — CoGe-LLM vince con
   gap 941k contro 1.07M del deterministico.
8. **best-effort è peggio** (attivo 1,96M, sp16 4,84M: legge le pagine CE come debiti),
   quindi allargare la rete "empty→best-effort" non aiuta.

## 6. Ciò che funziona correttamente (nessuna regressione)

`sp13 = 133.705` è **giusto** (= utile dichiarato 133.705,26) e il codice ha
**rifiutato** di forzarlo al 418.171 implicito ("risultato implicito non confermato:
nessun valore è stato modificato"). Prima del refactor questo file avrebbe *plugato*
284k in cassa/debiti e sarebbe "entrato" con numeri falsi. **Il 422 è l'esito onesto**
di un'estrazione che ha davvero perso massa: non è una regressione dei 18 commit, è un
caso di testo corrotto preesistente che ora non viene più nascosto.

## 7. Piano di correzione

### FATTO (verificato, nessuna regressione)

1. **[FATTO] Rilevare l'asse di split** in `parse_entries_contrapposte_8digit`: se i due
   header condividono la **y** e differiscono in **x** → split per x; se condividono la x
   → split per y (ruotata, comportamento attuale = corpus esistente invariato).
   `_c8_parse_side(words, lo, hi, axis=1)` — default `axis=1` invariato per i chiamanti
   esistenti. Test: `tests/test_c8_split_axis.py` (3 test, entrambe le orientazioni).
   **Misura su budget_615**: passivo 0 → 1.057.711,53; entries 3 → 9.
   Suite: 136 passed / 4 failed (le stesse 4 preesistenti del §8).
   **NON basta**: il file non importa ancora (restano i punti 2-4).

### FATTO — 2026-07-20 (budget_615 ora IMPORTA; suite `tests/test_c8_split_axis.py` = 5/5)

2. **[FATTO] Gutter+sezione a livello di documento.** Due difetti distinti erano in gioco:
   - **Gutter dai DATI, non dagli header** (`_c8_refine_gutter_x`, solo axis=0): l'header-midpoint
     (365) tagliava la banda degli **importi attivo** (right-aligned a x≈357-379, vicini alla
     colonna-codice passivo a 417) → ~260k di attivo finivano nel reader passivo e persi. Il
     gutter va nel gap pulito prima della colonna-codice destra (≈398). Override solo se
     l'header-midpoint cade FUORI dal gap (additivo: pagine già corrette invariate).
   - **Seconda passata** per le pagine i cui header ATTIVITA'/PASSIVITA'/COSTI/RICAVI sono
     **vettoriali** (saltate dalla passata header): riusa il gutter di documento e usa la
     **COLONNA fisica** come verità (sx = attivo/costi, dx = passivo/ricavi). Il confine SP→CE
     viene dal **riconoscimento OIC** (`resolve(...).statement` — NON dai prefissi codice, che
     variano tra gestionali): prima pagina a maggioranza CE = inizio CE, contiguo fino a fine
     documento. Una pagina-footer CE i cui "header" sono i label TOTALE (split vuoto) NON viene
     marcata come letta → la raccoglie la seconda passata.
3. **[FATTO] Utile dal CE** (`ricavi − costi`) quando i footer SP sono illeggibili.
4. **[FATTO] Recupero mastri orfani vettoriali** (`_c8_recover_orphan_passivo`): NB — su questo
   export **anche gli importi di dettaglio sono corrotti** (glifi `_` interlacciati DENTRO il
   token importo), quindi il control-total wholesale non è applicabile. Recupero **mirato**: legge
   i dettagli passivo puliti (strip `_`) sulle pagine solo-dettaglio, e aggiunge SOLO il
   sottoinsieme che chiude ESATTAMENTE il gap Attivo-Passivo (`_unique_subset_summing_to`),
   ratei/risconti → sp18, altri debiti (OE) → sp17. `amministratori c/compensi` (già dentro un
   mastro catturato) non entra nel gap → escluso.
5. **[FATTO] Auto-validazione** (§7.4): il recupero si applica SOLO se il foglio quadra
   (`attivo == passivo`), altrimenti `bs` invariato → non può mai corrompere un foglio.
6. **[implicito]** Il foglio ora quadra PRIMA del reconcile declared, quindi il pareggio-CE
   1.456.925,50 letto come ancora SP è un no-op (non c'è gap da plugare). Se in futuro servisse,
   escludere esplicitamente i totali di sezione CE dall'ancora SP.
7. **[DA FARE, opzionale]** Rilevatore garbled: firma `_`-interlacciato (difesa in profondità;
   da solo non fa importare il file — il recupero mirato lo importa già).

**Esito**: `import_pdf_balance_sheet` (deterministico) supera `validate_balance`; attivo=passivo=
2.096.501,91 (netto); sp13=133.705,26; CE net (chiavi full) = 133.705,26 = sp13 (identità CE↔SP ok).

## 8. Nota sul corpus / test

- Il corpus (137 file) **non è presente** in questo checkout: regressione limitata alla
  suite unit + `tests/debug/`.
- Baseline suite (main @ bbf113a): **4 failed, 133 passed, 24 skipped**, preesistenti:
  - `test_contra_netting.py::test_contra_rows_on_613_finds_the_fondi_mass`
  - `test_contra_netting.py::test_613_production_path_with_stubbed_gross_llm`
    → `ValueError: too many values to unpack (expected 2)`: `_contra_rows` restituisce
    ora **3** valori, i test ne spacchettano 2 (test non aggiornati).
  - `test_csv_schema_detection.py` (2)
  Falliscono solo perché i PDF di evidenza sono presenti in `docs/examples/` (untracked):
  senza quei file gli `skipif` li saltano (da qui il "157 passed" del commit).
