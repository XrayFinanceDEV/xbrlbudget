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
`cassa_sotto_minimo` (§10) — il bulk e l'anteprima condividono lo stesso motore e lo stesso dict,
quindi nessuna di queste manca da una delle due porte.

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
«nessun piano»: il motore usa la formula di oggi **intera**, lato breve e lato lungo, ed è il
comportamento di prima del lotto al centesimo (`mode: "legacy"`, sotto).

- **Solo sulla riga del primo anno di piano.** `pregresso` su una riga successiva alza
  `pregresso is allowed only in the first forecast year` (`calculations/forecast_engine.py:1181-
  1186`). È una fotografia dell'anno base, non un'ipotesi per-anno.
- **`opening` deve coincidere col bilancio base**, tolleranza 0,01 €, o il motore si ferma con
  «il saldo di apertura di {voce} è cambiato ({dichiarato} → {base}): rivedi lo scadenziamento»
  (`validate_pregresso`, `calculations/forecast_engine.py:334-362`).
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
smette di applicarsi (`calculations/forecast_engine.py:2116-2145` per i crediti, `:2442-2468` per
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

- **saldo pagato in N** = il debito tributario **generato a fine N−1**, al netto del credito
  tributario di apertura fino a capienza (l'eccedenza resta credito). Per N = 1 è la quota
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
  `sp06e(N)` = credito generato + eccedenza del credito di apertura non ancora usata.

Uscita di cassa dell'anno = saldo + acconti + rate, attraverso il plug come tutto il resto.

**Via manuale.** `sp06e_growth_pct` o `sp16e_growth_pct` valorizzati saltano tutto questo, come
prima del lotto: i debiti tributari si muovono per crescita percentuale, e un piano tributario
scritto insieme a quelle percentuali produce `pregresso_ignored: ["debiti_tributari"]` invece di
applicarsi a metà.

### `details['imposte']` — sempre presente, ogni anno

| Chiave | Valore |
|---|---|
| `current_tax` | l'imposta corrente dell'anno (da `_tax_components`, le differite restano fuori) |
| `saldo_paid` | il saldo versato quest'anno |
| `acconti_paid` | l'acconto versato quest'anno |
| `rate_paid` | le rate del rateizzato versate quest'anno |
| `generated_debt` | il debito tributario generato a fine anno (→ `sp16e` dell'anno prossimo) |
| `generated_credit` | il credito tributario generato a fine anno |
| `opening_credit_left` | il credito di apertura non ancora usato |
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
