# Scadenziamento del pregresso — lotto 2: il motore separa ciò che c'è già da ciò che genera

**Data:** 2026-09-08 · **Stato:** disegno approvato a voce dal proprietario nei cinque
punti del §3, spec in revisione
**Dipende da:** `2026-09-08-percorso-ipotesi-budget-design.md` (lotto 1): usa il suo
endpoint di anteprima, il suo dict `details`, la sua `build_assumption_row`, e riempie i
controlli che quel lotto lascia spenti con badge *lotto 2* nei passi 6 e 7.
**Tocca:** `calculations/projection_common.py`, `calculations/forecast_engine.py`,
`database/models.py` + `migrate_db.py`, `backend/app/schemas/budget.py`,
`backend/app/services/assumptions_service.py`, i passi 6 e 7 del wizard.
**Non tocca:** `calculations/intra_year_engine.py` (§9).

---

## 1. Il problema

Il motore budget proietta il circolante con formule di **stock**: crediti = ricavi × DSO
/ 360, fornitori = acquisti × DPO / 360, previdenziali e altri debiti = precedente ×
(1 + %). Ogni formula **sostituisce** l'intero saldo dell'anno prima, quindi il pregresso
si presume incassato o pagato entro l'anno, sempre, e l'utente non può dire «quel credito
lo incasso in due anni» o «quel debito è rateizzato». Le voci oltre 12 mesi (`sp07`,
`sp17d/e/f/g`) si muovono solo con una percentuale a mano.

Le imposte stanno peggio: la posizione tributaria è precedente + imposte dell'anno −
acconti (`forecast_engine.py:1076-1089`, `projection_common.tax_closing_position`), con
acconti a **zero** di default. Il debito tributario generato **non viene mai pagato**: si
accumula anno dopo anno e la cassa proiettata è gonfiata di un'imposta all'anno. È un
difetto che quadra, e nessun controllo lo vede.

## 2. Obiettivo

Per i cinque saldi del circolante pregresso — crediti commerciali, debiti verso fornitori,
debiti tributari, debiti previdenziali, altri debiti — il saldo di chiusura di ogni anno
di piano è **generato + residuo del pregresso**:
- il **generato** è la formula di oggi applicata all'anno di piano;
- il **residuo** è il saldo di apertura al 31/12 dell'anno base meno gli importi che
  l'utente ha scadenziato fin lì, classificato a breve o oltre 12 mesi per scadenza.

Le imposte adottano il meccanismo reale **saldo + acconto**: nell'anno N si paga il saldo
dell'anno N−1 e gli acconti dell'anno N; il pregresso si divide fra saldo dell'anno
precedente (pagato nel primo anno) e rateizzato (con il suo piano).

Criteri di successo:
- con schema vuoto, i quattro saldi non tributari producono **gli stessi numeri di oggi**
  al centesimo (parità sulla suite `test_engine_accounting_invariants.py`);
- le imposte cambiano per tutti gli scenari a posizione tributaria automatica, e la spec
  lo dichiara (§3.2, §10): la cassa scende dell'imposta pagata, e un piano che oggi
  risulta coperto può mostrare un fabbisogno scoperto;
- ogni flusso del pregresso compare da solo nel rendiconto (che legge i delta di SP) e
  nell'anteprima del lotto 1 attraverso `details`;
- un residuo non incassato entro l'orizzonte resta a bilancio, dichiarato, mai azzerato.

## 3. Le cinque decisioni

### 3.1 Una regola per cinque saldi

| Saldo | Massa di apertura (anno base) | Generato (formula di oggi) | Righe del CE toccate |
|---|---|---|---|
| Crediti commerciali | `sp06 − sp06e − sp06f` + `sp07 − sp07e − sp07f` | `ricavi × DSO / 360` (`forecast_engine.py:943-958`) | `ce09d` per l'inesigibile |
| Debiti verso fornitori | `sp16d + sp17d` | `(ce05 + ce06) × DPO / 360` (`:1055-1065`) | — |
| Debiti tributari | `sp16e + sp17e` | saldo + acconto, §3.2 | — |
| Debiti previdenziali | `sp16f + sp17f` | `base × ce08/ce08_base` o `prev × (1+%)` (`:1093-1107`) | — |
| Altri debiti | `sp16g + sp17g` | `prev × (1+%)` (`:1090`, `:1092`) | — |

