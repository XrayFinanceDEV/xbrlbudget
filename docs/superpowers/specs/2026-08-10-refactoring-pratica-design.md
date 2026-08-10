# Refactoring di `app/pratica/page.tsx` + gate al render

Data: 2026-08-10
Stato: approvato dall'utente (design), spec da rivedere

## Il problema

`frontend/app/pratica/page.tsx` è a 6.019 righe. Contiene, in un unico file:
funzioni pure di calcolo (indicatori, scoring, rating di crisi, costruzione delle
righe di bilancio), sei componenti React completi, ~500 righe di tabelle di
costanti per le rettifiche, e il componente wizard che possiede lo stato.

Due conseguenze concrete, non estetiche:

1. **Le funzioni di calcolo non sono testabili.** Sono dichiarate a livello di
   modulo in un file il cui unico export è `export default function
   InfraannualePage`. Non sono importabili, quindi non sono coperte da alcun
   test — e sono esattamente quelle da cui dipendono i rating mostrati
   all'utente (`computeIndicators`, `scoreIndicator`, `computeCrisisRating`).
2. **Il gate di percorso è applicato solo alla navigazione.** Le otto tab si
   rendono con `{activeTab === "x" && …}` senza consultare `pratica-steps.ts`.
   Ogni sito che chiama `setActiveTab` deve ricordarsi di controllare i gate.

Questo lavoro chiude entrambi.

## Obiettivi

- `page.tsx` da 6.019 a ~1.850 righe, spostando codice **senza riscriverlo**.
- Le funzioni pure diventano importabili e coperte da test.
- Il gate diventa strutturale: lo impone il render, non la disciplina dei chiamanti.

## Non obiettivi

- **Non** si decompone il componente wizard in tab-componenti. Richiederebbe di
  inventare un'interfaccia per 12 `useState` e ~10 handler oggi solo nella
  closure: interfacce inventate durante un refactoring sono il modo in cui
  entrano le regressioni. Resta un follow-up.
- **Non** si fondono i formatter della pratica con `lib/formatters.ts`.
  `formatCurrency` lì ha zero decimali, `formatEuro` qui ne ha due: sono
  funzioni diverse con lo stesso mestiere, fonderle cambierebbe l'output di
  dieci pagine.
- **Non** si estende il gate alle rotte previsionali (`/analysis`,
  `/forecast/*`, `/cashflow`, `/report`). Sono raggiungibili anche **fuori** da
  una pratica, dalla nav piatta: bloccarle richiede di distinguere i due casi, e
  il modo in cui falliscono oggi è una pagina senza dati, non un'azione
  sbagliata.
- **Non** si tocca `app/budget/page.tsx` (1.826 righe), che ha lo stesso
  problema in scala minore.

## Decisioni prese

**Collocazione: file piatti in `lib/`**, come `lib/pratica-format.ts`, accanto al
`lib/pratica-steps.ts` che c'è già. Una cartella `lib/pratica/` obbligherebbe a
spostarci dentro anche `pratica-steps.ts` per coerenza — sei importatori, il file
di test e diversi riferimenti in `CLAUDE.md` — churn senza guadagno funzionale.

**Ambito: solo il meccanico.** Si spostano i moduli puri e i sei componenti che
hanno già un'interfaccia props esplicita e non catturano nulla dalla closure
della pagina. Nessuna interfaccia nuova.

**Rete di test: caratterizzazione.** Si fissa il comportamento attuale, non lo si
giudica. Verificare che le soglie siano *giuste* secondo la dottrina CNDCEC/OIC è
un'altra indagine: farebbe emergere divergenze preesistenti da decidere caso per
caso, fuori da un refactoring.

## Mappa dei moduli

Regola di dipendenza unidirezionale: **`lib/pratica-*` non importa mai da `app/`
o `components/`**; i componenti importano da `lib`. Nessun ciclo possibile.

### Moduli puri (`lib/`)

