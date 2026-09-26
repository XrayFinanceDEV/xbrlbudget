# Fix dei rilievi AMBIENTA confermati dal triage — design

**Data:** 2026-09-26 · **Branch:** `fix/rilievi-ambienta` (worktree `../budget-fix-rilievi`, da `test/rilievi-ambienta` 8eaffab)
**Viene da:** triage `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md` (banco `tests/test_rilievi_ambienta.py`,
`frontend/lib/rilievi-ambienta.test.ts`, verdetto `tools/triage_rilievi.py`).

## 1. Perché

Il triage ha confermato 18 rilievi del consulente su motore, report e wizard (A01-bis, A02, A04, B01, B02, B03, B05,
C01–C09) e ne ha lasciati tre alla decisione del proprietario (A05, A06 doppio comando, E05). Il proprietario ha deciso
il 2026-09-26 (§3). Ogni fix ha già il suo oracolo: il test del triage marcato `xfail(strict=True)`. Un fix è finito
quando il suo test passa **e** il marcatore è tolto; un test il cui oracolo contraddice una decisione del proprietario si
riscrive su quella decisione, nello stesso commit, dicendolo.

## 2. Tre lotti, in quest'ordine

| Lotto | Perimetro | Dipende da |
|---|---|---|
| 1 · Motore | B01, B02, B03, B05, A04, E05, firma del motore e `pareggio` persistiti | — |
| 2 · Report e indici | A01-bis, A02, C01–C09 | lotto 1 (firma, `pareggio`) |
| 3 · Wizard | A05, A06 | — |

Un piano per lotto. I lotti 1 e 2 cambiano numeri che l'utente legge: ogni cambiamento di numero su scenari esistenti è
voluto e va dichiarato in CLAUDE.md/doc nello stesso lotto.

## 3. Decisioni

### Lotto 1 — motore (`calculations/forecast_engine.py`, `calculations/projection_common.py`)

- **B01 rimanenze.** `ce10_var_rimanenze_mat_prime` di ogni anno = −(`sp05a` fine − `sp05a` inizio) (convenzione OIC B11:
  un aumento delle rimanenze di materie riduce il costo), non più il valore della base. Il DIO si calcola sul **consumo di
  materie** (`ce05` + `ce10`), non sui ricavi, per le sole materie (`sp05a`); le altre rimanenze (`sp05b`–`sp05e`) restano
  come oggi. Un override di `ce10` vince, come ogni override di CE.
- **B02 ammortamenti.** Il valore netto dei cespiti esistenti e quello dei nuovi investimenti si tengono separati per
  categoria (materiali, immateriali). La quota dei cespiti esistenti = min(quota della base, residuo esistente); la quota
  dei nuovi = somma per investimento. Dichiarato in `details['ammortamenti']`.
- **E05.** Un nuovo investimento si ammortizza a **metà aliquota** nell'anno in cui entra, piena dopo. Proventi e oneri
  straordinari (`ce18`, `ce19`) valgono **zero** in ogni anno di piano, salvo override.
- **B03 TFR.** `ce08a` = `ce08b` / 13,5 (la formula che il wizard dichiara, `tfr_accrual_quota`). `ce08d` altri costi del
  personale = `ce08` − `ce08b` − `ce08c` − `ce08a`; se viene negativo, `ce08d` = 0 e `ce08` si ricompone come somma, con
  una diagnostica dichiarata.
- **B05.** Nell'ultimo anno di piano, un contratto con residuo e senza rata scadenziata per l'anno dopo porta a breve
  min(residuo, ultima rata scadenziata), dichiarato in `details['debito_bancario']['contratti']`.
