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
(`backend/app/services/assumptions_service.py:318-327`):

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
`toast.warning` col `message`: `app/budget/page.tsx:982-985`, `app/pratica/page.tsx:801`
(`calculateProjectedBS`) e `:895` (`saveProjection12M`). Un quarto chiamante che se ne
dimenticasse dipingerebbe una colonna Proiezione vuota sotto un toast verde.

`POST /generate`, per contrasto, **non** cattura: fa 400 su `ValueError` e 500 su tutto il
resto (`backend/app/api/v1/budget_scenarios.py:936-945`). Lo stesso motore, lo stesso errore,
due esiti HTTP opposti a seconda della porta da cui si è entrati.

## 2. Gli override: due meccanismi, non uno

### 2.1 Conto economico — 32 colonne `ce*_override`

`BudgetAssumptions` porta **32** colonne `ce*_override` (`database/models.py:683-716`), non 31:
`ce01`–`ce20` meno `ce17` (sostituito dalle sue due sotto-voci), più `ce03a` (incrementi di
immobilizzazioni per lavori interni, A.4), `ce08a`–`d`, `ce09a`–`d`, `ce11b`, `ce17`, `ce17a`,
`ce17b`. Lo stesso insieme di 32 compare in `backend/app/schemas/budget.py` (due volte),
nell'allowlist `_CE_OVERRIDE_FIELDS` di `budget_scenarios.py:770-779` e nella mappa
`FIELD_TO_OVERRIDE` di `frontend/app/forecast/income/page.tsx:63`.

Ogni colonna è un **valore assoluto in euro**. `NULL` = usa il calcolo del motore.
`ce20_override` fissa le imposte totali e scavalca `tax_rate` (`forecast_engine.py:730-731`,
`intra_year_engine.py:270-271`); `ce17a_override`/`ce17b_override` sono letti separatamente,
**non** come netto in `ce17_override` (`forecast_engine.py:938-939`).

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
una volta sola alla fine. Attenzione all'ultimo ramo: se la rigenerazione fallisce la risposta
è **500 «Overrides saved but forecast regeneration failed»** — gli override sono già stati
committati e si applicheranno alla prima rigenerazione successiva, anche se questa chiamata
è andata in errore.

Su `/forecast/income` il ciclo è: clic sulla cella previsionale → input in linea → `blur`/Enter
mette la modifica in `pendingEdits` (**sfondo giallo + sottolineatura gialla**) → compare
«Aggiorna Previsionale» → il clic manda tutto in un `PATCH` solo, invalida la cache di
`/analysis` e ricarica. Una cella svuotata manda `null`. Un override **già persistito** si
riconosce da una sottolineatura `border-b-2 border-primary` — il colore del tema, non un blu
fisso — e lo stato si legge dall'oggetto `assumptions` della risposta di `/analysis`
(`app/forecast/income/page.tsx:505-524, 544-548`).

### 2.2 Stato patrimoniale — il sacco JSON `sp_overrides`

`BudgetAssumptions.sp_overrides` è una colonna **JSON** (`models.py:680`), un dizionario
`{campo_sp: valore}`. Non è un residuo: `/forecast/balance` è **editabile** e la scrive
(`frontend/app/forecast/balance/page.tsx:153-183`), passando per la `PUT` per anno; entrambi i
motori la applicano in coda al calcolo dello SP (`forecast_engine.py:1553`,
`intra_year_engine.py:571`), e il ramo a 12 mesi del wizard della pratica ne manda
una versione propria, con tutte le voci SP del periodo (`app/pratica/page.tsx:872`).

`_apply_sp_overrides` (`forecast_engine.py:381-470`) ha tre comportamenti da conoscere:

1. una chiave che non esiste nel risultato è **ignorata in silenzio**;
2. ogni valore è **clampato a ≥ 0**, tranne `sp13_utile_perdita` e
   `sp12h_riserva_neg_azioni_proprie`: un override negativo su qualunque altro campo diventa
   uno zero, senza errore;
3. il dettaglio vince sull'aggregato, e la cassa resta la voce di pareggio a meno che non sia
   stata forzata esplicitamente.

## 3. Precedenza, e che cosa sopravvive a che cosa

Un override **vince sempre** sulla percentuale di crescita della stessa riga: si può cambiare
`revenue_growth_pct` quanto si vuole, se `ce01_override` è valorizzato il ricavo previsionale
non si muove.

E gli override **sopravvivono al salvataggio**:

