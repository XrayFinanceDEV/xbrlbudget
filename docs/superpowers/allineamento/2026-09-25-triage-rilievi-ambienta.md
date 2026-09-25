# Triage AMBIENTA — verdetto 2026-09-25

Commit confrontati: `62bfed1` (prima del lotto di fix) vs `HEAD` = `4b20725` (branch
`test/rilievi-ambienta`), tramite `tools/triage_rilievi.py` (worktree temporaneo su `62bfed1`
sotto `.superpowers/triage/`, rimosso a fine corsa). Foglio scritto:
`inbox/Verifica_piano_Ambienta_triage.xlsx` (l'originale `Verifica_piano_Ambienta_problemi.xlsx`
non è stato toccato).

**Base dati**: AMBIENTA 2026 locale, `FinancialYear` id 493 (ricavi 4.109.510), **non** il 2026 del
consulente (ricavi 4.209.510). Gli oracoli sono le formule del consulente applicate a questa base:
un numero atteso che nel foglio del consulente compare come "129.308" in questo banco può uscire
diverso in valore assoluto — ciò che si verifica è il *meccanismo* (la formula/il ramo di codice),
non la cifra del foglio originale.

## Controllo di raccolta (prerequisito del verdetto)

- `vecchio-pytest.xml` (su `62bfed1`): **24 testcase**, **0 `<error>`**. Nessun problema di
  collezione: la suite gira e produce pass/fail/skip veri.
- `nuovo-pytest.xml` (su `HEAD`): **24 testcase**, **0 `<error>`**.
- `vecchio-vitest.xml` / `nuovo-vitest.xml`: **3 testcase** ciascuno, nessun errore di collezione.

I verdetti sotto sono quindi validi su entrambi i lati: nessun caso di "vecchio non collezionato"
da segnalare.

**Test SKIPPED sul lato vecchio** (9 su pytest — tutti test di report, non wizard/motore):
`test_A01_bis_salvataggio_respinto_...`, `test_A02_bep_del_report_...`, `test_C01`...`test_C09`.
Motivo dello skip: `pytest.importorskip("app.renderers.business_plan.data")` /
`importorskip("backend.app.renderers.business_plan.data")` nell'helper `_bp()` — il **Business
plan ReportLab non esisteva ancora a `62bfed1`**, quindi quei moduli non sono importabili su quel
commit. Non è un errore di raccolta: è "n/a", e il verdetto lo dichiara esplicitamente
(`Confermato (n/a su 62bfed1)` / `Non riprodotto (n/a su 62bfed1)`), mai un "Risolto" derivato da
un lato che non ha mai girato.

## Tabella per test