Per ogni saldo l'utente scrive un **piano**: quanto del saldo di apertura si chiude in
ciascun anno di piano, in euro (forma canonica) o in percentuale del saldo (seconda vista
della stessa cella). Il residuo dopo l'ultimo importo resta aperto.

**Regola di compatibilità.** Se per un saldo **non c'è piano** (chiave assente o `null`),
il motore usa le formule di oggi **intere**, lato breve e lato lungo: il pregresso si
chiude tutto nel primo anno, che è l'ipotesi implicita attuale. Se **c'è un piano**, il lato
breve è generato + residuo dovuto l'anno dopo, e il **lato lungo è interamente pregresso**
(residuo dovuto oltre): la percentuale di crescita di `sp07`/`sp17x` per quel saldo viene
ignorata, e `details` lo dice. Nessuna via di mezzo: un saldo è o tutto vecchio modello o
tutto nuovo.

### 3.2 Le imposte: saldo + acconto

È l'unico saldo il cui comportamento cambia **anche senza piano**, perché quello di oggi è
un difetto.

Per ogni anno di piano N, con `imposte(N)` = imposte correnti dell'anno (da
`_tax_components`, `forecast_engine.py:575-607`, le differite restano fuori come oggi):
- **acconti(N)** = `tax_advances_paid` della riga N se > 0, altrimenti
  `imposte(N−1) × acconto_pct / 100`, con `acconto_pct` di default **100** (regola italiana
  IRES/IRAP: acconto pari all'imposta dell'anno prima) e `imposte(0)` = `ce20` dell'anno
  base, l'unico dato di imposta che il consuntivo porta; `acconto_pct = 0` significa nessun acconto automatico;
- **saldo pagato in N** = debito tributario generato a fine N−1; per N = 1 è la quota
  «saldo anno precedente» del pregresso (§4), al netto del credito tributario di apertura
  `sp06e`, che lo compensa fino a capienza (l'eccedenza resta credito);
- **rate pagate in N** = l'importo del piano del rateizzato per l'anno N;
- **debito generato a fine N** = `max(0, imposte(N) − acconti(N))`;
  **credito generato a fine N** = `max(0, acconti(N) − imposte(N))`;
- `sp16e(N)` = debito generato + rate dovute in N+1; `sp17e(N)` = rate dovute oltre N+1;
  `sp06e(N)` = credito generato + eccedenza del credito di apertura non ancora usata.

Uscita di cassa dell'anno = saldo + acconti + rate, attraverso il plug come tutto il resto.

La via manuale resta: `sp06e_growth_pct` o `sp16e_growth_pct` non nulli (`:1077-1080`)
saltano tutto questo, come oggi, e un piano tributario scritto insieme a quelle
percentuali produce la diagnostica `pregresso_ignored: debiti_tributari`.

`projection_common.tax_closing_position` **non cambia**: la usa l'infrannuale (§9). Il
nuovo calcolo è una funzione nuova, `tax_settlement_saldo_acconto(...)`, chiamata solo dal
motore budget.

### 3.3 Scadenza per costruzione

Alla chiusura dell'anno N: la parte del residuo pregresso **dovuta in N+1** sta a breve
(`sp06`, `sp16x`); il resto sta oltre 12 mesi (`sp07`, `sp17x`). Nell'ultimo anno di
piano tutto il residuo non scadenziato è oltre: non c'è un «anno dopo» nel piano, e il
motore non inventa scadenze. È la regola che manda da sole le rate tributarie oltre
l'anno in `sp17e`, e un credito non incassato entro l'orizzonte in `sp07`.

I sotto-campi di `sp06`/`sp07` continuano a essere ripartiti a valle dal totale sulle
proporzioni dell'anno base (`_alloc`, `forecast_engine.py:1248-1298`); i sotto-campi di
`sp16`/`sp17` sono già calcolati uno per uno.

### 3.4 L'inesigibile è una svalutazione crediti

Il piano dei crediti ammette, per anno, un importo **inesigibile**: riduce il residuo e va
in `ce09d_svalutazione_crediti` di quell'anno. Oggi `ce09d` è la copia dell'anno base
(`:743`), e resta tale: `ce09d(N) = ce09d_base + inesigibile(N)`, salvo `ce09d_override`.
Non c'è un fondo svalutazione nel modello (`sp14` ha solo quiescenza, imposte, derivati,
altri): si resta al netto. La svalutazione riduce l'utile e il patrimonio; la cassa non
cambia rispetto a un residuo lasciato aperto, salvo l'effetto fiscale.

