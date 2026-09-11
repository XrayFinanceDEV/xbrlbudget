# Le API del previsionale — ipotesi, override, generazione, promote

Quattro superfici scrivono su uno scenario e ne rigenerano il previsionale. Falliscono in
**tre modi diversi**, e uno dei tre non si vede: è la ragione principale per cui questa pagina
esiste.

| Chiamata | Che cosa scrive | Come fallisce |
|---|---|---|
| `PUT /companies/{id}/scenarios/{sid}/assumptions` | tutte le righe di ipotesi dello scenario | **HTTP 200 anche quando il previsionale è rifiutato** |
| `PATCH /companies/{id}/scenarios/{sid}/ce-override` | solo le colonne `ce*_override` indicate | 400 / 404 / 500 |
| `POST /companies/{id}/scenarios/{sid}/generate` | niente (rigenera; con `?clear_overrides=true` azzera prima) | 400 / 500 |
| `PUT .../assumptions/{year}` (per anno, «deprecata») | una riga sola — **è la via con cui `/forecast/balance` salva gli `sp_overrides`** | 4xx |

## 1. Il bulk delle ipotesi, e il suo 200 bugiardo

```jsonc
PUT /companies/{id}/scenarios/{sid}/assumptions
{
  "assumptions": [
    { "forecast_year": 2025, "revenue_growth_pct": 5.0, "...": "..." },
    { "forecast_year": 2026, "revenue_growth_pct": 4.0, "...": "..." }
  ],
  "auto_generate": true
}
```

Con `auto_generate: true` il servizio sceglie il motore dal `scenario_type`
(`IntraYearEngine` per `infrannuale`, `ForecastEngine` altrimenti) e lo esegue. Se il motore
solleva — per il gate semantico sulla fonte, per ricavi di base negativi, per qualunque
ragione — l'eccezione viene **catturata** e la risposta è ugualmente **200**
(`backend/app/services/assumptions_service.py:322-331`):

```jsonc
{ "success": true, "assumptions_saved": 2,
  "forecast_generated": false,
  "forecast_years": [2025, 2026],
  "message": "Assumptions saved successfully, but forecast generation failed: ..." }
```

Due dettagli che si sbagliano facilmente:

- `success` resta `true`: si riferisce al **salvataggio delle ipotesi**, che è davvero
  avvenuto e committato prima del tentativo di generazione.
- `forecast_years` **non è vuoto**: è l'elenco degli anni delle ipotesi salvate, non degli
  anni previsionali prodotti. A restare vuoto è `analysis.forecast_years` della successiva
  `GET /analysis`. Chi controlla `forecast_years.length` invece di `forecast_generated`
  non si accorge di nulla.

I tre chiamanti in `frontend/` controllano `forecast_generated === false` e mostrano un
`toast.warning` col `message`: `app/budget/page.tsx:991-994`, `app/pratica/page.tsx:801`
(`calculateProjectedBS`) e `:895` (`saveProjection12M`). Un quarto chiamante che se ne
dimenticasse dipingerebbe una colonna Proiezione vuota sotto un toast verde.

### 1.1 `forecast_stale` — il previsionale mostrato è più vecchio delle ipotesi

Se l'utente esce dal wizard invece di leggere il toast, o è passato dal percorso
`auto_generate=false`, le pagine successive (CE Prev., SP Prev., Riclassificato, Rendiconto,
Report) continuavano a mostrare i numeri della generazione **precedente**, senza alcun segnale.
`GET /companies/{id}/scenarios/{sid}/analysis` porta ora tre campi per questo
(`backend/app/services/analysis_service.py:211-260`, `_forecast_staleness`):

| Campo | Valore |
|---|---|
| `forecast_stale` | `true` quando l'ultima scrittura delle `BudgetAssumptions` è **successiva** all'ultima generazione riuscita del `ForecastYear`. Dichiarato **sempre**, anche `false`: una chiave assente varrebbe zero, cioè "allineato" — tacere sarebbe dichiararsi puliti senza averlo controllato. Nessun `ForecastYear` **o** nessuna ipotesi ⇒ `false`: un controllo che manca è "non lo so", mai un verdetto negativo. |
| `assumptions_updated_at` | ISO 8601 in **UTC esplicito con la `Z`**, o `null` se non ci sono ipotesi. |
| `forecast_updated_at` | ISO 8601 in **UTC esplicito con la `Z`**, o `null` se non è mai stato generato nulla. |

Le colonne sorgente sono `datetime.utcnow()` **ingenuo** (nessun fuso in colonna): il servizio
aggiunge la `Z` a mano dopo aver normalizzato un eventuale timestamp con fuso in UTC. Ometterla
farebbe leggere il valore come ora **locale** da `Date.parse` — misurato: `08:00` diventerebbe
`06:00Z` in Europe/Rome. Il confronto che decide `forecast_stale` è sugli **istanti** `datetime`,
non sulle stringhe: `isoformat()` omette la frazione quando i microsecondi sono zero, e l'ordine
lessicografico di `"…00Z"` rispetto a `"…00.500000Z"` è l'inverso di quello dei due istanti.

`POST /generate`, per contrasto, **non** cattura: fa 400 su `ValueError` e 500 su tutto il
resto (`backend/app/api/v1/budget_scenarios.py:936-945`). Lo stesso motore, lo stesso errore,
due esiti HTTP opposti a seconda della porta da cui si è entrati.

## 2. Gli override: due meccanismi, non uno

### 2.1 Conto economico — 32 colonne `ce*_override`

`BudgetAssumptions` porta **32** colonne `ce*_override` (`database/models.py:703-736`), non 31:
`ce01`–`ce20` meno `ce17` (sostituito dalle sue due sotto-voci), più `ce03a` (incrementi di
immobilizzazioni per lavori interni, A.4), `ce08a`–`d`, `ce09a`–`d`, `ce11b`, `ce17`, `ce17a`,
`ce17b`. Lo stesso insieme di 32 compare in `backend/app/schemas/budget.py` (due volte),
nell'allowlist `CE_OVERRIDE_FIELDS` di `backend/app/services/assumptions_service.py` e nella
mappa `FIELD_TO_OVERRIDE` di `frontend/app/forecast/income/page.tsx:72`.

Ogni colonna è un **valore assoluto in euro**. `NULL` = usa il calcolo del motore.
`ce20_override` fissa le imposte totali e scavalca `tax_rate` (`forecast_engine.py:2115-2116`,
`intra_year_engine.py:271-272`); `ce17a_override`/`ce17b_override` sono letti separatamente,
**non** come netto in `ce17_override` (`forecast_engine.py:2341-2342`).

Il batch:

```jsonc
PATCH /companies/{id}/scenarios/{sid}/ce-override
{ "overrides": [
    { "forecast_year": 2026, "field": "ce01_override", "value": 1750000 },
    { "forecast_year": 2026, "field": "ce05_override", "value": null }
] }
→ { "success": true, "applied": 2 }
```

