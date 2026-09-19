# M2-02E — quattro indicatori canonici mancanti per le pagine v4

## Worktree e commit

- Worktree: `/home/peter/orca/workspaces/budget/m2-02e-indicatori`, branch
  `XrayFinanceDEV/m2-02e-indicatori`, base `12edc86` (verificato con `git log --oneline -1` prima
  di iniziare — invariato).
- File toccati (6, `git diff --stat`):
  - `calculations/report_indicators.py` (+23) — le quattro formule.
  - `backend/app/services/final_report_dossier.py` (+11) — esposizione nel catalogo indicatori.
  - `frontend/components/final-report/Dossier.test.tsx` (+1/-1) — conteggio congelato 44 → 48.
  - `tests/fixtures/final_report/v2/{bilancio,infrannuale,startup}.json` — rigenerate con
    `PYTHONPATH=backend:. python tests/test_final_report_v2.py`.
  - `contracts/final_report_dossier_catalog.json` **non toccato** nella versione finale (vedi
    «Scostamento dal piano» sotto).
- Nessun terminatore di riga normalizzato, nessun file untracked incluso, nessun push.

## Che cosa è stato costruito

Quattro nuove voci `practice.*` in `calculations/report_indicators.py::indicator_results`, stesso
schema delle esistenti (metodologia, convenzione `pratica-v1`, motivo di indisponibilità quando il
denominatore non è valido):