| ID | test | 62bfed1 | HEAD | verdetto | meccanismo |
|---|---|---|---|---|---|
| A01 | `test_A01_scostamento_materie_applicato_dal_motore` (pytest) | pass | pass | Non riprodotto | il motore applica correttamente lo scostamento −5 punti sulle materie (CE Prev / dato interno) |
| A01 | `A01 lo scostamento digitato resta lo scostamento dopo un cambio dei ricavi` (vitest, wizard) | fail | fail | Confermato | `expected '-7' to be '-5'` — lo scostamento digitato è salvato come percentuale assoluta (`variableGrowthChange`), non come delta dalla crescita ricavi: quando i ricavi cambiano dopo, `variableGrowthDeviation` non lo ricalcola e lo scostamento mostrato cambia |
| A01-bis | `test_A01_bis_salvataggio_respinto_non_stampa_il_previsionale_vecchio_come_buono` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | `il PDF in bozza tace sul previsionale vecchio` — un salvataggio respinto (200, `forecast_generated: false`) lascia a schermo il previsionale vecchio, e il PDF in bozza non dice né "non aggiornat…" né "ipotesi salvate": stampa il previsionale vecchio come buono senza avviso |
| A02 | `test_A02_bep_del_report_usa_la_ripartizione_del_motore` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | costi variabili/fatturato di pareggio del report divergono da `details['pareggio']` del motore di 1.570.083,60 — il BEP del report non usa la ripartizione fissi/variabili effettiva, ma quella degli slider 60/40 di default |
| A03 | `test_A03_acconto_manuale_maggiore_di_zero_vince_sulla_percentuale` (pytest) | pass | pass | Non riprodotto | gli acconti digitati (50.000/10.000/20.000) vincono correttamente sulla percentuale |
| A03 | `A03 il passo Imposte ha un campo per anno collegato a tax_advances_paid` (vitest, wizard) | pass | pass | Non riprodotto | il campo per anno è collegato a `tax_advances_paid` |
| A04 | `test_A04_incasso_scadenziato_sui_crediti_oltre_12_mesi_arriva_allo_sp` (pytest) | fail | pass | Risolto (2026-09-24) | l'incasso scadenziato sui crediti oltre 12 mesi ora arriva correttamente allo SP (44.000 nel 2027) |
| A05 | `test_A05_immobilizzazioni_finanziarie_senza_regola_non_seguono_i_ricavi` (pytest) | pass | pass | Non riprodotto | `sp04` resta costante (52.550) sui tre anni con la regola "Manuale" e i campi vuoti: nessun override, nessuna indicizzazione implicita ai ricavi |
| A06 | `test_A06_previdenziali_seguono_il_personale_se_la_tendina_lo_dice` (pytest) | pass | pass | Non riprodotto | `sp16f` segue `ce08` (personale) quando la tendina lo dice, entro tolleranza di 1€ |
| A06 | `A06 l'etichetta dei previdenziali dice quello che fa il motore` (vitest, wizard) | pass | pass | Non riprodotto | l'etichetta di `sp16f` concorda con ciò che il motore farà (nomina "personale" solo quando la casella governa davvero) |
| B01 | `test_B01_variazione_rimanenze_del_ce_segue_lo_sp` (pytest) | fail | fail | Confermato | scarto di 22.401,33 fra `ce10_var_rimanenze_mat_prime` e la variazione reale delle rimanenze SP: nel CE la variazione resta ancorata al valore 2026, nello SP le rimanenze seguono il DIO — le due viste divergono |
| B02 | `test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo` (pytest) | fail | fail | Confermato | `assert Decimal('61040.00') == Decimal('25716.59')` — l'ammortamento dei cespiti materiali esistenti continua alla quota piena (36.040/anno) anche oltre il residuo netto, invece di fermarsi al residuo (72.796,59 − 72.080 = 716,59 nel 2029) |
| B03 | `test_B03_tfr_uguale_retribuzioni_diviso_13_5` (pytest) | fail | fail | Confermato | scarto di 12.274,75 fra `ce08a_tfr_accrual` e `ce08b_salari_stipendi / 13,5`: l'accantonamento TFR è calcolato come residuo del costo del personale (personale − salari − oneri), non come salari/13,5 |
| B04 | `test_B04_fidi_e_residui_che_non_quadrano_col_bilancio_si_rifiutano` (pytest) | pass | pass | Non riprodotto | fidi + residuo che non quadrano col debito bancario di bilancio (scarto 11.000) vengono correttamente respinti, con lo scarto nel messaggio |
| B05 | `test_B05_ultimo_anno_la_rata_successiva_sta_a_breve` (pytest) | pass | pass | Non riprodotto | la rata 2030 oltre l'orizzonte è correttamente scadenziata a breve nel 2029 quando il piano copre tutti gli anni fino alla rata |
| B05 | `test_B05_bis_rata_oltre_orizzonte_non_scadenziata` (pytest, variante) | fail | fail | Confermato *(collassa su B05, vedi «Letture»)* | `assert Decimal('300000.00') >= Decimal('353409.00')` — quando il piano di rimborso scadenzia solo 2027-2029 e resta un residuo a fine 2029, la rata dell'ultimo anno (53.409) non finisce a breve: `sp16a` resta al solo importo dei fidi |
| C01 | `test_C01_il_dscr_del_report_comprende_la_quota_capitale` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | DSCR proxy del report (3,3685) vs atteso (1,5298), scarto 1,84: il DSCR del report è (MOL−imposte)/oneri, senza la quota capitale al denominatore |
| C02 | `test_C02_dso_sui_soli_crediti_commerciali` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | DSO del report = 119 (tutti i crediti, tributari e oltre 12 mesi compresi) vs atteso 97,55 (soli crediti commerciali sp06a+sp07a) |
| C03 | `test_C03_rod_sui_debiti_finanziari` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | ROD del report 2,37% vs atteso 4,53%: il denominatore include i debiti fornitori, non i soli debiti finanziari (banche + altri finanziatori) |
| C04 | `test_C04_pfn_del_report_comprende_gli_altri_finanziatori` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | PFN del report 960.882,60 vs atteso 997.386,34: esclude gli altri finanziatori a lungo (`sp17b`), che l'interfaccia (`finDebt`) invece include |
| C05 | `test_C05_un_solo_current_ratio_nel_documento` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | Liquidità corrente sez. 8 (1,2835) ≠ Current Ratio (ILC) All. E (1,1736), scarto 0,11: due valori diversi per lo stesso indicatore nello stesso documento |
| C06 | `test_C06_indice_di_indebitamento_e_debiti_su_patrimonio` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | "Indice di Indebitamento" in All. E vale immobilizzazioni/PN (2,2446) invece di debiti totali/PN (9,3553) |
| C07 | `test_C07_copertura_immobilizzazioni_con_il_tfr` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | copertura immobilizzazioni 154,83% (report) vs 192,07% atteso: il TFR non è incluso fra le fonti consolidate (PN + debiti a lungo + TFR) |
| C08 | `test_C08_erogazioni_e_rimborsi_su_righe_separate` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | `cf_nuovo_debito` 2027 = 191.591,00 invece di 280.000: erogazione e rimborsi risultano compensati sulla stessa riga anziché su righe separate |
| C09 | `test_C09_oneri_su_mol_parte_dalla_colonna_base` (pytest, report) | skip (n/a) | fail | Confermato (n/a su 62bfed1) | il testo narrativo (`key_points`) non cita la percentuale oneri/MOL della colonna base (27,25%): parte da un'altra colonna |
| E05 | `test_E05_caratterizzazione_ammortamento_primo_anno_e_straordinari` (pytest) | pass | pass | *caratterizzazione, non verdetto* | registra lo stato attuale (aliquota piena nel primo anno di un nuovo investimento): non è un rilievo da confermare o smentire, vedi «Letture» |