`value: null` azzera l'override e restituisce la riga al motore. Un `field` fuori
dall'allowlist è **400**, un anno senza riga di ipotesi è **404**, e la rigenerazione avviene
una volta sola alla fine — **nella stessa transazione del salvataggio**
(`assumptions_service.apply_ce_overrides`). Se la rigenerazione fallisce, lo status **dipende dal
motivo** (`budget_scenarios.py:826-835`, `patch_ce_override`): un rigetto di dominio del motore —
`ValueError`, il caso reale nella stragrande maggioranza (`Unfunded financing requirement`, un
override incompatibile con lo scoperto, ecc.) — risponde **400**; solo un'eccezione davvero
inattesa (un bug, non un rifiuto legittimo dell'ipotesi) risponde **500**. In ENTRAMBI i casi
**nessuno** degli override del lotto resta scritto: `db.rollback()` disfa tutto cio' che la
chiamata aveva applicato, quindi una `GET` successiva legge le ipotesi esattamente come prima
del tentativo. Prima di questa correzione gli override venivano committati **prima** di provare
a rigenerare: un fallimento li lasciava comunque scritti, e si applicavano (facendo fallire di
nuovo, con lo stesso errore) alla prima rigenerazione successiva — invisibile all'utente, perché
il client scarta la modifica rifiutata e mostra il previsionale vecchio.

Su `/forecast/income` il ciclo è: clic sulla cella previsionale → input in linea → `blur`/Enter
mette la modifica in `pendingEdits` (**sfondo giallo + sottolineatura gialla**) → compare
«Aggiorna Previsionale» → il clic manda tutto in un `PATCH` solo, invalida la cache di
`/analysis` e ricarica. Una cella svuotata manda `null`. Un override **già persistito** si
riconosce da una sottolineatura `border-b-2 border-primary` — il colore del tema, non un blu
fisso — e lo stato si legge dall'oggetto `assumptions` della risposta di `/analysis`
(`app/forecast/income/page.tsx:508-527, 546-551`).

### 2.2 Stato patrimoniale — il sacco JSON `sp_overrides`

`BudgetAssumptions.sp_overrides` è una colonna **JSON** (`models.py:700`), un dizionario
`{campo_sp: valore}`. Non è un residuo: `/forecast/balance` è **editabile** e la scrive
(`frontend/app/forecast/balance/page.tsx:153-158`), in un lotto UNICO che può toccare **più
anni in una sola chiamata**:

```jsonc
PATCH /companies/{id}/scenarios/{sid}/sp-override
{ "overrides": [
    { "forecast_year": 2026, "field": "sp16a_debiti_banche_breve", "value": 400000.55 },
    { "forecast_year": 2027, "field": "sp16a_debiti_banche_breve", "value": 350000.00 },
    { "forecast_year": 2026, "field": "sp06a_crediti_clienti_breve", "value": null }
] }
→ { "success": true, "years": 2 }
```

entrambi i motori applicano il sacco in coda al calcolo dello SP (`forecast_engine.py:3525`,
`intra_year_engine.py:572`), e il ramo a 12 mesi del wizard della pratica ne manda una versione
propria, con tutte le voci SP del periodo (`app/pratica/page.tsx:876`).

`PATCH /sp-override` (`assumptions_service.apply_sp_overrides`, `budget_scenarios.py:868-946`)
applica TUTTE le voci del lotto — anche su anni diversi — PRIMA di rigenerare, una volta sola,
nella STESSA transazione: un rifiuto (400 se il motore solleva un `ValueError`, 500 altrimenti —
stessa distinzione di §2.1) fa `db.rollback()` dell'INTERO lotto, non solo dell'ultima voce, e
`sp_overrides` resta esattamente come prima della chiamata su OGNI anno toccato. Non c'è
un'allowlist di campi come `CE_OVERRIDE_FIELDS`: una chiave che il risultato del motore non
riconosce è ignorata in silenzio (vedi sotto).

Prima di tutto questo, però, il **corpo** è validato da
`budget_schemas.SpOverrideRequest` (`backend/app/schemas/budget.py:439-458`): un `value` non
numerico, un NaN/infinito, un `forecast_year` mancante o un `overrides` che non è una lista
rispondono **422**, e nulla viene scritto né rigenerato. Fino al lotto 2 la rotta non aveva
alcuno schema (`request: Any = Body(...)`), quindi un `"abc"` giungeva intatto al
`Decimal(str(raw_value))` del motore (`forecast_engine.py:1594`, dentro `_apply_sp_overrides`),
che solleva `decimal.InvalidOperation` — un `ArithmeticError`, non un `ValueError` — e l'unica
risposta possibile era un **500** «Forecast regeneration failed» (M2). Il rollback era già
corretto e nulla restava scritto: sbagliato era solo il codice. Un corpo valido si comporta
come prima anche nella forma salvata: `_sp_override_json_value` (`budget_scenarios.py:844-860`)
ricompone un numero della stessa specie che portava il JSON — `model_dump(mode="json")` di
Pydantic 2 girerebbe i `Decimal` in stringhe, `jsonable_encoder` in float anche dove il corpo
ne portava uno intero (`1000` → `1000.0`).

Ricaduta sul frontend: nessuna. `patchSpOverrides` (`lib/api.ts:720-730`) manda già
`value: number | null` (`OverrideBatchEntry`, `lib/forecast-balance-save.ts:50-54`), e
`getErrorMessage` sa leggere il `detail` a lista di un 422 (`lib/utils.ts:32-37`).

Sostituisce un pattern precedente (fino al giro di correzione 3 del task 10):
`PUT /assumptions/{year}` **per ogni anno modificato, in parallelo** (`Promise.all` lato
client). Dal giro di correzione 2 ciascuna di quelle chiamate rigenerava l'INTERO scenario
nella propria transazione: N rigenerazioni pesanti in corsa sullo stesso file SQLite rischiavano
`database is locked`, e un anno poteva essere validato senza ancora vedere la modifica
dell'altro (non ancora committata) — un rifiuto spurio anche quando la combinazione delle due
modifiche sarebbe stata valida. `PATCH /sp-override` applica tutto prima di rigenerare una volta
sola, eliminando sia la concorrenza sia il rifiuto spurio. `PUT /assumptions/{year}`
(`assumptions_service.update_single_year_assumptions`) resta disponibile con la stessa garanzia
transazionale del giro 2 per un aggiornamento di un singolo anno — nessun chiamante nel
frontend la usa più.

`_apply_sp_overrides` (`forecast_engine.py:1569-1672`) e i controlli che corrono sulla stessa
scrittura hanno cinque comportamenti da conoscere:

1. una chiave che non esiste nel risultato è **ignorata in silenzio**;
2. ogni valore è **clampato a ≥ 0**, tranne `sp13_utile_perdita` e
   `sp12h_riserva_neg_azioni_proprie`: un override negativo su qualunque altro campo diventa
   uno zero, senza errore;
3. il dettaglio vince sull'aggregato, e la cassa resta la voce di pareggio a meno che non sia
   stata forzata esplicitamente;
4. un override dell'**aggregato** `sp16`/`sp17` senza override sulle sue voci mette la
   differenza su `sp16g`/`sp17g`; se quella voce è governata da un piano `altri_debiti` o da
   un'indicizzazione, l'override è **rifiutato** con un `ValueError` in italiano (§10). I debiti
   finanziari `a`/`b`/`c` non ricevono mai né questa differenza né il centesimo di
   arrotondamento (`_sp_forced_fields`, `_normalize_balance_sheet_cents`);
5. un override sul lato **oltre** di un saldo con piano di scadenziamento (`sp17d`, `sp17e`,
   `sp17f`, `sp17g`, `sp07` e le sue sotto-voci commerciali `sp07a`–`sp07d`/`sp07g`) è
   **rifiutato** con un `ValueError` in italiano, in qualunque anno del piano, l'ultimo dopo
   l'ultima rata compreso; lo stesso sul lato **breve** dei quattro debiti quando il valore
   forzato scende sotto la rata dovuta l'anno dopo — tranne i tributari in via manuale, dove il
   lato breve resta libero: lì la guardia è il rifiuto sul totale `sp16e + sp17e` (§9) — e su
   `sp17e` anche senza piano, quando l'anno che lo leggerebbe è a saldo + acconto
   (`_rifiuto_override_governati`). Sul lato breve dei **crediti commerciali** lo stesso rifiuto
   vale sulla parte commerciale di `sp06` (l'aggregato, o una sua sotto-voce `sp06a`–`sp06d`/
   `sp06g`, o `sp06e`/`sp06f` se la spostano): sotto il residuo a breve del piano il `generated`
   dichiarato diventerebbe un credito nuovo negativo, e il motore lo rifiuta — ma da
   `_realign_sp_declarations`, non da `_rifiuto_override_governati`, perché qui non c'è un unico
   campo forzato da confrontare: il residuo si misura sul persistito (`sp06 − sp06e − sp06f`),
   dopo che gli altri override dell'anno sono già stati applicati. Sul
   `PATCH /sp-override` è un 400 con
   rollback del lotto intero; sul bulk è `forecast_generated: false` con l'override salvato
   comunque.

Dopo gli override, le scomposizioni dei `details` seguono il persistito
(`_realign_sp_declarations`): `details['imposte']`, le righe di `details['pregresso']` — i
quattro saldi di debito e, dallo stesso giro, anche `crediti_commerciali` — e il `valore` di
`details['indicizzazione'][voce]`; per la posizione tributaria il valore forzato di
`sp16e`/`sp06e` diventa lo stato d'apertura dell'anno dopo (§9). Sulla riga `crediti_commerciali`
il riallineamento non è incondizionato come sui quattro debiti: se la parte commerciale
persistita scende sotto il `residual_short` che il piano deve incassare l'anno dopo, il
`generated` dichiarato diventerebbe negativo — un credito nuovo negativo, che il motore non
modella (decisione del proprietario, 2026-09-11) — e la generazione si **rifiuta** invece di
scrivere la riga (§2.2, punto 5).

## 3. Precedenza, e che cosa sopravvive a che cosa

Un override **vince sempre** sulla percentuale di crescita della stessa riga: si può cambiare
`revenue_growth_pct` quanto si vuole, se `ce01_override` è valorizzato il ricavo previsionale
non si muove. Vince tranne sulle righe che il piano governa: sul lato oltre di un saldo con
piano di scadenziamento, e sul lato breve sotto la rata dovuta l'anno dopo, l'override non è
ammesso (§2.2).

Sulle **righe a giorni** — `sp06a`, `sp06b`, `sp06c`, `sp06d`, `sp06g` (le voci commerciali
ripartite dal DSO, `_alloc`; `sp06e` e `sp06f` non ci sono: seguono la posizione tributaria e le
imposte differite, non i giorni) e `sp16d` (DPO) — un
override vale invece **un anno solo**: la riga si ricalcola ogni anno dalla formula dei giorni,
non da `prev`, quindi dall'anno N+1 torna quella senza override e la differenza rientra come
variazione del circolante dell'anno dopo (il rendiconto la mostra come flusso operativo, non
sparisce). Era così già prima del lotto; le righe che crescono da `prev` portano invece
l'override avanti.