### 3.5 Il piano vive nella riga del primo anno

Colonna nuova `BudgetAssumptions.pregresso` (`JSON`, nullable), valida **solo sulla riga
del primo anno di piano**, esattamente come `financing_loans[].opening_residual`
(`forecast_engine.py:450-454`): su un'altra riga il motore alza
`pregresso is allowed only in the first forecast year`. Ogni saldo dichiara il proprio
`opening`: se differisce dalla massa di apertura letta dal bilancio base (tolleranza
0,01 €) il motore si ferma con «il saldo di apertura di {voce} è cambiato ({dichiarato}
→ {base}): rivedi lo scadenziamento», invece di scadenziare un numero che non esiste più.

Un piano vuoto per gli scenari già salvati è la colonna a `NULL`: nessuna ricostruzione
del database, una riga in `migrate_db.py` (`MIGRATIONS["budget_assumptions"]`).

## 4. Il modello dati

```json
{
  "crediti_commerciali":  { "opening": 422000.00, "amounts": [380000.00, 30000.00], "writeoff": [12000.00, 0] },
  "debiti_fornitori":     { "opening": 322000.00, "amounts": [322000.00] },
  "debiti_tributari":     { "opening": 96000.00, "saldo": 61000.00, "rateizzato": 35000.00,
                            "amounts": [11667.00, 11667.00, 11666.00], "acconto_pct": 100 },
  "debiti_previdenziali": { "opening": 41000.00, "amounts": [41000.00] },
  "altri_debiti":         { "opening": 58000.00, "amounts": [58000.00] }
}
```

- `amounts[i]` è l'importo chiuso nell'anno di piano i (0 = primo anno); per
  `debiti_tributari` riguarda il solo rateizzato, il saldo è pagato nel primo anno per
  definizione. Lunghezza ≤ orizzonte; importi ≥ 0; somma ≤ massa (per i crediti
  `amounts + writeoff` ≤ `opening`; per le imposte `saldo + rateizzato = opening` al
  centesimo e `Σ amounts ≤ rateizzato`). Superare la massa è un errore, non un
  troncamento: incassare più di quanto c'è inventa cassa.
- Una chiave assente o `null` vale «nessun piano» (§3.1); per `debiti_tributari` vale
  «tutto saldo, niente rateizzato, acconto 100%».
- Pydantic: `PregressoInput` con cinque sotto-modelli tipizzati, validazioni di forma
  (segno, lunghezza) nello schema, validazioni di massa nel motore, dove c'è il bilancio
  base. Persistito con `jsonable_encoder` come gli altri tre JSON
  (`assumptions_service.py:139-168`) attraverso `build_assumption_row` del lotto 1, così
  bulk e anteprima lo trattano allo stesso modo.
- `tax_advances_paid` (per anno, esistente) cambia lettura ma non forma: da «riduce il
  debito di fine anno» a «acconti dell'anno, se > 0 vincono sull'automatico». Le righe
  esistenti valgono 0 → automatico. Il default `0` dello schema resta.

## 5. Il motore

### 5.1 Kernel (`projection_common.py`)

```python
@dataclass
class RunoffYear:
    opening: Decimal; closed: Decimal; writeoff: Decimal
    residual: Decimal; residual_short: Decimal; residual_long: Decimal

def runoff_schedule(opening, amounts, writeoff, year_index, horizon) -> RunoffYear
def tax_settlement_saldo_acconto(opening_credit, saldo_due, rate_due, current_tax,
                                 previous_tax, acconto_pct, explicit_advances) -> TaxYear
```

`runoff_schedule` è pura: residuo dopo l'anno `year_index`, e la sua divisione breve/oltre
secondo §3.3 (`residual_short = amounts[year_index+1]` se esiste, altrimenti 0). `TaxYear`
porta saldo pagato, acconti pagati, rate pagate, debito e credito generati, credito di
apertura residuo. Entrambe hanno test unitari propri.

### 5.2 Orchestrazione (`forecast_engine.py`)

- In `load_forecast_source` (lotto 1): lettura di `pregresso` dalla prima riga, controllo
  della riga, controllo delle masse di apertura contro `base_bs`, controllo delle somme.
  Ogni violazione è `ValueError` prima del ciclo → `error.year = null` nell'anteprima.
