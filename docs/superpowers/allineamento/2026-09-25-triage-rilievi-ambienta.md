# Triage AMBIENTA — verdetto 2026-09-25 (rifatto dopo la revisione finale)

Commit confrontati: `62bfed1` (prima del lotto di fix) vs `HEAD` = `6d7ed1c` (branch `test/rilievi-ambienta`,
ultimo commit del banco prima di questo rapporto), tramite `tools/triage_rilievi.py` (worktree temporaneo su
`62bfed1` sotto `.superpowers/triage/`, rimosso a fine corsa). Foglio scritto:
`inbox/Verifica_piano_Ambienta_triage.xlsx` (l'originale `Verifica_piano_Ambienta_problemi.xlsx` non è stato
toccato).

**Come si misura.** pytest gira con `--runxfail` e Vitest su una copia temporanea del file con `it.fails(` riscritto
in `it(`, su entrambi i commit: i marcatori xfail non cambiano l'esito misurato (prima della revisione finale un
xfail usciva come `skipped` e il verdetto si invertiva). Sopra il verdetto meccanico c'è uno strato di **letture a
mano** (`LETTURE` nello script) che sovrascrive Stato e Note dove l'esito del banco da solo inganna; la nota tiene
sempre l'esito meccanico («— banco: 62bfed1=…, HEAD=…»).

**Base dati**: AMBIENTA 2026 locale, `FinancialYear` id 493 (ricavi 4.109.510), **non** il 2026 del consulente
(ricavi 4.209.510). Gli oracoli sono le formule del consulente applicate a questa base: si verifica il
*meccanismo*, non la cifra del foglio originale.

## Controllo di raccolta

- `vecchio-pytest.xml` (62bfed1): 27 testcase, 0 `<error>` — 7 failed, 9 passed, 11 skipped (i test di report:
  il Business plan ReportLab non esisteva, `_bp()` fa `importorskip("backend.app.renderers.business_plan.data")`).
- `nuovo-pytest.xml` (HEAD): 27 testcase, 0 `<error>` — 16 failed, 11 passed.
- `vecchio-vitest.xml` / `nuovo-vitest.xml`: 4 testcase ciascuno, 0 errori. Import statici: tutte le funzioni del
  wizard esistono già su 62bfed1 (ruling nel file Vitest).

## Tabella per test (esito misurato, senza marcatori)