E gli override **sopravvivono al salvataggio**:

| Azione dell'utente | Chiamata | Effetto sugli override |
|---|---|---|
| `/budget` → «Salva e Calcola Previsionale» | `PUT /assumptions` (`auto_generate=true`), righe idratate | **conservati** |
| `/budget` → «Ricalcola» **senza** spuntare la casella | `POST /generate` | **conservati** |
| `/budget` → «Ricalcola» **con** *«Azzera le modifiche manuali del CE previsionale»* | `POST /generate?clear_overrides=true` | azzerati — ma vedi sotto |
| `/forecast/income` → svuotare una cella | `PATCH /ce-override` con `value: null` | azzerato solo quello |

`clear_overrides` scorre `assumption.__table__.columns` e mette a `None` ogni colonna il cui
nome **finisce per `_override`** (`budget_scenarios.py:1000-1003`). `sp_overrides` finisce per
`_overrides`: **non viene azzerato**. La casella dice «del CE previsionale» e in questo è
onesta, ma chi la spunta aspettandosi di tornare al previsionale puro del motore si tiene
tutti gli override di stato patrimoniale.

## 4. I giorni di rotazione derivati dall'anno base

Quando `dso_days` / `dio_days` / `dpo_days` non sono impostati nelle ipotesi, il motore li
deriva dall'anno base con `DAYS = 360` (`forecast_engine.py:2484`):

| | formula | nota |
|---|---|---|
| DSO | `(sp06 − sp06e − sp06f) / ce01 × 360` | solo i crediti **commerciali**: crediti tributari e imposte anticipate sono esclusi perché dipendono dalla posizione fiscale, non dal giro d'affari (`:2214-2236`) |
| DIO | `sp05 / ce01 × 360` | il denominatore è il **ricavo**, non gli acquisti (`:2238-2252`) |
| DPO | `sp16d / (ce05 + ce06) × 360` | solo i debiti **verso fornitori**, non l'aggregato `sp16` (`:2429-2442`) |

> **L'aliquota di default non è quella che l'app usa.** Lo schema Pydantic ha
> `tax_rate: Decimal = 24` (`backend/app/schemas/budget.py:188`, l'IRES da sola), ma ogni
> chiamante del frontend manda **27,9** — la miscela IRES 24 + IRAP 3,9 dichiarata in
> `STARTUP_TAX_RATE_PCT` (`app/budget/page.tsx:370`) e ripetuta letterale in
> `app/pratica/page.tsx:780, 877` e in `lib/budget-horizon.ts:245`. Il 24% si vede solo su una
> chiamata che ometta il campo.

Il circolante scala quindi con i ricavi e i costi previsionali, **anche quando questi vengono
da un override CE**: `_calculate_balance_sheet` legge `forecast_inc`, cioè il conto economico
già calcolato con gli override applicati (`:2133-2134`). Più ricavi → più crediti; più acquisti
→ più debiti verso fornitori; la cassa fa da pareggio, ma **solo verso l'alto**: un fabbisogno
di cassa non diventa mai da solo debito a breve. Di default il motore solleva `Unfunded
financing requirement <importo>` e non produce nulla; solo con `overdraft_allowed` (per anno di
ipotesi) il fabbisogno diventa uno scoperto generato dal piano, dichiarato in `sp16a` e nei
`details` (`scoperto_generato`, `scoperto_residuo`) — vedi «Forecasting Engine» in `CLAUDE.md`.

## 4-bis. Il nuovo finanziamento: che cosa sta a breve

Un prestito nuovo è la legacy `financing_amount` / `financing_duration_years` /
`financing_interest_rate` della riga d'ipotesi, oppure una riga di `financing_loans[]` con
`amount` (ed eventualmente `grace_years` e `balloon_pct`). Si rimborsa col calendario del kernel
`new_financing_schedule` (`calculations/projection_common.py`): quote capitali costanti dopo
l'eventuale preammortamento, maxirata insieme all'ultima rata, interessi in `ce15` sul residuo di
apertura. Un contratto misto (`amount` e `opening_residual` sulla stessa riga) si divide in due
contratti con le stesse condizioni: la parte nuova segue questa sezione, quella pregressa no.

Il residuo del prestito **non** sta tutto in `sp17a_debiti_banche_lungo`: la parte che il
calendario rimborsa **nell'anno dopo** sta in `sp16a_debiti_banche_breve`, il resto in `sp17a`
(`_quota_breve_prestiti_nuovi` in `calculations/forecast_engine.py`).

- Finché anche l'anno dopo è di preammortamento la quota a breve è zero; nell'anno prima della
  maxirata la maxirata sta a breve.
- L'ultimo anno di piano non si azzera: la rata dell'anno oltre l'orizzonte viene dal contratto.
- La quota è la differenza fra due residui al centesimo della catena persistita, non la rata
  arrotondata: 100.000,38 in 4 anni ha rata 25.000,095 e quota a breve 25.000,09.
- È una riclassifica dello stato patrimoniale, non un flusso: interessi e risultato non cambiano, e
  — **senza un `sp_overrides` su `sp16a` o `sp17a`** — nemmeno cassa e totale del debito bancario.
  Il cash sweep non la tocca mai: rimborsa solo lo scoperto e il debito bancario pregresso senza
  piano (§4-ter); il debito bancario pregresso conserva la propria ripartizione. Il rendiconto
  (`backend/app/calculations/cashflow_detailed.py`, `cashflow.py`) non la vede nemmeno lui: il
  circolante e' `sp16`/`sp17` **meno** `financial_debt_short`/`financial_debt_long` (non la somma dei
  sotto-campi operativi, che puo' scostarsi di un centesimo dall'aggregato), il finanziario e'
  `financial_debt_short`/`financial_debt_long` — mai l'aggregato grezzo
  `sp16`/`sp17` — quindi la riclassifica fra `sp16a` e `sp17a` non attraversa il confine
  operativo/finanziario del rendiconto.