- In `_calculate_balance_sheet`, per ogni saldo con piano: sostituisce il lato breve con
  generato + `residual_short` e il lato lungo con `residual_long`; per i crediti
  `sp06_trade` e `sp07_trade` sono le masse trattate, `sp06e/f` e `sp07e/f` restano
  fuori. Per le imposte, il blocco `:1071-1089` viene sostituito da
  `tax_settlement_saldo_acconto` sotto lo stesso `manual_tax_position`.
- In `_calculate_income_statement`: `ce09d` secondo §3.4.
- Il plug di cassa (`:1196-1223`) e il gate `Unfunded financing requirement` non
  cambiano: i flussi del pregresso vi passano come tutto il resto.

### 5.3 `details` dichiarati (estensione del dict del lotto 1)

Per anno, sempre presenti, anche a zero:
- `pregresso.{saldo}`: `opening`, `closed`, `writeoff`, `residual_short`,
  `residual_long`, `generated`, `mode` (`"legacy"` senza piano, `"runoff"` con piano);
- `imposte`: `current_tax`, `saldo_paid`, `acconti_paid`, `rate_paid`, `generated_debt`,
  `generated_credit`, `opening_credit_left`, `mode` (`"saldo_acconto"` | `"manual"`);
- `pregresso_ignored`: elenco dei saldi con piano scritto ma scavalcato dalla via
  manuale (oggi solo `debiti_tributari`).

Il rendiconto continua a leggere i delta di `sp06`/`sp16` aggregati
(`backend/app/calculations/cashflow_detailed.py:179-199`): i flussi del pregresso vi
compaiono da soli, dentro «crediti» e «debiti». Una riga «imposte pagate» separata è
fuori ambito; `details.imposte` la rende possibile a chi la vorrà.

## 6. L'interfaccia (passi 6 e 7 del lotto 1)

**Passo 6 — Scadenziamento del pregresso.** La colonna di sinistra riceve, sotto le righe
dei debiti finanziari, una tabella con quattro righe — crediti commerciali, debiti verso
fornitori, debiti previdenziali, altri debiti — e per ciascuna: il saldo di apertura, una
cella per anno di piano, e il **residuo** calcolato accanto. Un interruttore per la
tabella sceglie se le celle si scrivono in euro o in percentuale del saldo; la forma
canonica salvata è l'euro. Sotto la riga dei crediti, una riga «di cui inesigibile» per
anno, chiusa di default. Una riga vuota vale «tutto nel primo anno» e lo dice in
segnaposto. La riga «debiti tributari» rimanda al passo 7. L'anteprima del passo mostra,
per ogni saldo con piano, residuo a breve e oltre; l'avviso di fabbisogno scoperto è già
del lotto 1.