| File | Sorgente | Contenuto | Consumatori |
|---|---|---|---|
| `pratica-format.ts` | 119–143, 222–249 | `formatEuro`, `formatPct`, `formatInputNumber`, `parseInputNumber`, `MONTH_LABELS`, `SECTOR_OPTIONS` | tutti |
| `pratica-codes.ts` | 144–221, 250–287, 1398–1456, 5028–5065 | `EDITABLE_CE_CODES`, `CE_OVERRIDE_FIELD_BY_CODE`, `buildCeOverridePayload`, `KEY_BS_CODES`, `VP_CODES`, `EBITDA_COST_CODES`, `ALWAYS_SHOW_CODES`, `ATTIVO_CODES`, `PASSIVO_CODES`, `DETAIL_PARENTS`, `EXTRA_ALERT_DEFS` | page, tabelle |
| `pratica-reconcile.ts` | 2842–2918 | `reconcileSubfields` | page, statement-rows, hook rettifiche |
| `pratica-indicators.ts` | 288–519 e 533–579 (i due `ChartConfig` a 520–532 restano fuori) | `safeDivide`, `IndicatorSet`, `linearScore`, `invertedScore`, `computeIndicators`, `scoreIndicator`, `INDICATOR_DEFS`, `scoreDotColor`, `computeCrisisRating` | `IndicatoriTable`, `StampaContent` |
| `pratica-statement-rows.ts` | 580–1012 | `buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda` | page, `StampaContent` |
| `pratica-rettifiche-rules.ts` | 1013–1397, 1457–1521 | `PROPOSAL_RULES`, `EDITABLE_RETTIFICHE`, `AUTO_ADJUSTED`, `NON_POSTABLE_FIELDS`, `RETTIFICHE_LABELS`, `AcctCategory`, `fieldCategory`, `allowedCounterpartCategories`, `computeCpDelta`, `COUNTERPART_*`, `RETTIFICHE_BS_*`, `DEBT_GROUPS`, `PASSIVO_TOTAL_FIELDS`, `CE_A`…`CE_IMPOSTE`, `ProposalMode`, `DoubleEntryProposal`, `RETTIFICHE_MAX` | `RettificheTab` |

`pratica-statement-rows` dipende da `pratica-codes` e `pratica-reconcile`;
`pratica-indicators` non dipende da nulla; gli altri sono foglie.

### Componenti (`components/pratica/`)

| File | Sorgente | Righe |
|---|---|---|
| `RettificheTab.tsx` | 1522–2841 | ~1.320 |
| `ComparisonTable.tsx` | 4581–4800 | ~220 |
| `ProjectionTable.tsx` | 4801–5027 | ~227 |
| `ExtraAccountingAlerts.tsx` | 5066–5116 | ~50 |
| `IndicatoriTable.tsx` | 5117–5346 + i due `ChartConfig` (520–532) | ~240 |
| `StampaContent.tsx` | 5347–6019 | ~673 |

I due `ChartConfig` (`economicIncidenceChartConfig`, `financialMarginsChartConfig`)
sono usati **solo** da `IndicatoriTable` e sono configurazione di presentazione:
seguono il componente, non vanno in `lib`.

`EXTRA_ALERT_DEFS` invece è usato sia da `ExtraAccountingAlerts` sia da
`StampaContent` (riga 5997): è una tabella di dati senza JSX e va in
`pratica-codes.ts`.

### Correzione a `CLAUDE.md` emersa in fase di design

`CLAUDE.md` afferma che `RettificheTab` «leans on ~15 module-level constants
shared with the Confronto and Proiezione tabs», e ne deduce che estrarlo
richieda prima un modulo condiviso. Verificato identificatore per
identificatore: **una sola** costante è davvero condivisa (`DETAIL_PARENTS`, usata
a 4693 e 4917), e non è nemmeno usata dentro `RettificheTab`. Le altre quattordici
sono confinate al proprio blocco. La nota in `CLAUDE.md` va corretta.

## Il gate al render

Una guardia sola, prima degli otto rami `{activeTab === "x" && …}` in
`InfraannualePage`:

```tsx
const blocked = useMemo(() => {
  if (!pratica) return null;
  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const step = steps.find((s) => s.id === activeTab);
  if (!step || step.enabled) return null;
  return {
    reason: gateReason(step, gates, pratica),
    back: firstEnabledStep(steps, step.phase) ?? firstEnabledStep(steps, "dati"),
  };
}, [pratica, activeTab]);
```

Quando `blocked` è valorizzato, al posto del contenuto della tab va una card con
il motivo e un bottone che riporta allo step raggiungibile. Nessun ramo `activeTab
=== …` va modificato: la guardia li avvolge.

### Due decisioni controintuitive, da non "correggere" in seguito

**Step sconosciuto → non blocca.** `buildPraticaSteps` omette deliberatamente
degli step in certi workflow (startup, legacy budget resume). Bloccare
sull'assenza creerebbe vicoli ciechi nuovi. Una difesa in profondità non deve
inventare stati senza uscita.