1. **`practice.opex_revenue`** — Costi Operativi / Ricavi, %. Formula:
   `(production_cost − ce09_ammortamenti) / ce01_ricavi_vendite × 100` (denominatore **ce01**, non
   il valore della produzione: coerente con la tabella «Driver» di pagina 7, dove il rapporto è
   letto contro i soli ricavi di vendita, non contro l'intero valore della produzione). Nessuna
   guardia `positive=True` sul denominatore, come gli altri rapporti su ricavo (`ebitda_margin`,
   `ros`, `of_revenue`).
2. **`practice.effective_tax_rate`** — Aliquota Effettiva, %. Formula:
   `ce20_imposte / profit_before_tax × 100`, **stessa convenzione e stessa soglia di scarto del
   motore di previsione** (`calculations/forecast_engine.py::_tax_components`, oltre il 60%):
   ricalcolata qui invece di letta dal motore perché `_tax_components` lavora su una coppia
   `base_inc`/`projected_inc` di due periodi distinti, non su un singolo periodo del dossier — il
   brief ammette esplicitamente questa via («se non è riusabile senza toccare il motore, calcola
   lo stesso rapporto... e dichiaralo nella metodologia»).
   > **Nota 2026-09-18 — a questa frase non credete più per la parte sul motore.** Dal commit
   > `073927b` (commercialista) `_tax_components` **non deriva nessuna aliquota**: applica
   > `tax_rate` così com'è, `base_inc` è un parametro morto e la soglia del 60% vive in
   > `projection_common.aliquota_effettiva`, che serve solo a **proporre** l'aliquota. Il dossier
   > non potrebbe leggere dal motore una proporzione che il motore non calcola più: la formula e la
   > soglia di questo indicatore restano giuste, la motivazione qui sopra è storica. Motivo `non_positive_denominator` se
   il risultato ante imposte non è positivo, `aliquota_fuori_intervallo_plausibile` (nuovo, non
   presente altrove nel file) se il rapporto supera il 60%.
3. **`practice.ebit_margin`** — Margine EBIT, %. Formula: `EBIT / ricavi × 100`, identica a
   `practice.ros` esistente ma esposta con una chiave e un'etichetta proprie: `ros` è pensata per
   la tabella redditività di pagina 13, `ebit_margin` copre **tutti** i periodi canonici (storico,
   osservato, rettificato, chiusura, anni di piano) per il grafico «Evoluzione dei margini» di
   pagina 8, dove `chart_series["margins"]` copre solo gli anni di piano e non ha il punto della
   chiusura.
4. **`practice.quick_ratio`** — Liquidità Immediata, ratio. Formula:
   `(attivo corrente pratica − rimanenze) / debiti entro 12 mesi` — stesso numeratore già usato da
   `mt` (margine di tesoreria, in euro) ma come rapporto anziché come importo. Convenzione
   `pratica-v1` distinta da `analytical.liquidity.quick_ratio` (perimetro diverso, già annotato
   nella mappatura v4 pagine 12-33): non riusa quest'ultima per non mescolare due perimetri di
   attivo corrente diversi nello stesso grafico «Liquidità corrente e immediata».

Esposizione nel catalogo (`backend/app/services/final_report_dossier.py::build_indicator_catalog`):
le quattro voci **non** entrano in `contracts/final_report_dossier_catalog.json` (quel file è
generato da `frontend/lib/pratica-indicators.ts::INDICATOR_DEFS`, il perimetro — distinto — della
scheda Indicatori della pratica, con la propria interfaccia `IndicatorSet` e il proprio sistema di
punteggio di crisi: toccarlo avrebbe portato la modifica ben oltre il modello v2 del report). La
via corretta, già in uso per M2-02C (`practice.personnel_revenue`), è un secondo elenco `definitions
+=` scritto a mano dentro `build_indicator_catalog`, con la propria label/format/family. Le
quattro nuove voci seguono lo stesso pattern.

## Scostamento dal piano

Il brief («esposizione nel catalogo del dossier, `backend/app/services/final_report_dossier.py`»)
è stato inizialmente letto come «aggiungi le righe a `contracts/final_report_dossier_catalog.json`»
(dove vivono `dscr`, `ebitda_margin`, `mt`, ecc.). Il primo tentativo ha modificato quel JSON a
mano — e ha fatto fallire `lib/final-report-v2-contract.test.ts` («keeps the backend presentation
catalog synchronized with the existing report»): quel file è un **artefatto generato** da
`node tools/final_report/export_catalog.cjs`, a sua volta sorgente da `pratica-indicators.ts`.
Rigenerarlo da lì avrebbe richiesto aggiungere le quattro chiavi a `IndicatorSet` e alla funzione
di calcolo `computeIndicators` della scheda Indicatori (un perimetro client separato, con un
proprio sistema di punteggio), fuori scope. Corretto seguendo il precedente di M2-02C: le quattro
voci sono ora nel secondo elenco hardcoded di `build_indicator_catalog`, il JSON contratto è
**tornato esattamente come prima** (verificato con `node tools/final_report/export_catalog.cjs
--check`, che ora passa).

## Valori AMBIENTA (azienda 575, scenario 18 "Budget 2027–2029")

Da una **copia** del DB reale (`cp financial_analysis.db copia-m2-02e.db`, mai il DB reale),
`PYTHONPATH=backend:.`, `assemble_final_report(db, company_id=575, scenario_id=18,
schema_version=2)`. 7 periodi: `historical:2025`, `observed:2026`, `adjusted:2026`,
`closing:2026`, `forecast:2027/2028/2029`.

| Periodo | opex_revenue % | effective_tax_rate % | ebit_margin % | quick_ratio |
|---|---|---|---|---|
| historical:2025 | 102,49 | **null** [aliquota_fuori_intervallo_plausibile] | 2,02 | 0,9498 |
| observed:2026 | 96,82 | 0,00 | 1,98 | 1,1632 |
| adjusted:2026 | 101,57 | 41,80 | 2,36 | 1,0167 |
| closing:2026 | 101,65 | 57,76 | 2,20 | 1,0784 |
| forecast:2027 | 101,27 | 57,76 | 1,78 | 1,1329 |
| forecast:2028 | 99,75 | 57,76 | 3,21 | 1,0965 |
| forecast:2029 | 97,17 | 57,76 | 5,72 | 1,1548 |

Nota su `effective_tax_rate`: il valore resta stabile a ~57,76% da `closing:2026` in poi perché il
motore di previsione deriva l'aliquota effettiva **una sola volta** dall'anno base (qui la
chiusura promossa) e la riapplica a ogni anno di piano (`_tax_components`); le piccole differenze
fra un anno e l'altro (57,76187158... vs 57,76187906...) vengono dalla componente di imposte
differite sommata sopra l'imposta corrente. Su `historical:2025` il rapporto grezzo è 78,60%
(imposte 28.773 / risultato ante imposte 36.608,36): sopra il 60%, scartato correttamente.

## Controllo a mano

`practice.ebit_margin` su `historical:2025` (`financial_year_id=444`), letto riga per riga dal DB
copiato:

```
production_value = ce01+ce02+ce03+ce03a+ce04 = 4.006.984,18
production_cost   = ce05+ce06+ce07+ce08+ce09+ce10+ce11+ce11b+ce12 = 3.930.971,76
ebit              = production_value - production_cost = 76.012,42
ricavi (ce01)     = 3.761.087,73
ebit_margin       = 76.012,42 / 3.761.087,73 × 100 = 2,021022253580880975621379616
```

Coincide esattamente con il valore riportato dal modello assemblato (nessuno scostamento, calcolo
in `Decimal` su entrambi i lati).

Controllo aggiuntivo su `effective_tax_rate` (stesso anno): `ce20_imposte = 28.773`,
`profit_before_tax = 36.608,36` (ebit + risultato finanziario + rettifiche D + straordinario) →
rapporto grezzo `0,78596801...` = 78,60%, sopra la soglia del 60% del motore → il modello
correttamente restituisce `null` con motivo `aliquota_fuori_intervallo_plausibile`.

## Test eseguiti

```
cd /home/peter/orca/workspaces/budget/m2-02e-indicatori
PYTHONPATH=backend:. backend/venv/bin/python -m pytest -q tests/test_final_report_v2.py \
  tests/test_final_report_contract_parity.py tests/test_analysis_exact_decimals.py \
  tests/test_m1_05b_assumption_sections.py
# 83 passed, 199 warnings (preesistenti, deprecation) in 4,71s

cd frontend
npx vitest run lib/final-report-v2-contract.test.ts components/final-report/Dossier.test.tsx
# 2 file, 9 test, tutti verdi (1,14s) — incluso il sync check del catalogo generato

npx tsc --noEmit
# nessun output, verde
```

## Rischi residui

- `practice.opex_revenue` supera il 100% su quasi tutti i periodi di AMBIENTA (97-102%): non è un
  difetto — il denominatore è `ce01` (soli ricavi di vendita), non il valore della produzione, e
  la differenza è coperta da `ce02/ce03/ce04` (altri componenti positivi del valore della
  produzione) che il rapporto richiesto dal brief esclude di proposito. Un lettore della pagina 7
  potrebbe leggere un valore >100% come un errore: è la conseguenza attesa della formula
  specificata dalla mappatura, non un bug.
- La soglia `aliquota_fuori_intervallo_plausibile` è nuova (non esisteva altrove nel file):
  nessun renderer la consuma ancora in modo esplicito (il vincolo del task esclude modifiche ai
  template Typst, che li sta riscrivendo un altro agente) — verificare, quando quell'agente
  integrerà la tabella «Driver» di pagina 7, che un motivo di indisponibilità venga mostrato come
  testo dichiarativo e non come una cella vuota silenziosa.
- Non ho toccato `frontend/lib/pratica-indicators.ts` (scheda Indicatori della pratica): i quattro
  indicatori nuovi vivono **solo** nel modello v2 del report finale, non nella scheda Indicatori
  del percorso pratica, che resta con le sue proprie chiavi (incluso `_quick_ratio`, tuttora
  privato). È la lettura corretta dello scope del brief, ma è una scelta di confine che vale la
  pena confermare col richiedente se in futuro la scheda Indicatori dovesse voler mostrare le
  stesse quattro voci.