- **A04.** L'incasso della massa «oltre 12 mesi» dei crediti commerciali consuma prima `sp07a` (clienti) e poi le altre
  sotto-voci, invece del riparto proporzionale; il wizard lo dice nella nota del passo 5. Il test del triage sul riparto
  misto si riscrive su questa regola (l'oracolo del consulente — «scende la voce altri crediti» — è superato dalla decisione).
- **Firma e pareggio persistiti.** `ForecastYear` guadagna una colonna JSON `engine_meta` = `{"engine_version": <str>,
  "pareggio": <details['pareggio']>}`, scritta a ogni generazione; migrazione in `migrate_db.py`. `engine_version` è una
  costante in `forecast_engine.py` che si incrementa a ogni cambiamento di numeri del motore (questo lotto la porta a 2).
  I previsionali esistenti hanno `NULL`: nessuna firma = «non lo so», non un verdetto (§Invarianti).

### Lotto 2 — report e indici (una definizione per indice)

- **A01-bis.** PDF e Word del Business plan in bozza portano un avviso (copertina e intestazione) quando il report ha la
  diagnostica `forecast_stale` o quando `engine_meta.engine_version` è minore della versione corrente: «Previsionale
  precedente alle ipotesi salvate: da rigenerare» / «Previsionale generato da una versione precedente del motore: da
  rigenerare». Lo scarico non si blocca. /report mostra lo stesso avviso.
- **A02.** Il BEP del report legge `engine_meta.pareggio` per gli anni di piano; la colonna base resta come oggi. Niente
  più ripartizione 60/40 nel report.
- **C01.** Resta un solo indicatore, **DSCR** = (MOL − imposte) / (oneri finanziari + quota capitale rimborsata
  nell'anno). La quota capitale viene dai piani dei finanziamenti (`details['debito_bancario']` e altri finanziatori). Il
  «DSCR (proxy)» sparisce da tabelle, grafici, testi e soglie; i testi della sintesi si riscrivono sul DSCR vero.
- **C02.** DSO = (`sp06a` + `sp07a`) / ricavi × 360; DPO sui soli fornitori (già così); DIO sulle rimanenze / consumo.
- **C03, C04.** Un solo perimetro di debito finanziario = banche + altri finanziatori + obbligazioni, breve e lungo. PFN
  = quel perimetro − cassa (e attività finanziarie a breve se il report le conta già); ROD = oneri / quel perimetro. La
  stessa funzione serve report, Indici e wizard (`budget-piano-step.ts` resta la ricapitolazione a schermo, allineata).
- **C05.** Un solo current ratio = (rimanenze + crediti a breve + attività finanziarie a breve + liquidità + ratei attivi)
  / (debiti a breve + ratei passivi); quick ratio = lo stesso senza rimanenze. CCN simmetrico sui ratei. Stessa formula
  nella sezione 8 e nell'Allegato E.
- **C06.** «Indice di indebitamento» = debiti totali / PN.
- **C07.** Copertura immobilizzazioni = (PN + debiti a lungo + TFR) / immobilizzazioni.
- **C08.** Il rendiconto espone **erogazioni** e **rimborsi** dei debiti finanziari su righe separate: erogazioni = nuovi
  finanziamenti dell'anno dai piani (più tiraggi di fidi), rimborsi = erogazioni − Δ debito finanziario. Niente più netto.
  La sintesi cita i rimborsi di ogni anno di piano.
- **C09.** Il testo oneri finanziari/MOL parte dalla colonna base.

### Lotto 3 — wizard

- **A05.** Passare una voce a «Manuale» scrive in `sp_overrides` il **saldo dell'anno base**, costante in ogni anno, non i
  valori della regola precedente. Il test esistente `budget-sp-manuale.test.ts` («congela i valori dell'anteprima») si
  riscrive su questa decisione.
- **A06.** Resta la sola tendina; la casella «Debiti previdenziali scalano col costo del personale» sparisce. Migrazione
  una tantum: gli scenari con `previdenza_scales_with_personnel = true` ricevono `sp_indexing.sp16f = sp_indexing.sp17f =
  "personale"` e il flag torna `false`. Il motore smette di leggere il flag (il campo resta nel modello per compatibilità).

## 4. Verifica

- Per lotto: i test del triage del suo perimetro passano senza marcatore; nessun altro test del banco cambia stato; suite
  del motore/report/frontend verdi (`pytest` sui file toccati + `npx vitest run` + `npx tsc --noEmit` + `npm run build`
  quando si tocca il frontend).
- Ogni numero che cambia su scenari esistenti ha un test che lo fissa e una riga di documentazione.
- Alla fine di ogni lotto, `tools/triage_rilievi.py` rieseguito: le letture fisse (`LETTURE`) dei rilievi chiusi si
  aggiornano a mano.

## 5. Fuori perimetro

Parte D ed E01–E03 (consulente); E04 (base IVA): solo una nota nel passo Circolante del wizard, se costa poco, altrimenti
rinviata; i test del triage non toccati da un lotto restano `xfail`.