## Verdetto per ID (come scritto dallo script, riga per riga)

```
A01  Confermato
A02  Confermato (n/a su 62bfed1)
A03  Non riprodotto
A04  Risolto (2026-09-24)
A05  Non riprodotto
A06  Non riprodotto
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
E05  Non riprodotto
```

(D01-D05, E01-E03 sono "Consulente", fuori dal perimetro di questo banco: lo script non scrive
un verdetto software per loro, e il foglio li lascia "Aperto".)

## Letture

- **A01**: il motore applica correttamente lo scostamento (verde, `test_A01_scostamento_...`);
  sono rossi `A01-bis` (il report stampa un previsionale vecchio dopo un salvataggio respinto senza
  dirlo — è la causa più probabile di ciò che ha visto il consulente) e il wizard (lo scostamento
  digitato è salvato come percentuale assoluta, quindi non si mantiene quando la crescita ricavi
  cambia in seguito). Nota tecnica: l'ID `A01-bis` collassa nel foglio sotto l'ID `A01` insieme al
  test del motore e a quello del wizard, perché il regex del verdetto (`[A-E]\d{2}`) prende
  "A01" anche da "A01_bis"; il verdetto per l'ID risulta quindi "Confermato" (il peggiore dei tre),
  anche se il test del motore da solo è verde — da qui la tabella per test sopra, che li separa.
- **A05**: il motore tiene `sp04` costante con i campi vuoti (verde). Indizio non verificato in
  questo banco: lo scenario AMBIENTA 25 locale ha `sp_indexing` `{"sp04": "ricavi"}` salvato; una
  schermata che mostrasse «Manuale» sopra una regola "ricavi" già salvata spiegherebbe il rilievo
  visto dal consulente, ma non è coperta da un test qui — resta un'ipotesi, non un verdetto.
- **B05 / B05-bis**: stesso ID nel foglio, due test pytest. `test_B05_ultimo_anno_la_rata_successiva_sta_a_breve`
  è verde (il piano copre tutti gli anni fino alla rata, e la rata 2030 finisce correttamente a
  breve nel 2029). `test_B05_bis_rata_oltre_orizzonte_non_scadenziata` è rosso: quando il piano di
  rimborso scadenzia solo 2027-2029 e a fine 2029 resta un residuo oltre quelle rate, la rata
  dell'ultimo anno (53.409) non viene comunque portata a breve. Il verdetto per ID collassa sul
  peggiore ("Confermato"), coerente con l'ID unico nel foglio.
- **E04**: fuori perimetro (spec §6) — nessun test in questo banco, il foglio riporta "Senza test".
- **E05**: è un test di **caratterizzazione**, non un verdetto: registra lo stato attuale
  dell'ammortamento del primo anno su un investimento nuovo (aliquota piena, non pro-rata) e degli
  oneri diversi ripetuti ogni anno, senza dichiarare se sia corretto o no. Va letto come "stato
  di oggi", non come "confermato" o "non riprodotto" nel senso degli altri ID, anche se il foglio
  (che non distingue caratterizzazioni da verdetti) lo marca "Non riprodotto" perché il test è
  verde su entrambi i lati.
- **Base**: tutti gli oracoli sono applicati su AMBIENTA 2026 locale (`FinancialYear` id 493,
  ricavi 4.109.510), non sul 2026 del consulente (ricavi 4.209.510): i valori assoluti citati sopra
  (129.308, 353.409, …) sono quelli ricalcolati su questa base con le formule del consulente, non
  le cifre del foglio originale del consulente.