- I proventi da partecipazioni (`ce13`) tolti dall'utile nel primo blocco rientrano come dividendi
  incassati, e `cash_reconciliation.third_party_funds_gap` dichiara lo scarto fra i mezzi di terzi per
  residuo e la variazione misurata del debito finanziario: zero quando il rendiconto classifica ogni
  movimento.
- `details['debito_bancario']['contratti']` dichiara ogni anno il `breve` di ogni prestito,
  riconciliato con quanto `sp16a` persiste davvero (§4-ter).

**Perché conta:** `sp16` e `sp17` stanno entrambi nel passivo, quindi il pareggio non vede dove sta
la quota; la vedono CCN, current ratio e circolante di Altman. Sulla base del kit di test (12.345,67
di breve e 23.456,79 di lungo pregresso, 100.000,38 in 4 anni al 4,35%) il current ratio 2027 è
2,0794 (0,3620 il circolante di Altman, CCN/TA); con tutto il prestito oltre l'esercizio
risultavano 2,4206 e 0,4093.

Un `sp_overrides` su `sp16a` **o su `sp17a`** cambia significato rispetto a prima di questo task, e
muove cassa e debito bancario totale della quota — in direzioni opposte, perché la riclassifica
avviene PRIMA che gli override vengano applicati:
- `sp16a` ora fissa un totale che **contiene** la quota. Se la porta sotto, il taglio cade prima sul
  breve pregresso e la quota dichiarata è ciò che ne resta: un override salvato quando il prestito
  stava tutto in `sp17a` oggi toglie anche la quota a breve dal debito (−25.000,09 di debito e di
  cassa ogni anno, sul kit di test).
- `sp17a` ora fissa solo la parte **oltre** la quota: la quota resta comunque a breve in `sp16a`,
  sopra il totale forzato. Un override salvato quando il prestito stava tutto in `sp17a` oggi
  aggiunge quindi la quota al debito (+25.000,09 di debito e di cassa ogni anno, sul kit di test).

## 4-ter. Il cash sweep e `details['debito_bancario']`

Il perimetro dello sweep, dal lotto 3A (decisione 3 del proprietario):

- Lo sweep rimborsa (1) lo scoperto, come prima — la cassa netta lo contiene gia' — e (2) il debito
  bancario pregresso **senza alcun piano**: nell'anno non ci sono contratti con residuo iniziale
  (`opening_residual`) né `existing_debt_repayment_years` > 0. Prima la quota a breve, poi la lunga.
  Nient'altro.
- I contratti della griglia, il prestito nuovo della legacy `financing_amount` e il pregresso con gli
  anni di rimborso **seguono solo il proprio piano**, capitale e interessi: uno sweep che li
  spegnesse lascerebbe maturare `ce15` su un debito a zero (misurato: 7.200,00 di oneri in tre anni).
- La cassa eccedente oltre `cash_sweep_min_cash` resta in `sp09`.

**Lo sweep decide una volta sola, sulla cassa di dopo gli `sp_overrides`** (rilievo I2 della revisione
finale del lotto 2): gira in `_normalize_balance_sheet_cents`, sulla cassa gia' al centesimo, subito
prima del cancello di `_Overdraft.copri`, e non chiama `copri` lui stesso. Deciso prima degli override
e sulla cassa grezza, lo sweep fabbricava un fabbisogno: su un piano finanziabile rispondeva
«Unfunded financing requirement 11.053,98», e con lo scoperto concesso rimborsava 50.000 di `sp17a`
aprendo 11.053,98 di scoperto nello stesso anno. Un `sp_overrides` che fissa `sp16a`/`sp16` o
`sp17a`/`sp17` fissa anche il totale: da quel lato lo sweep non paga.

### `details['debito_bancario']`

Si dichiara **ogni anno, anche vuota** (a valle una chiave assente vale zero), e sostituisce la
vecchia chiave unica della quota a breve dei prestiti nuovi.