| ID | test | 62bfed1 | HEAD | meccanismo |
|---|---|---|---|---|
| A01 | `test_A01_scostamento_materie_applicato_dal_motore` | pass | pass | il motore applica lo scostamento −5 punti sulle materie |
| A01 | vitest `A01 lo scostamento digitato resta lo scostamento dopo un cambio dei ricavi` | pass | pass | riscritto sul percorso vero (`withRevenueGrowth`): lo scostamento resta. Il vecchio test (rosso) era un falso positivo |
| A01-bis | `test_A01_bis_salvataggio_respinto_non_stampa_il_previsionale_vecchio_come_buono` | skip (n/a) | **fail** | dopo un salvataggio respinto il PDF in bozza stampa il previsionale vecchio senza avviso |
| A02 | `test_A02_bep_del_report_usa_la_ripartizione_del_motore` | skip (n/a) | **fail** | il BEP del report non usa `details['pareggio']` del motore |
| A03 | `test_A03_acconto_manuale_maggiore_di_zero_vince_sulla_percentuale` | pass | pass | acconti digitati usati; ora anche sul persistito (posizione tributaria netta 2027 spostata di 50.000 − acconto di default) |
| A03 | vitest `A03 il passo Imposte ha un campo per anno collegato a tax_advances_paid` | pass | pass | campo collegato |
| A04 | `test_A04_incasso_scadenziato_sui_crediti_oltre_12_mesi_arriva_allo_sp` (base: oltre tutto su sp07a) | fail | pass | sp07a 45.000 → 44.000 |
| A04 | `test_A04_…_altri_crediti_oltre_12_mesi[tutto_su_sp07g]` (nuovo) | fail | pass | tutto su sp07g: 45.000 → 44.000 |
| A04 | `test_A04_…_altri_crediti_oltre_12_mesi[mix_del_consulente]` (nuovo) | fail | **fail** | sp07a 35.231 + sp07g 9.769: l'incasso si ripartisce per proporzione, sp07g 2027 = 9.551,91 invece di 8.769 |
| A05 | `test_A05_immobilizzazioni_finanziarie_senza_regola_non_seguono_i_ricavi` | pass | pass | sp04 senza regola resta 52.550 |
| A05 | vitest `A05 passare a Manuale da «ricavi» congela in sp_overrides la crescita coi ricavi` (nuovo, caratterizzazione) | pass | pass | `withSpRule(…, null, anteprima)` scrive 55.178 / 58.488 / 62.582 in `sp_overrides`: i numeri del consulente |
| A06 | `test_A06_previdenziali_seguono_il_personale_se_la_tendina_lo_dice` | pass | pass | sp16f segue ce08 |
| A06 | vitest `A06 l'etichetta dei previdenziali dice quello che fa il motore` | pass | pass | etichetta coerente col motore |
| B01 | `test_B01_variazione_rimanenze_del_ce_segue_lo_sp` | fail | **fail** | ce10 fermo al 2026 mentre lo SP segue il DIO |
| B02 | `test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo` | fail | **fail** | 61.040 contro 25.716,59 nel 2029 |
| B03 | `test_B03_tfr_uguale_retribuzioni_diviso_13_5` | fail | **fail** | TFR = residuo del personale, non salari/13,5 |
| B04 | `test_B04_fidi_e_residui_che_non_quadrano_col_bilancio_si_rifiutano` | pass | pass | respinto con lo scarto nel messaggio |
| B05 | `test_B05_rata_oltre_orizzonte_non_scadenziata_sta_a_breve` (scenario del consulente, rinominato) | fail | **fail** | piano fino al 2029 con residuo: sp16a 2029 = 300.000, manca la rata |
| B05 | `test_B05_bis_rata_2030_scadenziata_sta_a_breve` (variante, rinominata) | pass | pass | con la rata 2030 scadenziata sp16a 2029 = 353.409 |
| C01 | `test_C01_il_dscr_del_report_comprende_la_quota_capitale` | skip (n/a) | **fail** | DSCR senza quota capitale |
| C02 | `test_C02_dso_sui_soli_crediti_commerciali` | skip (n/a) | **fail** | DSO su tutti i crediti |
| C03 | `test_C03_rod_sui_debiti_finanziari` | skip (n/a) | **fail** | ROD sul totale debiti |
| C04 | `test_C04_pfn_del_report_comprende_gli_altri_finanziatori` | skip (n/a) | **fail** | PFN senza sp17b |
| C05 | `test_C05_un_solo_current_ratio_nel_documento` | skip (n/a) | **fail** | 1,28 contro 1,17 |
| C06 | `test_C06_indice_di_indebitamento_e_debiti_su_patrimonio` | skip (n/a) | **fail** | 2,24 = immob/PN; né debiti/PN (9,36) né attivo/PN (11,38) |
| C07 | `test_C07_copertura_immobilizzazioni_con_il_tfr` | skip (n/a) | **fail** | TFR fuori dalle fonti consolidate |
| C08 | `test_C08_erogazioni_e_rimborsi_su_righe_separate` | skip (n/a) | **fail** | erogazione e rimborsi compensati |
| C09 | `test_C09_oneri_su_mol_parte_dalla_colonna_base` | skip (n/a) | **fail** | il testo non parte dalla colonna base |
| E05 | `test_E05_caratterizzazione_ammortamento_primo_anno_e_straordinari` | pass | pass | aliquota piena nel primo anno (comportamento criticato) |
| E05 | `test_E05_caratterizzazione_straordinari_ripetuti_ogni_anno` (nuovo) | pass | pass | ce18/ce19 della base ripetuti identici 2027-2029 (comportamento criticato) |

I 16 test in **fail** su HEAD sono esattamente quelli marcati `xfail(strict=True, raises=AssertionError)`.

## Verdetto per ID (stampa dello script; `[meccanico: …]` quando una lettura prevale)

