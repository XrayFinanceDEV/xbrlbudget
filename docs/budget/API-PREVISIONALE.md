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
(`backend/app/services/assumptions_service.py:221-229`):

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
`toast.warning` col `message`: `app/budget/page.tsx:1088`, `app/pratica/page.tsx:873`
(`calculateProjectedBS`) e `:957` (`saveProjection12M`). Un quarto chiamante che se ne
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
`ce20_override` fissa le imposte totali e scavalca `tax_rate` (`forecast_engine.py:541-542`,
`intra_year_engine.py:270-271`); `ce17a_override`/`ce17b_override` sono letti separatamente,
**non** come netto in `ce17_override` (`forecast_engine.py:737-738`).

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
motori la applicano in coda al calcolo dello SP (`forecast_engine.py:1341`,
`intra_year_engine.py:571`), e il ramo a 12 mesi del wizard della pratica ne manda
una versione propria, con tutte le voci SP del periodo (`app/pratica/page.tsx:933-937`).

`_apply_sp_overrides` (`forecast_engine.py:236-324`) ha tre comportamenti da conoscere:

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
deriva dall'anno base con `DAYS = 360` (`forecast_engine.py:836`):

| | formula | nota |
|---|---|---|
| DSO | `(sp06 − sp06e − sp06f) / ce01 × 360` | solo i crediti **commerciali**: crediti tributari e imposte anticipate sono esclusi perché dipendono dalla posizione fiscale, non dal giro d'affari (`:897-911`) |
| DIO | `sp05 / ce01 × 360` | il denominatore è il **ricavo**, non gli acquisti (`:915-922`) |
| DPO | `sp16d / (ce05 + ce06) × 360` | solo i debiti **verso fornitori**, non l'aggregato `sp16` (`:1012-1019`) |

> **L'aliquota di default non è quella che l'app usa.** Lo schema Pydantic ha
> `tax_rate: Decimal = 24` (`backend/app/schemas/budget.py:148`, l'IRES da sola), ma ogni
> chiamante del frontend manda **27,9** — la miscela IRES 24 + IRAP 3,9 dichiarata in
> `STARTUP_TAX_RATE_PCT` (`app/budget/page.tsx:321`) e ripetuta letterale in
> `app/budget/page.tsx:990` e in `app/pratica/page.tsx:851, 938`. Il 24% si vede solo su una
> chiamata che ometta il campo.

Il circolante scala quindi con i ricavi e i costi previsionali, **anche quando questi vengono
da un override CE**: `_calculate_balance_sheet` legge `forecast_inc`, cioè il conto economico
già calcolato con gli override applicati (`:875-876`). Più ricavi → più crediti; più acquisti
→ più debiti verso fornitori; la cassa fa da pareggio, e una cassa negativa diventa debito a
breve.

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
| `frontend/lib/api.ts` | `bulkUpsertAssumptions`, `patchCeOverrides`, `generateForecast(clearOverrides)`, `promoteProjection` |