| Chiave | Valore |
|---|---|
| `pregresso_senza_piano` | `{apertura, rimborso_sweep, breve, lungo}` quando nell'anno non ci sono contratti con `opening_residual` né `existing_debt_repayment_years` > 0; altrimenti `null` |
| `pregresso_piano_anni` | `{apertura, rimborso, breve, lungo}` con `existing_debt_repayment_years` > 0 e nessun contratto col residuo; altrimenti `null` |
| `contratti` | una riga per contratto (misti gia' divisi, anche non ancora erogati), nell'ordine di `financing_amount` e poi della griglia: `{indice, anno, tasso, erogato, residuo_iniziale, rimborso, interessi, breve, lungo}` |

**Invariante:** somma dei `breve` + `scoperto_residuo` = `sp16a`, somma dei `lungo` = `sp17a`, al
centesimo, ogni anno. La scrive `_dichiara_debito_bancario` DOPO la normalizzazione, dai valori
persistiti, e la riconcilia cosi': la differenza fra le componenti grezze e il persistito (centesimi
di arrotondamento, un `sp_overrides` sul debito bancario, lo sweep) in aumento va sulla «casa del
pregresso» — `pregresso_senza_piano`, altrimenti `pregresso_piano_anni`, altrimenti l'ultimo
contratto col residuo iniziale, altrimenti l'ultimo contratto nuovo; in riduzione si toglie prima al
pregresso (le due componenti, poi i contratti col residuo dall'ultimo), poi ai contratti nuovi
dall'ultimo, mai sotto zero. Sono spostamenti di centesimi fra componenti, non debito creato: la
somma resta `sp16a`/`sp17a`.

## 5. Promote — dalla proiezione infrannuale a un anno di bilancio

```
POST /companies/{id}/scenarios/{sid}/promote
→ { "success": true, "financial_year_id": 123, "year": 2025, "company_id": 1,
    "message": "...", "verification": { "exact_match": true,
      "balance_sheet_fields": N, "income_statement_fields": M, "semantic_valid": true } }
```

Copia l'unico `ForecastYear` dello scenario in un nuovo `FinancialYear(period_months=None)`,
così l'anno proiettato può fare da anno base a uno scenario budget successivo. Solo scenari
`infrannuale`.

La sequenza, in `backend/app/services/promote_service.py`:

1. **Primo cancello, prima di scrivere:** `check_quadratura(...).semantic_valid` sulla
   proiezione (`:46-57`). Non è una soglia in euro: è pareggio **e** identità CE↔SP **e**
   non-mascheramento **e** coerenza aggregati/dettagli.
2. **Sostituzione:** un `FinancialYear` annuale già esistente per company+anno
   (`period_months` `NULL` **o** `12`) viene **cancellato** con tutto il suo BS/IS in cascata
   (`:59-67`). Un anno importato a mano per lo stesso anno viene distrutto.
3. **Copia** per intersezione di colonne fra i modelli Forecast e i modelli definitivi
   (`_copy_columns`), saltando pk/fk e timestamp.
4. **Secondo cancello, dopo la scrittura e prima del commit:** confronto campo per campo fra
   sorgente e copia (`_verify_copy`) **più** una seconda `check_quadratura` sul bersaglio
   copiato. Un fallimento fa `rollback()` dell'intera transazione — quindi **anche il record
   annuale cancellato al punto 2 torna al suo posto** (`:107-139`).

Il nuovo record nasce con `validation_status="verified"`, `forecastable=True`,
`parser_version="promoted-projection-v3-verified-copy"` e un `validation_report` che dichiara
`"source": "promoted_projection"`.

> `_forecast_bs_imbalance` (`promote_service.py:158`) è il resto del vecchio cancello a soglia
> in euro. **Non ha più alcun chiamante in produzione**: lo esercita solo
> `tests/test_quadratura_gates.py`, che continua a descriverlo come «promote_service
> quadratura gate». Non lo è più dal passaggio a `semantic_valid`.

Dopo il promote si crea normalmente uno scenario budget con `base_year` = l'anno promosso.

## 6. File chiave

| File | Che cosa contiene |
|---|---|
| `database/models.py` | `BudgetAssumptions` — le 32 colonne `ce*_override`, `sp_overrides`, `pregresso`, `overdraft_allowed`/`overdraft_limit` |
| `backend/app/schemas/budget.py` | gli stessi campi lato Pydantic (`PregressoInput` e le sue due sotto-classi comprese) |
| `backend/app/services/assumptions_service.py` | il bulk, e il `try/except` che produce il 200 con `forecast_generated: false` |
| `backend/app/services/analysis_service.py` | `_forecast_staleness` — `forecast_stale`, `assumptions_updated_at`, `forecast_updated_at` (§1.1) |
| `backend/app/api/v1/budget_scenarios.py` | `PATCH /ce-override` + `_CE_OVERRIDE_FIELDS`, `POST /generate?clear_overrides`, i 3 endpoint dei commenti AI, `POST /promote` |
| `backend/app/services/promote_service.py` | i due cancelli, la sostituzione, la copia verificata |
| `calculations/forecast_engine.py` | override nel CE, `_apply_sp_overrides`, DSO/DIO/DPO derivati, `validate_pregresso`, la classe `_Overdraft` |
| `calculations/projection_common.py` | i kernel puri condivisi: `runoff_schedule`, `tax_settlement_saldo_acconto`, `pregresso_opening_masses` |
| `calculations/intra_year_engine.py` | gli stessi override sul percorso infrannuale — **non** tocca lo scadenziamento del pregresso né l'overdraft |
| `frontend/app/forecast/income/page.tsx` | `FIELD_TO_OVERRIDE`, `EditableCell`, `pendingEdits`, salvataggio batch |
| `frontend/app/forecast/balance/page.tsx` | l'editor dello SP previsionale che scrive `sp_overrides` |
| `frontend/lib/pratica-codes.ts` | `CE_OVERRIDE_FIELD_BY_CODE`, `buildCeOverridePayload` |
| `frontend/lib/api.ts` | `bulkUpsertAssumptions`, `patchCeOverrides`, `generateForecast(clearOverrides)`, `promoteProjection`, `previewForecast` |
| `backend/app/services/forecast_preview_service.py` | il servizio dell'anteprima: `load_forecast_source` + `compute_forecast(stop_on_error=False)`, nessuna sessione toccata |

## 7. Anteprima — stesso motore, nessuna scrittura

```
POST /companies/{id}/scenarios/{sid}/preview
{ "assumptions": [ { "forecast_year": 2026, "revenue_growth_pct": 5.0, "...": "..." } ] }
```

Stesso corpo del bulk (`{"assumptions": [...]}`); bulk e anteprima condividono
`build_assumption_row` (`backend/app/services/assumptions_service.py:99`) e
`validate_assumptions_list`, così un campo aggiunto a un percorso non può mancare all'altro. Le
righe costruite sono transitorie — **mai `db.add`, mai `commit`** — e il motore le legge con
`getattr` come farebbe con righe persistite. Rifiuta con **400** uno scenario
`scenario_type == "infrannuale"` prima di leggere qualunque cosa: quel percorso ha il proprio
motore (`IntraYearEngine`) e le proprie tab (Confronto, Proiezione).

Risposta, sempre **200**, anche a calcolo interrotto:

```json
{
  "scenario_id": 12,
  "base_year": 2025,
  "forecast_years": [
    {
      "year": 2026,
      "income_statement": { "ce01_ricavi_vendite": 2597000.0, "...": "..." },
      "balance_sheet": { "sp09_disponibilita_liquide": 131240.0, "...": "..." },
      "details": {
        "ce05_fixed": 349860.0, "ce05_variable": 675220.0,
        "ce06_fixed": 257040.0, "ce06_variable": 178080.0,
        "dso_applied": 62.0, "dio_applied": 45.0, "dpo_applied": 78.0
      }
    }
  ],
  "error": null
}
```

`error` è `null` oppure `{"year": 2027, "message": "..."}`: in quel caso `forecast_years`
contiene solo gli anni calcolati **prima** dell'errore. Gli errori di ingresso (anno ≤ base,
anni duplicati, corpo vuoto, scenario infrannuale) restano **400** come nel bulk, perché sono
errori del chiamante, non del piano.

`details` porta sempre le chiavi dichiarate da `ForecastEngine.compute_forecast`:
`ce05_fixed`, `ce05_variable`, `ce06_fixed`, `ce06_variable` (i due addendi di materie prime e
servizi — `null` quando `ce05_override`/`ce06_override` è valorizzato, perché la scomposizione
non è definita su un importo forzato) e `dso_applied`, `dio_applied`, `dpo_applied` (i giorni di
rotazione effettivamente usati, forzati o derivati che siano).

`degenerate_turnover_ratio` è una **lista** — presente ogni anno, vuota quando non scatta nulla —
dei giorni **dedotti** che il motore ha scartato: `'dso'`, `'dio'`, `'dpo'`. Un giorno dedotto è
degenere quando il denominatore dell'anno base non è positivo, o quando il rapporto supera i 365
giorni: oltre un anno di giacenza smette di descrivere l'azienda e descrive il proprio
denominatore. Su un giorno degenere il motore **riporta il saldo dell'anno base** invece di
scalarlo, e `dso_applied`/`dio_applied`/`dpo_applied` dichiarano il giorno che quel saldo vale
davvero sul flusso proiettato (zero se il flusso è nullo), mai quello degenere. Un giorno
**esplicito** dell'ipotesi non passa dalla guardia: è una scelta, non una derivazione. Se il
saldo ha un piano di pregresso è il piano a governarlo e il riporto vale zero, o la stessa massa
sarebbe contata due volte.

