# Percorso ipotesi budget — lotto 1: sette passi con anteprima

**Data:** 2026-09-08 · **Stato:** approvato dal proprietario nel flusso, spec in revisione
**Origine:** lamentele degli utenti («l'inserimento delle ipotesi è cervellotico»), i tre
mockup del tester del 31/08 (`2026-08-31-ipotesi-budget-mockup.md`), e il prototipo
cliccabile discusso l'8/09 (`2026-09-08-percorso-ipotesi-budget-prototipo.html`, stesso
file dell'artifact «Percorso Ipotesi Budget»).
**Sostituisce:** la tab «Ipotesi» di `frontend/app/budget/page.tsx` (`ScenarioForm`) per gli
scenari da bilancio. Non tocca il modello dati e non tocca il motore, salvo il refactor
descritto al §5.

Un **lotto 2**, con spec separata, estende il motore con lo scadenziamento del pregresso
(incasso dei crediti esistenti, debiti tributari correnti e rateizzati). Questa spec gli
lascia il posto a schermo (§4.6, §4.7) e non ne anticipa la logica.

---

## 1. Il problema

Oggi le ipotesi sono un elenco unico: undici righe «essenziali», un accordion «Avanzate» con
quattro gruppi (uno da 24 righe, eterogeneo), un generatore automatico nascosto nell'altra
tab, e **nessun numero derivato a schermo**. Per vedere l'effetto di una percentuale sui
ricavi si salva, si genera, si va in CE Prev. o Indici, si torna indietro. Il percorso
misurato a luglio era di 40-55 interazioni e 8 decisioni di navigazione
(`docs/superpowers/2026-07-06-project-analysis.md:107-135`); la semplificazione di luglio
ha ridotto le celle, non il ciclo di verifica.

Due dettagli aggravano: le righe «Materie prime %» e «Servizi %» scrivono lo stesso valore
in due colonne (variabile e fissa), quindi la divisione fisso/variabile, che l'utente
vorrebbe usare per ragionare, di fatto non esiste finché non apre le Avanzate; e il
«Rimborso debiti bancari (anni)» convive con i piani dettagliati che lo disattivano.

## 2. Obiettivo

Un percorso in **sette passi**, nell'ordine in cui un analista ragiona: fatturato → costi
principali con quota fissa e variabile → voci minori del CE → capitale circolante →
pregresso e nuovo → imposte. A ogni passo, accanto agli input, **le sole righe del
previsionale che quel passo muove**, ricalcolate a ogni modifica **dal motore Python**
senza salvare. Il percorso finisce con «Salva e calcola previsionale» e porta alle tab
CE Prev. e SP Prev. esistenti, dove si applicano i correttivi finali: niente riepilogo.

Criteri di successo:
- l'utente vede ricavi, costi (totale, di cui fissi, di cui variabili, in % sul fatturato)
  e MOL cambiare mentre digita, senza lasciare la pagina;
- nessun secondo motore in TypeScript (regola del repo, memoria «un solo motore di
  proiezione»): ogni numero derivato viene dal motore Python via endpoint di anteprima;
- uno scenario salvato oggi si riapre nel nuovo percorso con gli stessi valori e produce
  lo stesso previsionale (parità byte-per-byte sul `ForecastYear`);
- gli override fatti in CE Prev. e SP Prev. sopravvivono al nuovo salvataggio, esattamente
  come oggi (§6).

## 3. Non obiettivi

- Nessun campo nuovo nel modello `BudgetAssumptions`, nessuna migrazione.
- Nessuna modifica alla semantica del motore (crescita anno su anno, override che vince
  sulla percentuale, cassa a saldo verso l'alto, errore su fabbisogno scoperto).
- Il percorso **Startup** (`startupMode`) non entra nel wizard: guida il CE con override
  assoluti, non con percentuali, e i suoi passi sarebbero diversi. Conserva il form attuale
  (rinominato `ScenarioFormStartup`, invariato) finché non avrà una spec propria. Vedi §9.
- Scenari `infrannuale`: hanno la tab Proiezione, non passano da `/budget`.
- Cruscotto fisso di KPI sempre visibile: scelta esplicita del proprietario, solo le
  righe del passo.

## 4. Il percorso

### 4.0 Cornice e navigazione

La pagina `/budget` in modalità modifica scenario (da bilancio) rende, sotto lo stepper
della pratica che c'è già (fasi + viste del Previsionale, con «Budget» attiva), una
**guida orizzontale a sette passi** dentro il contenuto della pagina: card con bordo e
ombra come le altre, tre etichette di gruppo sopra i passi — *Impostazione* (1),
*Conto economico* (2-4), *Stato patrimoniale* (5-7) — e a destra l'orizzonte
(«3 anni · 2026 – 2028»). Non è una terza barra di navigazione: la colonna sinistra
appartiene al contenitore Formula Finance e in alto ci sono già due righe.

Ogni passo è cliccabile in qualunque ordine (non ci sono gate: le ipotesi hanno sempre un
default valido). Un passo già visitato mostra la spunta. Sotto ogni passo il layout è a
**due colonne**: input a sinistra, **anteprima** a destra, appiccicata allo scroll; sotto
1100px le colonne si impilano con l'anteprima in fondo.

In fondo alla pagina, la barra fissa con «Indietro» / «Avanti»; al passo 7 «Avanti»
diventa «Salva e calcola previsionale». Il primario in cima allo stepper della pratica
(`usePrimaryAction`) **rispecchia sempre** il pulsante in fondo, passo per passo: al passo
3 dice «Avanti», al 7 «Salva e calcola previsionale». Il tester aveva osservato che il
pulsante in fondo non si vede; uno sempre visibile in alto che dice la stessa cosa risolve
senza invitare a saltare i passi.

Il passo corrente è ricordato in `localStorage` per scenario (`budget-wizard-step:{id}`),
letto in un `useEffect`, mai nell'inizializzatore (regola del repo).

### 4.1 Passo 1 — Scenario

Input: nome, descrizione, «scenario attivo», anno base (sola lettura, con la chiosa già
calcolata da `baseYearNote`), orizzonte. L'orizzonte è un controllo segmentato **3 / 5**
più un campo numerico per gli altri valori (1-5), sopra `lib/budget-horizon.ts` così com'è.

**Punto di partenza.** Il generatore automatico (`AutoGeneratorCard`) esce dalla tab
«Informazioni» e diventa la seconda card di questo passo, sempre aperta: un solo input
«Inflazione attesa» e la tabella delle sette tendenze storiche. Comportamento:
- scenario **nuovo** (nessuna ipotesi salvata): le percentuali dei passi 2-4 vengono
  precompilate dalla tendenza al primo render, senza premere nulla;
- scenario **esistente**: le ipotesi salvate vincono; il pulsante «Riparti dalla tendenza»
  le sovrascrive dopo una conferma che elenca quali righe cambieranno.

Anteprima: il bilancio dell'anno base con i tre anni di storico (ricavi, incidenza di
materie, servizi, personale, MOL, giorni medi), letto da `historicalData` come oggi.

### 4.2 Passo 2 — Fatturato

Input: `revenue_growth_pct`, `other_revenue_growth_pct`, una riga per voce, una colonna per
anno di piano, con la colonna 2025 in sola lettura. Nota fissa: «Le percentuali si applicano
all'anno precedente, non al 2025».

Anteprima: ricavi delle vendite (valore, variazione % e assoluta sull'anno precedente),
altri ricavi, valore della produzione, crescita cumulata sul base; un piccolo grafico a
barre (SVG, senza libreria) dei ricavi base + anni di piano.

### 4.3 Passo 3 — Costi principali

Due card di input.

**Composizione al {anno base}.** Per materie prime (`ce05`) e servizi (`ce06`): l'importo
dell'anno base, uno **slider 0-100 a passi di 5** con campo numerico accanto, e sotto la
barra a due colori con gli importi in euro «Fissa · N €» / «Variabile · M €». Lo slider
scrive `fixed_materials_percentage` / `fixed_services_percentage` **in tutti gli anni di
piano** con lo stesso valore: il modello è per anno, l'interfaccia no, ed è una scelta
deliberata (una quota fissa che cambia di anno in anno è un'ipotesi che nessun utente
ha mai chiesto). Se uno scenario già salvato ha valori diversi fra anni, lo slider mostra
il primo anno e un avviso «valori diversi per anno: muovendo lo slider li allinei».

**Variazione % sull'anno precedente.** Tabella in due gruppi con legenda a colori:
- *Costi variabili* (ambra): materie prime · parte variabile
  (`variable_materials_growth_pct`), servizi · parte variabile (`variable_services_growth_pct`);
- *Costi fissi* (blu): materie prime · parte fissa (`fixed_materials_growth_pct`), servizi ·
  parte fissa (`fixed_services_growth_pct`), personale (`personnel_growth_pct`), godimento
  beni di terzi (`rent_growth_pct`).

La colonna 2025 di ogni riga mostra la quota in euro corrispondente allo slider. Una riga
la cui quota è zero (slider a 0 o a 100) è resa spenta e non editabile. Il **dual-write**
delle righe «Materie prime %» e «Servizi %» sparisce: erano una scorciatoia per nascondere
la divisione, che ora è il centro del passo.

Default per uno scenario nuovo: le righe variabili copiano la percentuale dei ricavi, le
fisse l'inflazione del passo 1. Il pulsante «Allinea le variabili ai ricavi» ricopia
`revenue_growth_pct` nelle due righe variabili, per chi cambia il fatturato dopo aver
toccato i costi. Nessun vincolo automatico: le righe restano indipendenti.

Anteprima, per anno e con la colonna base:
- ricavi delle vendite (riferimento);
- **costi principali** = ce05 + ce06 + ce07 + ce08, con % sui ricavi;
- di cui **fissi** e di cui **variabili**, ciascuno con % sui ricavi — i componenti
  vengono dal motore (§5.3), non da un ricalcolo lato client;
- le quattro voci, ciascuna con % sui ricavi;
- **MOL stimato** con margine %;
- una barra impilata fissi/variabili per anno e il peso dei fissi sul totale, base → ultimo anno;
- sotto un separatore, «Debiti verso fornitori stimati» con la didascalia «con i giorni di
  pagamento fermi al 2025 (78 gg)». Non è una logica speciale: finché `dpo_days` è vuoto
  il motore usa i giorni dell'anno base, e la nota dice all'utente che si regolano al passo 5.

### 4.4 Passo 4 — Altre voci del conto economico

Input: oneri diversi di gestione (`other_costs_growth_pct`). È l'unica voce minore del CE
guidata da una percentuale; le altre righe di CE (ce02, ce03, ce10, ce11, ce13-ce19) sono
riportate costanti dal motore e si forzano solo da CE Prev.

Card «Calcolate dal piano» (sola lettura, badge *automatico*): ammortamenti (quote del
base più `depreciation_rate` sui nuovi investimenti del passo 6), oneri finanziari (sul
debito del passo 6), imposte (aliquota del passo 7). Ogni riga mostra «base → ultimo anno».
Nota fissa: «Un valore forzato a mano nel CE previsionale vince sempre su queste regole, e
resta finché non lo azzeri dal dialogo Ricalcola».

Anteprima: CE sintetico — valore della produzione, costi principali, oneri diversi, MOL,
ammortamenti, risultato operativo, oneri finanziari, risultato ante imposte.

### 4.5 Passo 5 — Capitale circolante

Input, card «Giorni medi»: `dso_days`, `dio_days`, `dpo_days` per anno, vuoto = «come nel
2025» con il segnaposto `auto N` calcolato come oggi da `computeAutoDays`
(`lib/budget-turnover.ts`, che resta uno specchio dichiarato della derivazione del motore).
Nota fissa sui soli crediti e debiti commerciali e sui 360 giorni.

Card «Voci minori dell'attivo e del passivo», chiusa di default con «Mostra tutte»:
`receivables_long_growth_pct`, `sp01`, `sp04`, `sp06e`, `sp06f`, `sp08`, `sp10`, `sp14`,
`sp16f`, `sp16g`, `sp17d`, `sp17f`, `sp17g`, `sp18` (tutti `*_growth_pct`), più
`previdenza_scales_with_personnel` e `tfr_accrual_suspended`. `sp16e` e `sp17e` (debiti
tributari) vanno al passo 7.

Anteprima: crediti verso clienti (con i giorni applicati), rimanenze, debiti verso
fornitori, capitale circolante commerciale, in % dei ricavi, assorbimento di cassa
nell'anno. I giorni applicati sono quelli restituiti dal motore (§5.3), così il segnaposto
e la riga non possono più divergere (#31).

### 4.6 Passo 6 — Pregresso e nuovo

Due colonne di **input**, separate a vista perché non si mescolano:

**Scadenziamento del pregresso** (saldi al 31/12 dell'anno base):
- debiti bancari esistenti: importo dal base (di cui a breve), `existing_debt_repayment_years`;
- altri finanziatori: importo dal base, `altri_finanz_repayment_years`;
- crediti verso clienti al base: importo, controllo **spento** con badge *lotto 2*;
- debiti tributari: importo, con «correnti / rateizzati» **spenti** con badge *lotto 2*.
- Nota: «Con un piano dettagliato in Finanziamenti la durata generica del rimborso viene
  ignorata: vale il piano» (comportamento attuale del motore).

Sotto, la card `FinancingLoansGrid` **così com'è** (piani dettagliati, copertura del debito
base, rata stimata), che oggi vive nella tab Ipotesi.

**Generato dal previsionale**:
- nuovo finanziamento, **una riga per anno di piano** come nel modello (`financing_amount`,
  `financing_duration_years`, `financing_interest_rate`): l'anno della riga è l'anno di
  erogazione, e il motore assembla i piani di tutti gli anni in un'unica lista;
- nuovi investimenti per anno: `tangible_investments`, `intangible_investments`;
- «Mostra tutte»: `depreciation_rate`, `depreciation_rate_intangible`,
  `asset_disposal_nbv`, `asset_disposal_proceeds`, `cash_sweep_enabled`,
  `cash_sweep_min_cash`.

Anteprima: debiti bancari esistenti, nuovo finanziamento, altri finanziatori,
immobilizzazioni nette, **cassa** (badge *a saldo*), PFN, PFN/MOL. Se il motore segnala un
fabbisogno scoperto, un avviso rosso con anno e importo: «Il previsionale non verrà
generato finché non lo copri: un nuovo finanziamento, meno investimenti, o un rimborso più
lungo del pregresso». Altrimenti la riga verde «La cassa resta positiva in tutti gli anni».

### 4.7 Passo 7 — Imposte

Input, card «Aliquota»: aliquota effettiva dell'anno base (sola lettura, badge *usata dal
piano*, da `computeEffectiveTaxRate`), `tax_rate` come «aliquota forzata, vuota = usa
l'effettiva», `tax_advances_paid`. Card «Differenze temporanee»:
`TaxTemporaryDifferencesGrid` così com'è. Card «Pagamento dei debiti tributari»:
`sp16e_growth_pct`, `sp17e_growth_pct` come oggi, più le due righe «correnti /
rateizzati» **spente** con badge *lotto 2* e la nota che spiega come si muove oggi la
posizione tributaria (precedente + imposte − acconti).

Anteprima: risultato ante imposte, imposte con l'aliquota applicata, utile netto, debiti
tributari a fine anno.

**Chiusura.** «Salva e calcola previsionale» esegue `handleSave` come oggi (§6), legge
`forecast_generated` e non l'HTTP 200 (invariante del repo), e a esito positivo naviga a
`/forecast/income`, la vista successiva nello stepper della pratica. A esito negativo il
toast riporta `message` e la pagina resta sul passo 7, o sul passo 6 se il messaggio è un
fabbisogno scoperto (`Unfunded financing requirement`).

## 5. Anteprima: l'endpoint e il refactor del motore

### 5.1 Endpoint

`POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/preview`

Corpo: `{"assumptions": [BudgetAssumptionsCreate, ...]}`, la stessa forma del bulk
`PUT /assumptions`. Dipende da `get_current_user_id` e da
`validate_company_owned_by_user` come ogni altra route; azienda altrui → 404.

Risposta 200, sempre, anche quando il motore si ferma:

```json
{
  "scenario_id": 12,
  "base_year": 2025,
  "forecast_years": [
    {
      "year": 2026,
      "income_statement": { "ce01_ricavi_vendite": 2597000.0, ... },
      "balance_sheet": { "sp09_disponibilita_liquide": 131240.0, ... },
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

`error` è `null` oppure `{"year": 2027, "message": "Unfunded financing requirement 84.120,00"}`:
in quel caso `forecast_years` contiene gli anni calcolati **prima** dell'errore, e il
client li mostra con l'avviso del §4.6. Gli errori di validazione dell'ingresso (anno ≤
base, anni duplicati, corpo vuoto) restano 400 come nel bulk: sono errori del chiamante,
non del piano.

**Non scrive nulla.** Nessun `db.add`, nessun `commit`, nessuna potatura degli anni fuori
piano. Le ipotesi del corpo diventano istanze transitorie di `BudgetAssumptions` costruite
con lo stesso mapping campo-per-campo del bulk (estratto in una funzione
`build_assumption_row(scenario_id, data) -> BudgetAssumptions` condivisa dai due percorsi,
così un campo aggiunto al bulk non può mancare all'anteprima), **mai aggiunte alla
sessione**. Il test di §8 lo verifica contando le righe prima e dopo.

### 5.2 Refactor: calcolo separato dalla persistenza

`ForecastEngine.generate_forecast(scenario_id)` oggi fa tre cose in un solo metodo: legge,
calcola, scrive (`calculations/forecast_engine.py:366-568`). Diventa:

```python
def compute_forecast(self, scenario, base_fy, assumptions, *, stop_on_error=True) -> ForecastComputation
def generate_forecast(self, scenario_id) -> Dict   # legge → compute (stop_on_error=True) → persiste, come oggi
```

`ForecastComputation` è una dataclass con `years: list[ForecastYearResult]` (anno, dict
CE, dict SP, dict `details`) e `error: ForecastError | None` (anno, messaggio). Con
`stop_on_error=True` (il default, usato da `generate_forecast`) l'eccezione del motore
sale come oggi: **nulla cambia per PUT bulk, PATCH ce-override e POST generate**. Con
`stop_on_error=False` (solo l'anteprima) il `ValueError` alzato dentro il ciclo viene
catturato, gli anni già calcolati restano in `years` e l'errore va in `error`.

Le letture (scenario, anno base con `get_fy_prefer_full`, gate `_validate_forecast_source`,
guardia sui ricavi negativi, assemblaggio dei `financing_loans`) restano in
`generate_forecast` e vengono replicate dal servizio di anteprima attraverso una funzione
condivisa `load_forecast_source(db, scenario_id)`; i controlli di ingresso che alzano
`ValueError` prima del ciclo (ricavi negativi, residui dei piani ≠ debito base) diventano
per l'anteprima un `error` con `year = null`.

### 5.3 I dettagli che il motore deve dichiarare

Il ciclo di calcolo produce oggi due dict destinati a `ForecastIncomeStatement(**inc)` e
`ForecastBalanceSheet(**bs)`, quindi non possono ospitare chiavi in più. `details` è un
terzo dict, per anno, riempito da `_calculate_income_statement` e
`_calculate_balance_sheet` attraverso un parametro `details: dict | None = None`:
- `ce05_fixed`, `ce05_variable`, `ce06_fixed`, `ce06_variable` — i due addendi della
  formula già scritta a `forecast_engine.py:645-668`; con `ce05_override` /
  `ce06_override` valorizzato i quattro valgono `null`, perché la divisione non è definita
  su un importo forzato, e l'anteprima mostra «—» con la chiosa «forzato in CE Prev.»;
- `dso_applied`, `dio_applied`, `dpo_applied` — i giorni effettivamente usati
  (`forecast_engine.py:946-957` e omologhi), che siano forzati o derivati.

Sono sette chiavi, **dichiarate sempre** (invariante del repo: una chiave assente vale
zero, quindi tacere equivale a dichiararsi puliti). Non vengono persistite.

### 5.4 Prestazioni e concorrenza

Il ciclo è aritmetica `Decimal` in memoria, nell'ordine dei millisecondi; il costo di
`generate_forecast` è la persistenza su SQLite, che qui non c'è. Il client chiama
l'anteprima con **debounce di 400 ms** dopo l'ultima modifica e annulla la chiamata in
volo con `AbortController` quando ne parte una nuova; una risposta arrivata dopo una
richiesta più recente viene scartata (numero di sequenza). La sessione SQLAlchemy resta in
sola lettura: nessun rischio di scrittura concorrente.

## 6. Stato, salvataggio, override

Lo stato è **lo stesso** di oggi: `assumptions: Record<anno, Partial<BudgetAssumptionsCreate>>`,
idratato da `GET /assumptions` con **tutti** i campi, compresi i 32 `ce*_override`,
`sp_overrides` e i cinque campi morti (`investments`, `receivables_short_growth_pct`,
`payables_short_growth_pct`, `interest_rate_*`). Il bulk lato server è delete-all +
reinsert: **ogni campo non rispedito viene cancellato**. Il wizard non costruisce mai il
payload da zero: scrive nella mappa idratata e la rispedisce intera, riga per anno, come
`handleSave` fa oggi (`page.tsx:1187-1197`). Il flag `idratato` continua a chiudere il
salvataggio finché le ipotesi salvate non sono atterrate.

Conseguenze da dire all'utente, non da nascondere:
- una riga con `ce05_override` mostra nel passo 3 il badge «forzato in CE Prev.» e
  l'anteprima ne segue l'importo forzato, non la percentuale (l'override vince);
- «Riparti dalla tendenza» non tocca gli override;
- il dialogo Ricalcola resta nella lista scenari e resta l'unico posto che li azzera
  (solo le colonne `_override`, mai `sp_overrides`: già documentato).

La creazione manuale di scenari resta disattivata fuori da `startupMode`: gli scenari
nascono dal ponte pratica, come oggi.

## 7. Architettura frontend

```
frontend/
  app/budget/page.tsx                 # ScenariosList + dialogo Ricalcola come oggi;
                                      # ScenarioForm → BudgetWizard (da bilancio) | ScenarioFormStartup
  components/budget/wizard/
    BudgetWizard.tsx                  # stato (mappa idratata), guida, barra, usePrimaryAction, salvataggio
    WizardRail.tsx                    # la guida orizzontale a sette passi
    PreviewPanel.tsx                  # card di anteprima: tabella per anno + avvisi, riceve righe già calcolate
    steps/StepScenario.tsx            # 4.1 (assorbe AutoGeneratorCard)
    steps/StepFatturato.tsx           # 4.2
    steps/StepCosti.tsx               # 4.3 (slider + tabella a due gruppi)
    steps/StepAltreVociCE.tsx         # 4.4
    steps/StepCircolante.tsx          # 4.5
    steps/StepPregressoNuovo.tsx      # 4.6 (riusa FinancingLoansGrid)
    steps/StepImposte.tsx             # 4.7 (riusa TaxTemporaryDifferencesGrid)
  hooks/use-forecast-preview.ts       # debounce 400 ms, AbortController, sequenza, stato {data, error, loading}
  lib/budget-wizard-steps.ts          # PURO: i sette passi, i gruppi, campo → passo, testo dei pulsanti
  lib/budget-preview-rows.ts          # PURO: dalla risposta di anteprima alle righe di ogni passo
  lib/api.ts                          # previewForecast(companyId, scenarioId, rows, signal)
  types/api.ts                        # ForecastPreviewResponse, ForecastYearDetails
```

`lib/budget-*` segue la regola di `lib/pratica-*`: **mai** import da `app/` o
`components/`, testabile in `environment: node`. `budget-preview-rows.ts` fa solo
l'aritmetica che ricapitola ciò che è a schermo — somme di voci restituite dal motore,
percentuali sui ricavi, differenze anno su anno, formattazione. Non deriva nulla: la
divisione fissi/variabili e i giorni applicati arrivano da `details` (§5.3). Se una riga
richiede un numero che il motore non restituisce, si aggiunge una chiave a `details`, non
una formula al client.

`AssumptionsGrid` e `assumption-rows.ts` restano per lo Startup; il wizard ha le proprie
tabelle per anno (più semplici: niente dual-write, niente badge di divergenza). Le regole
di validazione per campo (min, max, step, nullable) si estraggono da `assumption-rows.ts`
in `lib/budget-field-rules.ts` per essere condivise.

`components/budget/AutoGeneratorCard` e `calculateTrend`/`deriveYear` si spostano da
`page.tsx` a `lib/budget-trend.ts` (puro) + `steps/StepScenario.tsx`.

## 8. Test

**Backend** (`tests/test_forecast_preview.py`, stile degli script esistenti):
1. *Parità*: per uno scenario salvato, `compute_forecast` restituisce gli stessi CE e SP
   che `generate_forecast` persiste, al centesimo, su tutti gli anni.
2. *Nessuna scrittura*: dopo `POST /preview` il conteggio di `BudgetAssumptions`,
   `ForecastYear`, `ForecastBalanceSheet`, `ForecastIncomeStatement` è invariato e le
   ipotesi persistite sono identiche (anche con un corpo diverso da quello salvato).
3. *Fabbisogno scoperto*: investimenti fuori scala → 200 con `error.year` sul primo anno
   scoperto e `forecast_years` con i soli anni precedenti; `generate_forecast` sullo
   stesso scenario continua ad alzare.
4. *Dettagli dichiarati*: le sette chiavi di `details` ci sono in ogni anno; con
   `ce05_override` i quattro componenti di ce05/ce06 valgono `null`; `ce05_fixed +
   ce05_variable == ce05` al centesimo altrimenti.
5. *Proprietà*: scenario di un altro utente → 404.
6. *Il bulk non cambia*: la suite esistente sulle assumptions passa invariata.

**Frontend** (Vitest, `environment: node`):
- `lib/budget-wizard-steps.test.ts`: sette passi in ordine, ogni campo esposto appartiene
  a un solo passo, i cinque campi morti a nessuno, il testo del primario per passo;
- `lib/budget-preview-rows.test.ts`: righe del passo 3 da una risposta fissa (totale = somma
  delle quattro voci, fissi + variabili = totale, % sui ricavi), righe del passo 6 con e
  senza `error`, «—» sui componenti `null`;
- `hooks/use-forecast-preview.test.ts` (jsdom): debounce, annullamento della chiamata
  precedente, scarto della risposta fuori sequenza.

**A mano, con il collaudatore** (dev server, browser reale): scenario esistente riaperto
nel wizard → stessi valori nei sette passi; salva senza modifiche → `ForecastYear`
identico; slider a 0 e 100 → righe spente; fabbisogno scoperto al passo 6 → avviso, e il
salvataggio al passo 7 riporta al passo 6; override in CE Prev. → badge nel passo 3 e
sopravvivenza al salvataggio.

## 9. Decisioni prese e alternative scartate

| Decisione | Alternativa scartata | Perché |
|---|---|---|
| Guida orizzontale dentro la pagina | stepper verticale a sinistra (prototipo v1) | la colonna sinistra è del contenitore; in alto ci sono già due barre |
| Anteprima locale al passo, niente cruscotto | 5-6 KPI fissi | scelta del proprietario: l'utente ragiona un blocco alla volta |
| Anteprima dal motore Python via endpoint | ricalcolo in TypeScript | regola del repo: il gemello TS era divergito in quattro punti e mostrava tre bilanci diversi |
| `details` come terzo dict del motore | chiavi extra nei dict CE/SP | quei dict costruiscono le righe ORM; una chiave in più rompe la persistenza |
| Slider unico che scrive tutti gli anni | uno slider per anno | nessun utente ha chiesto una quota fissa che cambia nel tempo; il modello resta per anno |
| Niente riepilogo, chiusura su CE Prev. | passo 8 «Riepilogo» (prototipo v1) | scelta del proprietario: i correttivi finali si fanno nelle tab esistenti |
| Startup fuori dal wizard | un wizard con «modalità importi» | passi diversi, override al posto delle percentuali: spec propria |
| Primario in alto = pulsante in fondo | nascosto fino al passo 7 (prototipo) | il tester non trovava il pulsante in fondo; «Avanti» in alto non invita a saltare |
| Aliquota vuota = effettiva | default 24 dello schema | il 24 non gira mai (CLAUDE.md); il campo esprime la scelta reale |

## 10. Documentazione da aggiornare nello stesso lotto

- `CLAUDE.md` › Invarianti › Previsionale: «`POST /preview` non scrive nulla e risponde
  200 anche a un piano che si ferma: leggere `error`, non lo status»; «lo slider della quota
  fissa scrive tutti gli anni»; Quick Reference: il workflow budget cita l'anteprima.
- `docs/budget/API-PREVISIONALE.md`: sezione sull'anteprima (corpo, risposta, `details`,
  `error`), e la nota che il bulk e l'anteprima condividono `build_assumption_row`.
- `docs/frontend/PRATICA-PERCORSO.md`: la vista Budget descritta come sette passi;
  `docs/frontend/LAYOUT-SP-CE.md` non cambia (nessuna voce nuova).
- `docs/superpowers/specs/2026-08-31-ipotesi-budget-mockup.md`: stato → «superato da
  questa spec».
- `.claude/agents/collaudatore.md`: fra i terreni di collaudo, il percorso a sette passi e la
  corrispondenza fra l'anteprima di ogni passo e le tab CE Prev. / SP Prev. dopo il salvataggio.

## 11. Fuori ambito, rimandato al lotto 2

Con spec propria, da scrivere subito dopo l'approvazione di questa: incasso dei crediti
esistenti con un proprio piano (oggi il DSO sostituisce lo stock), debiti tributari divisi
in correnti e rateizzati con piano di rate (oggi: precedente + imposte − acconti), e la
regola generale «le voci patrimoniali generate dal previsionale sono separate dallo
scadenziamento del pregresso» anche per i debiti verso fornitori e i debiti previdenziali.
Il lotto 1 lascia i controlli spenti con badge *lotto 2* nei passi 6 e 7, così il posto è
già deciso e il lotto 2 aggiunge campi e logica senza spostare nulla a schermo.