**Passo 7 — Pagamento dei debiti tributari.** La card spenta del lotto 1 si accende:
saldo di apertura `sp16e + sp17e`; due campi «saldo dell'anno precedente» e
«rateizzato», il secondo calcolato come differenza; il piano delle rate per anno con la
scorciatoia «N rate uguali» (compila importi uguali, l'ultimo assorbe i centesimi);
«acconto sull'imposta dell'anno prima» in percentuale, default 100, con la chiosa che gli
acconti per anno della riga sopra (`tax_advances_paid`) lo scavalcano quando valorizzati.
Anteprima: imposte correnti, saldo pagato, acconti pagati, rate pagate, debito e credito
a fine anno, con la colonna base.

Nessuna vista nuova, nessuna voce nuova nel catalogo IV-CEE: `sp06`, `sp07`, `sp16x`,
`sp17x` esistono già in tutti gli elenchi.

## 7. Migrazione e compatibilità

- `database/models.py`: `pregresso = Column(JSON, nullable=True)`; `migrate_db.py`:
  `("pregresso", "JSON")` sotto `budget_assumptions`.
- Scenari già salvati: `pregresso = NULL` ⇒ quattro saldi identici a oggi; imposte a
  saldo + acconto con acconto 100% ⇒ **numeri diversi** (cassa più bassa, `sp16e` più
  basso, possibile fabbisogno scoperto). Va detto nel rilascio e nella pagina: il primo
  salvataggio dopo l'aggiornamento mostra nell'anteprima del passo 7 la differenza.
- Idratazione frontend: `pregresso` entra nella mappa idratata e viene rispedito intero
  (delete-all + reinsert del bulk, lotto 1 §6).

## 8. Test

**Kernel** (`tests/test_projection_common_runoff.py`):
- `runoff_schedule`: piano vuoto → tutto chiuso nel primo anno; 80/20 → residuo 20% a
  breve dopo l'anno 1, 0 dopo l'anno 2; piano più corto dell'orizzonte → residuo oltre
  nell'ultimo anno; inesigibile riduce il residuo senza contare come incasso; somma >
  massa → errore.
- `tax_settlement_saldo_acconto`: acconto 100% e imposta costante → debito generato 0 e
  uscita di cassa = imposta; imposta in calo → credito generato; credito di apertura
  compensa il saldo fino a capienza; `explicit_advances` scavalca la percentuale.

**Motore** (`tests/test_budget_pregresso.py`, con `tests/e2e_kit.py`):
1. *Punto fisso*: scenario senza piano, posizione tributaria manuale → CE e SP identici a
   prima del lotto, al centesimo, su 5 anni.
2. *Conservazione*: su un piano completo, `Σ (saldo + acconti + rate) pagati` in N anni =
   pregresso tributario + `Σ imposte(y)` − debito generato finale + credito finale.
3. *Scadenza*: rateizzato in 3 rate → dopo l'anno 1 `sp16e` contiene la rata 2, `sp17e`
   la rata 3; dopo l'anno 2 `sp17e = 0`.
4. *Crediti*: 80/20 → `sp06_trade(1) = ricavi × DSO/360 + 20% apertura`; la cassa
   dell'anno 1 è più bassa dello stesso 20% rispetto al piano vuoto.
5. *Inesigibile*: `ce09d` sale dell'importo, il residuo scende, l'attivo quadra.
6. *Errori*: piano su una riga non prima; apertura dichiarata diversa dal base; somma oltre
   la massa; `saldo + rateizzato ≠ opening`.
7. *Anteprima*: `details.pregresso` e `details.imposte` presenti in ogni anno, `mode`
   coerente; `pregresso_ignored` valorizzato quando la via manuale scavalca.
8. *Stress*: `test_numeric_stress_cycle.py` esteso con un piano su tutti e cinque i saldi,
   esatto al centesimo su 5 anni.
9. *Infrannuale*: le quattro suite `test_intra_year_*` e `test_infrannuale_dual_year.py`
   passano invariate.

**Frontend** (Vitest, node): `lib/budget-pregresso.ts` puro — conversione euro ↔ % sul
saldo, residuo, «N rate uguali» con i centesimi sull'ultima, validazione di forma prima
dell'invio.

## 9. Fuori ambito e note

- **Infrannuale invariato.** Crediti e fornitori lì non sono guidati da DSO/DPO ma da
  rotazioni sull'anno di riferimento (`intra_year_engine.py:980-996`), i sotto-campi da
  `_distribute_sp06` e gemelli, la posizione tributaria da `tax_closing_position` che
  resta com'è. Portarvi lo scadenziamento richiede prima di unificare i **due costruttori
  di bilancio duplicati** (`_project_balance_sheet` a `:1011` e
  `_project_balance_sheet_annualized` a `:1314`, con i due gemelli del CE a `:659` e
  `:846`): vedi la nota `docs/superpowers/2026-09-08-nota-costruttori-sp-infrannuale.md`.
- **Rendiconto**: nessuna riga «imposte pagate» separata (§5.3).
- **Fondo svalutazione crediti**: non esiste nel modello e non viene introdotto (§3.4).
- **Piani oltre l'orizzonte**: non si scrivono; il residuo resta dichiarato oltre.

## 10. Documentazione da aggiornare nello stesso lotto

- `CLAUDE.md` › Invarianti › Previsionale: «le imposte si pagano a saldo + acconto, il
  debito generato in N esce in N+1»; «`pregresso` vive solo nella riga del primo anno e
  dichiara la massa di apertura»; «un saldo con piano ha il lato lungo interamente
  pregresso: la sua % di crescita oltre viene ignorata»; § Forecasting Engine: il
  circolante è generato + residuo.
- `docs/budget/API-PREVISIONALE.md`: il campo `pregresso`, le validazioni, i `details`.
- `docs/budget/FORECASTING_GUIDE.md`: già superato in più punti; o si riscrive la sezione
  circolante e imposte, o si marca come storico. Da decidere nel piano.
- `docs/frontend/PRATICA-PERCORSO.md`: i passi 6 e 7 completi.

## 11. Due difetti preesistenti aggiunti a questo lotto (decisione del proprietario, 2026-09-09)

Trovati durante il lotto 1 — il primo estraendo i contratti del motore, il secondo al
collaudo col browser. Entrambi **preesistenti su `main`**, quindi non hanno bloccato il
merge del lotto 1; entrano qui perché toccano esattamente ciò che questo lotto rimette in
discussione: il confine fra ciò che il previsionale genera e ciò che è già a bilancio.

### 11.1 Un `sp_overrides` può persistere una CASSA NEGATIVA sotto un esito di successo

`_apply_sp_overrides` (`calculations/forecast_engine.py:466-468`) clampa la cassa con
`max(0, …)`, ma `_normalize_balance_sheet_cents(recompute_cash=True)` (`:344-351`) gira
**dopo** — chiamata a `:584` sul risultato di `:1553` — e ricalcola
`sp09 = passivo − attivo_senza_cassa` **senza clamp e senza sollevare**. Il clamp viene
scavalcato dal passaggio successivo.

Contraddice due invarianti dichiarati in `CLAUDE.md`: «la cassa plugga solo verso l'alto,
un plug negativo fa **sollevare** il motore» e «`sp_overrides` clampa a zero i negativi —
non dà errore, dà uno zero». Sul percorso **con** override non vale nessuna delle due.
A valle avvelena current ratio, PFN, circolante di Altman e liquidità FGPMI, che vengono
calcolati su un numero aritmeticamente impossibile senza un avviso.

Riproduzione misurata (`source backend/venv/bin/activate && PYTHONPATH=. python3`):

```python
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year
from backend.app.services import assumptions_service
from database.models import BudgetScenario

engine, Session = memory_sessions()
db = Session()
cid, _ = seed_base_year(db, user_id="plug")
sc = BudgetScenario(company_id=cid, name="plug", base_year=2026, scenario_type="budget")
db.add(sc); db.commit()

# Un override che SQUILIBRA il foglio: rimanenze gonfiate senza contropartita.
rows = [{"forecast_year": 2027, "revenue_growth_pct": 5.0,
         "sp_overrides": {"sp05_rimanenze": 5000000}}]
res = assumptions_service.bulk_upsert_assumptions(db, sc.id, rows, auto_generate=True)
print(res.get("forecast_generated"), res.get("message"))   # True, «...generated successfully»
for year, sp, _ce in read_forecast_maps(db, sc.id):
    print(year, sp["sp09_disponibilita_liquide"])           # 2027  -4779777.78
```

**Che cosa deve fare la correzione**: la cassa non può uscire negativa da nessun percorso.
O il ricalcolo finale rispetta lo stesso cancello del plug — e allora un override che
squilibra il foglio **solleva** come un fabbisogno scoperto — oppure lo squilibrio viene
**dichiarato** in `details` e l'interfaccia lo mostra. Quello che non è ammissibile è il
comportamento di oggi: un numero impossibile, persistito, sotto un messaggio di successo.
Vale la regola di casa: *diagnose, never fabricate*.

### 11.2 Dopo un salvataggio respinto, CE Prev. e SP Prev. mostrano il previsionale vecchio senza dirlo

Il bulk risponde **200 anche a un previsionale rifiutato**: le ipotesi restano salvate, il
`ForecastYear` no. Il wizard del lotto 1 gestisce bene il proprio caso — toast rosso, nessun
atterraggio su CE Prev., ritorno al passo dell'errore — ma se l'utente esce dalla barra di
navigazione in alto, **CE Prev., SP Prev., Riclassificato, Rendiconto e Report mostrano i
numeri del previsionale precedente** senza alcun segnale che non riflettano le ipotesi
salvate.

Misurato al collaudo: con `investments = 200.000.000` persistito per il 2025 e la
generazione respinta, `/analysis` restituisce ancora i tre anni con i numeri della baseline,
identici; nessuna stringa di avviso in pagina.

**Che cosa deve fare la correzione**: serve un modo per sapere che il `ForecastYear`
mostrato è **più vecchio** delle `BudgetAssumptions` salvate, e un indicatore su quelle
viste. Sta in questo lotto perché il lotto 2 introduce comunque nuove ragioni di rifiuto
(un piano di scadenziamento incapiente), quindi la frequenza del caso aumenta.