`details` porta anche, sempre (ogni anno, anche a zero/vuoto): `pregresso`, `imposte`,
`pregresso_ignored`, `pregresso_writeoff_ignored` (§8), `oneri_scoperto`, `scoperto_generato`,
`scoperto_residuo`, `cassa_assorbita`, `fabbisogno_picco`, `fabbisogno_picco_anno`,
`cassa_sotto_minimo` (§10), `indicizzazione`, `indicizzazione_ignorata` (§11),
`residuo_quadratura` — il bulk e l'anteprima condividono lo stesso motore e lo stesso dict,
quindi nessuna di queste manca da una delle due porte.

`residuo_quadratura` è la lista `{campo, importo}` delle posature del residuo di arrotondamento
della normalizzazione al centesimo dello SP (`_normalize_balance_sheet_cents`): `importo` è
quanto è stato sommato a `campo`. `campo` è il secchio del gruppo (`sp16g`, `sp06g`, …),
l'ultimo sotto-campo operativo libero, oppure l'aggregato `sp16_debiti_breve`/`sp17_debiti_lungo`
quando nessuna voce operativa del gruppo è libera (e allora `sp09` si muove dello stesso
importo). Mai `sp16a/b/c`, `sp17a/b/c`. Sempre presente, anche vuota.

## 8. Lo scadenziamento del pregresso

Il motore proietta il circolante con formule di **stock**: ogni formula sostituisce l'intero
saldo dell'anno prima, quindi il pregresso si presume incassato o pagato entro l'anno, sempre.
`BudgetAssumptions.pregresso` (colonna `JSON`, `database/models.py`) è il modo per dire
l'opposto: quanto del saldo al 31/12 dell'anno base si chiude in ciascun anno di piano, saldo per
saldo.

```jsonc
PUT /companies/{id}/scenarios/{sid}/assumptions
{
  "assumptions": [
    { "forecast_year": 2026, "revenue_growth_pct": 5.0,
      "pregresso": {
        "crediti_commerciali":  { "opening": 422000.00, "amounts": [380000.00, 30000.00], "writeoff": [12000.00, 0] },
        "debiti_fornitori":     { "opening": 322000.00, "amounts": [322000.00] },
        "debiti_tributari":     { "opening": 96000.00, "saldo": 61000.00, "rateizzato": 35000.00,
                                   "amounts": [11667.00, 11667.00, 11666.00], "acconto_pct": 100 },
        "debiti_previdenziali": { "opening": 41000.00, "amounts": [41000.00] },
        "altri_debiti":         { "opening": 58000.00, "amounts": [58000.00] }
      }
    },
    { "forecast_year": 2027, "revenue_growth_pct": 4.0 }
  ],
  "auto_generate": true
}
```

Cinque chiavi, tutte opzionali (`backend/app/schemas/budget.py` — `PregressoInput`,
`PregressoPlanInput`, `PregressoTributariInput`): `crediti_commerciali`, `debiti_fornitori`,
`debiti_tributari`, `debiti_previdenziali`, `altri_debiti`. Una chiave **assente o `null`** vale
«nessun piano»: il motore usa la formula di oggi **intera**, lato breve e lato lungo
(`mode: "legacy"`, sotto). Il centesimo di arrotondamento del gruppo debiti resta su
`sp16g`/`sp17g` come prima, ma può valere un centesimo diverso quando un'altra riga del gruppo
è cambiata (i tributari, §9).

- **Solo sulla riga del primo anno di piano.** `pregresso` su una riga successiva alza
  `pregresso is allowed only in the first forecast year` (`calculations/forecast_engine.py:1786-
  1789`). È una fotografia dell'anno base, non un'ipotesi per-anno.
- **`opening` deve coincidere col bilancio base**, tolleranza 0,01 €, o il motore si ferma con
  «il saldo di apertura di {voce} è cambiato ({dichiarato} → {base}): rivedi lo scadenziamento»
  (`validate_pregresso`, `calculations/forecast_engine.py:448-505`).
- **`amounts[i]`** è l'importo chiuso nell'anno di piano `i` (0 = il primo). Per
  `debiti_tributari` riguarda il **solo rateizzato**: il saldo dell'anno precedente si versa per
  intero nel primo anno di piano, per definizione (§9). Lunghezza ≤ orizzonte; importi ≥ 0; la
  somma non può superare la massa che scadenzia — `amounts + writeoff ≤ opening` per i crediti,
  `saldo + rateizzato = opening` **al centesimo** e `Σ amounts ≤ rateizzato` per i tributari
  (`validate_runoff`, `calculations/projection_common.py:297-307`). Superare la massa è un
  **errore**, non un troncamento
  silenzioso: incassare più di quanto c'è inventa cassa.
- **`writeoff[i]`** esiste solo su `crediti_commerciali`: è l'inesigibile di quell'anno, riduce
  il residuo e va in `ce09d_svalutazione_crediti` (`ce09d(N) = ce09d_base + inesigibile(N)`, salvo
  `ce09d_override` — se un override di CE forza `ce09` o `ce09d`, l'inesigibile scadenziato non
  può essere scaricato e resta a bilancio: `pregresso_writeoff_ignored`, sotto, lo dichiara).