```
A01  Confermato solo come previsionale vecchio nel PDF (A01-bis)   [meccanico: Regressione]
A02  Confermato (n/a su 62bfed1)
A03  Non riprodotto
A04  Confermato sulla riga del consulente (sp07g)   [meccanico: Confermato]
A05  Comportamento voluto (beb33c5)   [meccanico: Non riprodotto]
A06  Non riprodotto (doppio comando confermato)   [meccanico: Non riprodotto]
B01  Confermato
B02  Confermato
B03  Confermato
B04  Non riprodotto
B05  Confermato
C01  Confermato (n/a su 62bfed1)
C02  Confermato (n/a su 62bfed1)
C03  Confermato (n/a su 62bfed1)
C04  Confermato (n/a su 62bfed1)
C05  Confermato (n/a su 62bfed1)
C06  Confermato (n/a su 62bfed1)
C07  Confermato (n/a su 62bfed1)
C08  Confermato (n/a su 62bfed1)
C09  Confermato (n/a su 62bfed1)
E04  Senza test
E05  Riprodotto (caratterizzazione, scelta ⚖)   [meccanico: Non riprodotto]
```

(D01-D05, E01-E03 sono «Consulente», fuori perimetro: il foglio li lascia «Aperto».)

## Letture

Le letture a mano (`LETTURE` in `tools/triage_rilievi.py`) prevalgono sullo Stato meccanico nel foglio:

- **A01** — «Confermato solo come previsionale vecchio nel PDF (A01-bis); motore e wizard corretti». Il motore
  applica lo scostamento e il wizard lo mantiene (`withRevenueGrowth`, fissato anche da `budget-horizon.test.ts`);
  resta rosso solo A01-bis. Il meccanico «Regressione» è un artefatto: l'ID A01 raccoglie tre test, e su 62bfed1
  A01-bis è `skip` (n/a) mentre gli altri due passano, quindi il lato vecchio aggrega a `pass`.
- **A03**, **B04** — «Motore non riprodotto; sintomo spiegato da A01-bis»: il consulente ha visto un previsionale
  vecchio stampato dopo un salvataggio respinto (bulk 200, `forecast_generated: false`).
- **A04** — la riga del consulente è «Altri crediti oltre 12 mesi» = `sp07g` (9.769, «resta 8.769»), non `sp07a`.
  Il wizard scrive lo stesso piano qualunque sia la sottovoce (`massaOltre` dei crediti commerciali comprende
  `sp07g`); il motore mette il residuo sull'aggregato `sp07` e lo ripartisce in proporzione fra le sottovoci. Con
  tutto su una sottovoce (sp07a o sp07g) l'incasso arriva (risolto il 2026-09-24); con il mix del consulente no.
- **A05** — «Comportamento voluto (beb33c5) che produce il sintomo: passare a Manuale da «ricavi» congela la
  crescita — decisione del proprietario». Il motore con sp04 senza regola tiene il saldo; ma il wizard, passando a
  Manuale da una regola «ricavi», congela in `sp_overrides` i valori cresciuti (caratterizzazione Vitest).
- **A06** — «Motore non riprodotto; doppio comando confermato per ispezione»: casella + tendina sugli stessi
  previdenziali (`lib/budget-circolante-step.ts:229-232`), nessun test lo misura.
- **B05** — il test col nome `test_B05_` è ora lo scenario del consulente (piano che finisce nel 2029 con un
  residuo aperto): rosso. La variante con la rata 2030 scadenziata (`test_B05_bis_`) è verde.
- **E05** — «Riprodotto (caratterizzazione, scelta ⚖)»: i due test asseriscono il comportamento che il consulente
  critica (aliquota piena nel primo anno, straordinari ripetuti), quindi verde = riprodotto. Falliranno quando la
  scelta del proprietario sarà implementata: è atteso.
- **E04** — fuori perimetro (spec §6), «Senza test».
- **Base** — valori assoluti ricalcolati sulla base 493, non le cifre del foglio del consulente.

## Lotto 1, 2026-09-26

Fix sul motore (`docs/superpowers/specs/2026-09-26-fix-rilievi-ambienta-design.md` §3, branch
`fix/rilievi-ambienta`, task 1-8 del piano). `tools/triage_rilievi.py::LETTURE` aggiornato per B01, B02, B03, B05,
A04, E05 — «Risolto nel lotto 1 fix rilievi (2026-09-26)» (A04 ed E05 con «su decisione del proprietario»); il
banco (`tests/test_rilievi_ambienta.py`) conferma: `../budget/backend/venv/bin/python -m pytest
tests/test_rilievi_ambienta.py -q -p no:warnings` → **16 passed, 11 xfailed** — i sei rilievi del lotto passano
tutti senza marcatore `xfail`, i soli xfail residui sono del lotto 2 (A01-bis, A02, C01-C09), come atteso.