**Il gate legge la stessa cache dello stepper, senza round-trip al server.**
`praticaGates` deriva dallo stato persistito in `localStorage`. Renderlo più
severo dello stepper produrrebbe falsi blocchi: gli hook `useRettificheYear`
partono a `confirmed: false` e caricano **solo** sulla tab Rettifiche, quindi su
qualunque altra tab la verità server non è disponibile.

Conseguenza da dichiarare apertamente: se la cache dice "confermato" e il server
dice il contrario, il gate lascia passare — **esattamente come oggi**. Questo non
è un confine di autorizzazione e non va presentato come tale. Entrambe le review
del 2026-08-08 non sono riuscite a costruire un exploit raggiungibile, e questo
lavoro non ne scopre uno. Il valore è che l'invariante diventa strutturale invece
di dipendere dal fatto che ogni sito di navigazione se la ricordi.

### Perché l'invariante attuale è fragile

L'effetto in `page.tsx` che scrive `rettificheConfirmed` nel context gira senza
condizioni su `[verifica.confirmed, storico.confirmed, storico.exists]`. Dopo un
F5 sulla tab Stampa gli hook non caricano mai, quindi quei valori restano
`false/false/true` — gli stessi valori iniziali. L'effetto perciò **non riscatta**
e la cache persistita sopravvive.

L'invariante regge, ma regge perché i valori pre-caricamento coincidono con
quelli iniziali: una coincidenza, non una costruzione. È l'argomento principale
per rendere il gate strutturale.

## Verifica

Tre livelli, ciascuno con un mestiere distinto:

| Livello | Copre | Non copre |
|---|---|---|
| Diff verbatim vs `git show HEAD:…` | che i corpi spostati siano byte-identici | il resto |
| Test di caratterizzazione (Vitest) | che i calcoli non cambino da qui in avanti | il primo spostamento |
| `tsc` + `npm run build` + giro browser | import, compilazione, flussi reali | i valori numerici |

**I test di caratterizzazione non possono coprire retroattivamente il primo
spostamento**, perché prima di quello le funzioni non sono importabili: non
esiste un "prima" da cui catturare uno snapshot. Quel passaggio è coperto dal
diff verbatim, che per un *move* è più forte di uno snapshot — se un array ha
perso un elemento, il diff lo mostra; uno snapshot preso dopo il fatto no.

Copertura dei test di caratterizzazione: `computeIndicators`, `scoreIndicator`,
`computeCrisisRating`, `linearScore`/`invertedScore`, `reconcileSubfields`,
`buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda`. Input realistici
(un bilancio abbreviato con soli aggregati, uno con dettaglio completo, uno con
EBITDA negativo per i casi limite documentati in `MEMORY.md`).

## Ordine di lavoro

1. **Gate al render.** Piccolo, indipendente, spedibile da solo.
2. **Estrazione dei sei moduli puri** + verifica del diff verbatim.
3. **Test di caratterizzazione** sui moduli estratti.
4. **Estrazione dei sei componenti**, uno per commit.
5. **`CLAUDE.md`**: modello dei moduli, correzione della nota sulle ~15 costanti,
   stato aggiornato del residuo sul gate.
6. *(Opzionale)* **Rimozione dell'iniezione di `reconcileSubfields`** in
   `useRettificheYear`. Il parametro esiste solo per evitare l'import da un
   modulo di rotta (lo dice il commento); con la funzione in
   `lib/pratica-reconcile.ts` il vincolo sparisce. Tocca la firma dell'hook e due
   call site: tagliabile senza conseguenze.

Il gate va per primo di proposito: se il lavoro si fermasse a metà, la parte con
valore proprio è già a terra.

## Rischi

**Un identificatore usato da più blocchi finisce nel modulo sbagliato** e crea un
ciclo di import. Mitigazione: la mappa sopra è stata costruita cercando ogni
identificatore condiviso (`scoreDotColor`, `computeCrisisRating`,
`INDICATOR_DEFS`, `computeIndicators`, `buildBalanceItemsWithTotals`,
`buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda`, `EXTRA_ALERT_DEFS`,
`DETAIL_PARENTS` sono gli otto con più di un consumatore).
`tsc` rileva i cicli veri.

**Il gate blocca una pratica legittima.** Mitigazione: legge la stessa cache
dello stepper, quindi non può bloccare uno step che lo stepper mostra come
raggiungibile. Verifica nel browser sui due casi che contano — F5 sulla tab
Stampa di una pratica confermata, e apertura di una pratica a rettifiche non
confermate.

**Le righe spostate non sono verbatim.** Mitigazione: il diff automatico del
passo 2 è esattamente il controllo di questo.