**Scadenza per costruzione.** Alla chiusura dell'anno N, la parte del residuo dovuta in N+1 sta a
breve (`sp06`/`sp16x`); il resto sta oltre 12 mesi (`sp07`/`sp17x`). **Con un piano il lato lungo
è interamente pregresso**: il motore rigenera dalla formula di oggi solo il lato a breve
(generato + il residuo dovuto l'anno dopo), il resto del residuo ci resta per tutto il piano e la
percentuale di crescita di quella voce (`sp07_growth`, o `sp17d`/`sp17f`/`sp17g_growth_pct`)
smette di applicarsi (`calculations/forecast_engine.py:2745-2763` per i crediti, `:3104-3128` per
fornitori/previdenziali/altri debiti). Nell'ultimo anno di piano tutto il residuo non scadenziato
è oltre: non c'è un «anno dopo» nel piano, e il motore non inventa scadenze.

### `details['pregresso'][chiave]` — una per ciascuna delle cinque voci, ogni anno

| Chiave | Valore |
|---|---|
| `opening` | la massa che le altre chiavi della riga descrivono: la massa di apertura del bilancio base senza piano, la massa scadenziata con un piano — per i tributari è il **rateizzato**, non l'intera apertura, perché il saldo si versa a parte (§9) |
| `closed` | l'importo chiuso quest'anno (`amounts[year_index]`, o zero senza piano) |
| `writeoff` | l'inesigibile di quest'anno (solo crediti) |
| `residual_short` | il residuo dovuto l'anno **dopo** — quello che finisce a breve |
| `residual_long` | il resto del residuo, oltre l'esercizio |
| `generated` | il lato a breve **generato dalla formula di oggi**, prima di sommare `residual_short` |
| `mode` | `"runoff"` con un piano dichiarato, `"legacy"` senza (formula di oggi, intera) |

`pregresso_ignored` è una **lista**, sempre presente anche vuota: i saldi il cui piano è stato
scavalcato dalla via manuale (oggi il solo caso possibile è `debiti_tributari`, quando
`sp06e_growth_pct` o `sp16e_growth_pct` sono valorizzati — §9). `pregresso_writeoff_ignored` è
una lista di oggetti (`saldo`, `field`, `requested`, `reason`) per l'inesigibile che un override
di CE ha impedito di scaricare: senza questa chiave il piano direbbe un importo inesigibile e il
bilancio non ne mostrerebbe traccia, senza un solo avviso.

## 9. Le imposte a saldo + acconto

È l'unico dei cinque saldi il cui comportamento cambia **anche senza un piano**: il vecchio
meccanismo (`precedente + imposte dell'anno − acconti`, con acconti a **zero** di default)
accumulava debito tributario che non usciva mai — un difetto che quadrava, mai visto da un
controllo. Ora ogni anno di piano paga **saldo + acconto + rate**
(`calculations.projection_common.tax_settlement_saldo_acconto`, chiamata solo dal motore budget —
l'infrannuale continua a usare `tax_closing_position`, invariata):

- **saldo pagato in N** = il debito tributario **generato a fine N−1**, cioè
  `details['imposte'].generated_debt` dell'anno N−1 — il debito generato a fine N−1 oppure, se
  `sp16e` è stato forzato, `sp16e` persistito meno il rateizzato dovuto in N
  (`_realign_sp_declarations`) — al netto del credito tributario di apertura fino a capienza
  (l'eccedenza resta credito). Per N = 1 è la quota
  «saldo dell'anno precedente» che l'utente dichiara nel campo `pregresso.debiti_tributari.saldo`.
- **acconti(N)** = `tax_advances_paid` della riga N se **maggiore di zero**, altrimenti
  `imposte(N−1) × acconto_pct / 100` — `acconto_pct` di default **100**, `imposte(0)` è `ce20`
  dell'anno base (l'unico dato di imposta che il consuntivo porta). **Zero in `tax_advances_paid`
  non vuol dire «zero acconti»**: la colonna è `NOT NULL default 0`, quindi zero è il valore che
  dice «non compilata», e il motore ricade sulla percentuale. Chi vuole davvero zero acconti
  imposta `acconto_pct = 0`.
- **rate pagate in N** = l'importo del piano `pregresso.debiti_tributari.amounts` per l'anno N —
  scadenzia il **solo rateizzato**, mai il saldo.
- **debito generato a fine N** = `max(0, imposte(N) − acconti(N))`; **credito generato a fine N**
  = `max(0, acconti(N) − imposte(N))`.
- `sp16e(N)` = debito generato + rate dovute in N+1; `sp17e(N)` = rate dovute oltre N+1;
  `sp06e(N)` = credito generato + eccedenza del credito di apertura non ancora usata; con un
  override di `sp06e`, la somma di `generated_credit` e `opening_credit_left` è il valore
  forzato, ripartito riempendo prima `opening_credit_left` e poi `generated_credit`.

Uscita di cassa dell'anno = saldo + acconti + rate, attraverso il plug come tutto il resto.

**Via manuale.** `sp06e_growth_pct` o `sp16e_growth_pct` valorizzati saltano tutto questo, come
prima del lotto: i debiti tributari si muovono per crescita percentuale, e un piano tributario
scritto insieme a quelle percentuali produce `pregresso_ignored: ["debiti_tributari"]` invece di
applicarsi a metà. Un anno **manuale seguito da un anno automatico**, con un piano tributario,
non è però libero: il saldo dovuto si ricostruisce dal **totale** di debito tributario che
l'anno manuale lascia in bilancio (`sp16e + sp17e`), e se quel totale è **inferiore** al
rateizzato ancora aperto all'inizio dell'anno automatico il calendario ripartirebbe intero e la
cassa assorbirebbe la differenza senza un versamento — il motore lo rifiuta con un errore in
italiano che nomina l'anno manuale e l'anno che riparte dal piano. Tre vie d'uscita: tenere in
via manuale anche l'anno che riparte; lasciare nell'anno manuale un debito tributario
(`sp16e + sp17e`, per percentuale o per override) non inferiore al rateizzato aperto; modificare
il piano nel passo «Imposte». In un anno manuale l'override del lato breve tributario resta
comunque libero — il rifiuto (§2.2) guarda il totale che l'anno dopo legge, non il lato singolo.

### `details['imposte']` — sempre presente, ogni anno

| Chiave | Valore |
|---|---|
| `current_tax` | l'imposta corrente dell'anno (da `_tax_components`, le differite restano fuori) |
| `saldo_paid` | il saldo versato quest'anno |
| `acconti_paid` | l'acconto versato quest'anno |
| `rate_paid` | le rate del rateizzato versate quest'anno |
| `generated_debt` | il debito tributario a saldo di fine anno (→ `saldo_paid` dell'anno prossimo; `sp16e` = `generated_debt` + `residual_short`; con un override di `sp16e` vale `sp16e` − `residual_short`) |
| `generated_credit` | il credito tributario generato a fine anno — con un override di `sp06e` la loro somma è il valore forzato |
| `opening_credit_left` | il credito di apertura non ancora usato — un override di `sp06e` riempie prima questa, poi `generated_credit` |
| `mode` | `"saldo_acconto"` (il kernel governa) o `"manual"` (via manuale attiva: gli importi pagati sono dichiarati zero, perché non esistono — mai inventati) |

## 10. Scoperto di conto corrente (overdraft)

La cassa proiettata pluggia **solo verso l'alto**: un plug negativo è un fabbisogno scoperto.
`overdraft_allowed` (per anno di ipotesi, **`false` di default**) decide che cosa succede: spento,
il motore **solleva** `Unfunded financing requirement <importo>` e non produce nulla, come sempre;
acceso, il fabbisogno diventa uno scoperto **generato dal piano**, componente separato dal debito
bancario pregresso e dal nuovo finanziamento — anche nell'aritmetica, non solo nei `details`
(`calculations/forecast_engine.py`, classe `_Overdraft`). `overdraft_limit` (opzionale, ≥ 0) è il
tetto: oltre, il motore solleva di nuovo. Il cancello unico è `_Overdraft.copri`, chiamato una
volta sola dopo ogni rettifica compresi gli `sp_overrides`, su una cassa netta già arrotondata al
centesimo.

```jsonc
{ "forecast_year": 2027, "revenue_growth_pct": 5.0,
  "overdraft_allowed": true, "overdraft_limit": 100000.00 }
```

### `details` — sei chiavi dello scoperto, sempre presenti (anche a zero)

| Chiave | Valore |
|---|---|
| `scoperto_generato` | lo scoperto **nato** nell'anno (aumento sul saldo di apertura) |
| `scoperto_residuo` | lo scoperto **in essere a fine anno** — l'apertura dell'anno dopo |
| `cassa_assorbita` | quanto la cassa si riduce nell'anno, **anche dove resta positiva**: l'avviso arriva prima che diventi scoperto, non dopo |
| `oneri_scoperto` | l'interesse maturato al `financing_interest_rate`, sullo scoperto di **apertura** — mai su quello che l'anno stesso genera, sarebbe circolare |
| `fabbisogno_picco` | il fabbisogno di picco su **tutto il piano**, scritto su ogni anno: la domanda che si porta in banca non dipende dall'anno che si sta guardando |
| `fabbisogno_picco_anno` | l'anno in cui cade il picco — `null` quando il picco è zero |

Una settima chiave, distinta dalle sei di sopra e legata al `cash_sweep_min_cash` (Ruling 38):
`cassa_sotto_minimo`, quanto la cassa di chiusura sta sotto il minimo del cash sweep in un anno
con scoperto aperto o chiuso nell'anno — perché lo scoperto si rimborsa **per primo**, anche sotto
quel minimo (tenere liquidità pagando interessi sullo scoperto non avrebbe senso), e questo si
dichiara invece di evitarlo.

Un `sp_overrides` su `sp16a` (o sul suo aggregato `sp16`) fissa il totale: vince, e lo scoperto ne
discende — zero con cassa netta non negativa; con un fabbisogno nessuna ripartizione è coerente
(il passivo è fissato dall'override qualunque sia la divisione fra banca e scoperto), e il motore
rifiuta la combinazione con un errore esplicito invece di superare il totale.

⚠️ **Il totale `sp16`/`sp17` però non vince se il gruppo non ha più un ripiego libero.** Quando
un piano di scadenziamento (o un'indicizzazione) del *secchio* `sp16g`/`sp17g` ha già
forzato tutte le righe operative del gruppo, la differenza fra il totale richiesto e
la somma delle righe non è un arrotondamento: è la massa dell'override, e non c'è
un campo onesto che la riceva (sul secchio il calendario la cancellerebbe l'anno
dopo; su una riga `d`/`e`/`f` sarebbe un'obbligazione inventata). Il motore risponde
allora `forecast_generated: false` con «Il totale forzato di `sp16_debiti_breve` non
è ammesso» — sul `PATCH /sp-override` è un 400 con rollback, e la cella non
resta scritta. Senza piano né indicizzazione sul gruppo, il totale forzato continua
a vincere come sempre (`tests/test_forecast_residuo_quadratura_sp16.py`).

## 11. Indicizzazione delle voci minori dello SP (`sp_indexing`)

Undici voci minori dello stato patrimoniale seguono, per default, la formula di sempre —
`prev × (1 + %)`, cioè restano **ferme** se la percentuale non è impostata. `sp_indexing`
(`BudgetAssumptions.sp_indexing`, colonna `JSON`) le aggancia invece a un driver di volume:
`stock dell'anno BASE × fattore del driver`, la stessa forma già usata da
`previdenza_scales_with_personnel`. Indicizzare sulla base non accumula deriva, mentre un
`prev × (1+%)` composto per cinque anni sì.

```jsonc
{ "forecast_year": 2026, "revenue_growth_pct": 5.0,
  "sp_indexing": { "sp01": "ricavi", "sp16g": "acquisti", "sp08": "personale" } }
```

- **Chiave** = uno degli **undici** codici indicizzabili (`SP_INDEXABLE_FIELDS`,
  `calculations/forecast_engine.py:56-68`): `sp01`, `sp04`, `sp08`, `sp10`, `sp14`, `sp16f`,
  `sp16g`, `sp17d`, `sp17f`, `sp17g`, `sp18`. Un codice fuori da questo elenco è ignorato e
  dichiarato con il motivo `"voce non indicizzabile"` — non applicato a una voce che il motore
  governa in un altro modo.
- **Valore** = uno dei **tre driver**, tipizzato `Literal["ricavi", "acquisti", "personale"]`
  (`backend/app/schemas/budget.py:96,207,319`): `ricavi` = `ce01` previsto / `ce01` base,
  `acquisti` = `(ce05+ce06)` previsto / base, `personale` = `ce08` previsto / base
  (`calculations/forecast_engine.py:1132-1160`, `_sp_indexing_factors`). Un nome fuori da questi tre
  **non è rifiutato sulla porta normale**: il bulk `PUT /scenarios/{id}/assumptions` riceve un dict
  che non passa dallo schema (`request: Any = Body(...)`, `backend/app/api/v1/budget_scenarios.py:699`),
  e il motore lo ignora dichiarandolo in `indicizzazione_ignorata` con il motivo `"driver sconosciuto"`
  (`calculations/forecast_engine.py:1196`). Solo le rotte tipizzate per singola riga passano dal
  `Literal` Pydantic e rispondono 422.
- **Per anno al motore, per scenario al wizard.** Il motore legge `sp_indexing` riga per riga
  come ogni altra ipotesi (nessun vincolo "solo primo anno", a differenza di `pregresso`); il
  passo 5 del wizard («Capitale circolante») lo scrive però su **tutti** gli anni di piano con lo
  stesso criterio delle altre caselle "uguali per tutto il piano" — si legge la scelta del primo
  anno previsto (`spIndexingOf`, `frontend/lib/budget-circolante-step.ts:205-216`).
- **Driver degenere** (denominatore dell'anno base ≤ 0): il motore non indicizza, ricade sul
  comportamento costante/percentuale e dichiara il motivo `"driver degenere"` — mai un fattore
  inventato da un `or 1` di comodo.

### Mutuamente esclusivo con un piano del pregresso sulla stessa voce

Dichiarare un piano di scadenziamento su un saldo (§8) significa «questo saldo lo sto
estinguendo»; dichiarare un driver su una voce significa «questo saldo si rigenera col volume» —
due affermazioni contraddittorie sulla stessa voce. `SP_INDEXING_PLAN_KEY`
(`calculations/forecast_engine.py:78-84`) mappa i tre codici in comune ai saldi del pregresso —
`sp16f`/`sp17f` → `debiti_previdenziali`, `sp16g`/`sp17g` → `altri_debiti`, `sp17d` →
`debiti_fornitori` — e quando quel saldo ha un piano, l'indicizzazione sul codice mappato è
ignorata e dichiarata col motivo `"piano di scadenziamento"`. Vince sempre il piano, mai il
driver: con un piano il generato di quella voce è `base − massa scadenzata`, che
`validate_pregresso` impone uguale a zero — un fattore per zero resterebbe comunque zero, cioè
codice morto che l'utente crederebbe attivo se non fosse dichiarato ignorato.

Altre tre esclusioni, stesso pattern (`SP_INDEXING_GOVERNED`,
`calculations/forecast_engine.py:89-102`, controllato **prima** dell'elenco degli 11 indicizzabili
— per queste sette chiavi il motivo è quello specifico, non il generico "voce non indicizzabile"):
`sp06e`/`sp16e`/`sp17e` sono governate dalla posizione tributaria (§9), `sp16a`/`sp17a` dal piano
di rimborso del debito, `sp06f`/`sp07f` (imposte anticipate) dalla posizione fiscale — nessuna di
queste sette è comunque fra gli 11 codici indicizzabili, quindi l'esclusione dà solo un motivo più
preciso, non un divieto altrimenti assente. Indicizzarle darebbe comunque due padroni allo stesso
numero. E l'interruttore `previdenza_scales_with_personnel`, quando acceso, vince su un
`sp_indexing` scritto per `sp16f`/`sp17f`: è già lui l'indicizzazione di quelle due voci al costo
del personale, col motivo `"governata dall'interruttore previdenza/personale"`.

### `details` — due chiavi, sempre presenti (anche vuote)

| Chiave | Valore |
|---|---|
| `indicizzazione` | dizionario `{codice: {driver, fattore, percentuale_ignorata, valore}}` per ogni voce **davvero** indicizzata quest'anno. `percentuale_ignorata` è `true` quando la riga porta anche una `{codice}_growth_pct` non nulla sulla stessa voce — il driver vince, e la percentuale scritta non ha alcun effetto. `valore` è l'importo che l'indicizzazione ha **davvero** scritto sulla voce (non sempre ricostruibile come `base × fattore`: `sp04` sottrae le svalutazioni cumulate, `sp14` con differenze temporanee somma la quota del deferred) |
| `indicizzazione_ignorata` | lista di `{voce, driver, motivo}` per ogni chiave di `sp_indexing` che non ha avuto effetto — motivi: `"voce non indicizzabile"`, `"governata dall'interruttore previdenza/personale"`, `"piano di scadenziamento"`, `"driver degenere"`, e `"driver sconosciuto"` per un nome di driver fuori dai tre. Quest'ultimo **è raggiungibile**: sulla porta normale — il bulk `PUT /scenarios/{id}/assumptions` (§1), che riceve un dict e non passa dallo schema — è il motore a ignorare il driver e dichiararlo qui; il `Literal` a tre valori lo rifiuta con 422 solo sulle rotte tipizzate per singola riga (`POST /assumptions`, `PUT /assumptions/{year}`) |