- **B01** — `ce10_var_rimanenze_mat_prime` segue ora lo stato patrimoniale delle sole materie (sp05a), non più i
  ricavi; il DIO delle materie si deduce dal consumo (ce05 + ce10), non dal fatturato
  (`details['rimanenze_materie']`). Un `ce10_override` oltre la giacenza in apertura si rifiuta.
- **B02** — l'ammortamento dei cespiti esistenti si ferma al residuo netto invece di continuare alla quota piena;
  ogni nuovo investimento ammortizza per conto proprio (`details['ammortamenti']`).
- **B03** — `ce08a` (TFR) è sempre `ce08b / 13,5`, non più capato al residuo del personale; un'eccedenza ricompone
  il totale come somma e lo dichiara (`details['personale_ricomposto']`).
- **B05** — nell'ultimo anno di piano un contratto scadenziato a mano la cui lista non copre l'anno dopo ripete a
  breve l'ultima rata positiva (`rata_ripetuta`), invece di lasciare l'intero residuo a lungo termine oltre
  l'orizzonte del piano; la stessa regola vale anche per gli altri finanziatori (`details['altri_finanziatori']`),
  ruling del controller del Task 6.
- **E05** — decisione del proprietario (2026-09-26): un nuovo investimento ammortizza a metà aliquota nell'anno
  d'ingresso, piena dopo; proventi e oneri straordinari valgono zero in ogni anno di piano, salvo override
  esplicito. Il comportamento criticato dal consulente è quello che i due test caratterizzavano prima del lotto —
  ora asseriscono la regola scelta.
- **A04** — **Risolto nel lotto 1 fix, 2026-09-26, su decisione del proprietario** (Task 7, worktree separato
  `../budget-fix-rilievi-t7`, branch `fix/rilievi-t7` da `c1f621b`, cherry-pick `3eda49d` su
  `fix/rilievi-ambienta`): con un piano `crediti_commerciali` l'incasso della massa oltre 12 mesi consuma prima
  `sp07a` (clienti), poi `sp07b/c/d/g` in ordine, mai sotto zero (`_consuma_in_ordine`,
  `calculations/forecast_engine.py`) — non più il riparto proporzionale che sul mix del consulente (sp07a 35.231 +
  sp07g 9.769) spostava sp07g a 9.551,91 invece di 8.769. Senza piano, o quando la massa cresce, il riparto resta
  proporzionale come prima; `sp07e`/`sp07f` non toccati. Nota nel wizard
  (`frontend/lib/budget-pregresso-oltre.ts::OLTRE_NOTA.crediti_commerciali`).
- **Firma del motore** — `ForecastYear.engine_meta` (`{"engine_version", "pareggio"}`) e `ENGINE_VERSION = "2"`
  (`calculations/forecast_engine.py`), scritti a ogni generazione dal Task 1 in poi; `NULL` sui previsionali
  generati prima significa «non lo so», mai un motore vecchio da segnalare.
- **Lotto 2** (report e indici: A01-bis, A02, C01-C09) resta `xfail` — fuori dal perimetro di questo lotto, dipende
  dalla firma e dal `pareggio` persistiti qui.

## Lotto 2, 2026-09-26