| Azione dell'utente | Chiamata | Effetto sugli override |
|---|---|---|
| `/budget` → «Salva e Calcola Previsionale» | `PUT /assumptions` (`auto_generate=true`), righe idratate | **conservati** |
| `/budget` → «Ricalcola» **senza** spuntare la casella | `POST /generate` | **conservati** |
| `/budget` → «Ricalcola» **con** *«Azzera le modifiche manuali del CE previsionale»* | `POST /generate?clear_overrides=true` | azzerati — ma vedi sotto |
| `/forecast/income` → svuotare una cella | `PATCH /ce-override` con `value: null` | azzerato solo quello |

`clear_overrides` scorre `assumption.__table__.columns` e mette a `None` ogni colonna il cui
nome **finisce per `_override`** (`budget_scenarios.py:920-924`). `sp_overrides` finisce per
`_overrides`: **non viene azzerato**. La casella dice «del CE previsionale» e in questo è
onesta, ma chi la spunta aspettandosi di tornare al previsionale puro del motore si tiene
tutti gli override di stato patrimoniale.

## 4. I giorni di rotazione derivati dall'anno base

Quando `dso_days` / `dio_days` / `dpo_days` non sono impostati nelle ipotesi, il motore li
deriva dall'anno base con `DAYS = 360` (`forecast_engine.py:1042`):

| | formula | nota |
|---|---|---|
| DSO | `(sp06 − sp06e − sp06f) / ce01 × 360` | solo i crediti **commerciali**: crediti tributari e imposte anticipate sono esclusi perché dipendono dalla posizione fiscale, non dal giro d'affari (`:897-911`) |
| DIO | `sp05 / ce01 × 360` | il denominatore è il **ricavo**, non gli acquisti (`:915-922`) |
| DPO | `sp16d / (ce05 + ce06) × 360` | solo i debiti **verso fornitori**, non l'aggregato `sp16` (`:1012-1019`) |

> **L'aliquota di default non è quella che l'app usa.** Lo schema Pydantic ha
> `tax_rate: Decimal = 24` (`backend/app/schemas/budget.py:148`, l'IRES da sola), ma ogni
> chiamante del frontend manda **27,9** — la miscela IRES 24 + IRAP 3,9 dichiarata in
> `STARTUP_TAX_RATE_PCT` (`app/budget/page.tsx:361`) e ripetuta letterale in
> `app/pratica/page.tsx:780, 877` e in `lib/budget-horizon.ts:237`. Il 24% si vede solo su una
> chiamata che ometta il campo.

Il circolante scala quindi con i ricavi e i costi previsionali, **anche quando questi vengono
da un override CE**: `_calculate_balance_sheet` legge `forecast_inc`, cioè il conto economico
già calcolato con gli override applicati (`:875-876`). Più ricavi → più crediti; più acquisti
→ più debiti verso fornitori; la cassa fa da pareggio, e una cassa negativa diventa debito a
breve.

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
- È una riclassifica, non un flusso: cassa, interessi, risultato e totale del debito bancario non
  cambiano. Avviene dopo il cash sweep, che rimborsa prima il debito bancario pregresso e poi il
  prestito nuovo; il debito bancario pregresso conserva la propria ripartizione.
- `details['prestiti_nuovi_quota_breve']` dichiara la quota ogni anno, anche a zero, per quanto
  `sp16a` ne persiste davvero.

**Perché conta:** `sp16` e `sp17` stanno entrambi nel passivo, quindi il pareggio non vede dove sta
la quota; la vedono CCN, current ratio e circolante di Altman. Sulla base del kit di test (12.345,67
di breve e 23.456,79 di lungo pregresso, 100.000,38 in 4 anni al 4,35%) il current ratio 2027 è
2,0794; con tutto il prestito oltre l'esercizio risultava 2,4206.

Un `sp_overrides` su `sp16a` fissa un totale che **contiene** la quota. Se la porta sotto, il taglio
cade prima sul breve pregresso e la quota dichiarata è ciò che ne resta: un override salvato quando
il prestito stava tutto in `sp17a` oggi toglie anche la quota a breve dal debito.

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
| `database/models.py` | `BudgetAssumptions` — le 32 colonne `ce*_override` e `sp_overrides` |
| `backend/app/schemas/budget.py` | gli stessi campi lato Pydantic (due classi) |
| `backend/app/services/assumptions_service.py` | il bulk, e il `try/except` che produce il 200 con `forecast_generated: false` |
| `backend/app/api/v1/budget_scenarios.py` | `PATCH /ce-override` + `_CE_OVERRIDE_FIELDS`, `POST /generate?clear_overrides`, i 3 endpoint dei commenti AI, `POST /promote` |
| `backend/app/services/promote_service.py` | i due cancelli, la sostituzione, la copia verificata |
| `calculations/forecast_engine.py` | override nel CE, `_apply_sp_overrides`, DSO/DIO/DPO derivati |
| `calculations/intra_year_engine.py` | gli stessi override sul percorso infrannuale |
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