Fix su report e indici (`docs/superpowers/specs/2026-09-26-fix-rilievi-ambienta-design.md` §4, piano
`docs/superpowers/plans/2026-09-26-fix-rilievi-lotto2-report.md`, worktree `../budget-fix-rilievi-l2`, branch
`fix/rilievi-lotto2` da `fix/rilievi-ambienta` — lotto 1 compreso, task 1-8). `tools/triage_rilievi.py::LETTURE`
aggiornato per A01, A02, C01-C09 — «Risolto nel lotto 2 fix rilievi (2026-09-26)»; il banco
(`tests/test_rilievi_ambienta.py`) conferma: `../budget/backend/venv/bin/python -m pytest
tests/test_rilievi_ambienta.py -q -p no:warnings` → **35 passed, 0 xfailed** — nessun marcatore `xfail` residuo su
tutto il file. Suite gate completa (`BUDGET_REAL_DB=<db reale migrato>` sull'ultimo commit del lotto, `b01755c`):
**2153 passed, 6 failed, 283 skipped, 16 xfailed** — i 6 falliti sono esattamente i preesistenti elencati nei
vincoli globali del lotto, non collegati a questo giro.

- **A01-bis** — Task 1: PDF e Word del Business plan in bozza portano ora un secondo avviso,
  `engine_version_stale` (severità `error`, come `forecast_stale`), quando un `ForecastYear` porta un
  `engine_version` inferiore all'attuale — mai per l'infrannuale. In intestazione solo la forma corta
  («BOZZA · da rigenerare»: la frase intera troncherebbe il nome azienda), le frasi intere della spec una per
  riga in copertina (`BusinessPlanData.avvisi`). `engine_meta` `NULL`, o senza `engine_version`, non avvisa.
- **A02** — Task 2: il punto di pareggio degli anni di piano viene da `ForecastYear.engine_meta['pareggio']` (il
  motore), non più dalla ripartizione fissa 60/40 costi fissi/variabili; `None` con `engine_meta_missing`
  (nessun `engine_meta`) o `pareggio_non_definito` (`costi_variabili`/`costi_fissi_operativi` nulli nel motore,
  tipicamente ce05/ce06 sotto override). La colonna base/storica non è toccata.
- **C01** — Task 6: il DSCR è `(MOL − imposte) / (oneri finanziari + quota capitale rimborsata nell'anno)`, quota
  capitale da `financing.third_party_funds.decreases` del rendiconto dettagliato — non più un proxy
  (`(EBITDA - imposte) / oneri`); `None` (`cashflow_unavailable`) senza rendiconto per il periodo (prima colonna
  storica, periodi infrannuale `observed`/`adjusted`), `None` (`rimborsi_non_determinabili`) con
  `erogazioni_incoerenti`. Ogni occorrenza di "proxy" tolta dai renderer (PDF, Word, Typst).
- **C02** — Task 3: DSO sui soli crediti commerciali (`sp06a+sp07a`), non gli aggregati sp06/sp07 (che includono
  crediti tributari e diversi); DIO sul consumo di materie (`ce05+ce10`), non sul fatturato — `None` (mai zero) a
  consumo non positivo.
- **C03**/**C04** — Task 3: ROD e PFN condividono `financial_debt_total` (banche + altri finanziatori +
  obbligazioni, somma incondizionata) — prima un ramo tagliava fuori gli altri finanziatori quando c'erano già
  banche. ROD `None` (mai zero) a debito finanziario zero.
- **C05** — Task 4: un solo current ratio, quick ratio e CCN in tutto il documento
  (`attivo_corrente`/`passivo_corrente` in `calculations/report_indicators.py`, richiamate anche da `ratios.py`),
  simmetrici sui ratei: sp07 escluso dall'attivo corrente, sp18 incluso nel passivo corrente. Margine di
  tesoreria, acid test, Altman e FGPMI restano con la loro definizione di prima.
- **C06** — Task 3: l'indice di indebitamento è debiti totali / patrimonio netto (`leverage_ratio` uguale a
  `debt_to_equity`), non più immobilizzazioni/PN.
- **C07** — Task 3: la copertura delle immobilizzazioni include il TFR nel numeratore (patrimonio netto + debiti
  oltre 12 mesi + TFR).
- **C08** — Task 5: il rendiconto separa erogazioni e rimborsi quando `ForecastYear.engine_meta['erogazioni']` è
  noto (prestiti nuovi, altri finanziatori, tiraggio fidi, scoperto generato nell'anno); `erogazioni_incoerenti`
  ripiega sulla riga netta di sempre quando i dati non tornano.
- **C09** — Task 7: la frase sugli oneri finanziari sul MOL parte dalla colonna base/storica (`of_mol`) quando la
  dichiara, non più dal primo anno di piano.
- **Fix round della revisione (dentro il Task 3)** — ROD e DIO sono diventati `None` (mai zero) anche sulla
  pagina Indici (`GET .../scenarios/{id}/ratios`, che legge `FinancialRatiosCalculator` direttamente e non passa
  da `report_indicators.py`): i quattro campi (`rod`, `inventory_turnover_days`, `cash_conversion_cycle`,
  `spread`) diventano `Optional` in `ratios.py`, `schemas/calculations.py` e `frontend/types/api.ts`;
  `calculation_service.py` non li riscrive più a `0.0`. A schermo: «n.d.».
- **Un solo DSO, DIO, ROD, PFN, current/quick/CCN, indebitamento e copertura**: tutti gli scenari esistenti, non
  solo quelli generati dopo il lotto — la pagina Indici e il Business plan leggono le stesse formule di
  `calculations/ratios.py`/`report_indicators.py` a ogni richiesta, non un valore persistito.
