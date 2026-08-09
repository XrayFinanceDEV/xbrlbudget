# Stepper della pratica a fasi + barra azioni — design

**Data:** 2026-08-09
**Stato:** approvato in brainstorming, da pianificare
**Contesto:** segue `2026-08-08-percorso-unico-pratica-design.md`, che ha introdotto lo stepper

## Il problema

Lo stepper attuale (`components/PraticaStepper.tsx`) mostra **15 voci in fila** su un'unica
barra orizzontale:

```
Analisi: Anagrafiche · Import · Rettifiche · Confronto · Proiezione · Indicatori · Stampa
Previsionale: Budget · CE Prev. · SP Prev. · Riclassificato · Rendiconto · Report
Esci dalla pratica
```

Due difetti distinti:

1. **Tutto sullo stesso piano.** Sette di quelle voci non sono step da percorrere ma
   **output di sola lettura** consultabili in qualsiasi ordine (Indicatori, Stampa, CE/SP
   previsionale, Riclassificato, Rendiconto, Report). Mescolarle con le azioni fa sembrare
   il percorso lungo il doppio di quanto sia.
2. **Lo stepper dice dove sei, non cosa fare.** L'avanzamento è affidato a bottoni dentro il
   contenuto di ogni tab, con nomi e posizioni diverse: `Conferma e prosegui`
   (`app/pratica/page.tsx:4156`), `Vai alla Proiezione` (`:4280`), `Prosegui al Budget`
   (`:5598`), `Salva e Calcola Previsionale` su `/budget`. L'utente deve cercarli.

Effetto collaterale già noto: la pagina `/analysis` (Indici) è linkata dalla nav piatta ma
non appartiene ad alcuno step, quindi **dentro una pratica è irraggiungibile** — stessa
classe del problema che nel refactor precedente fece aggiungere SP Prev. e Riclassificato.

## Obiettivi

- Ridurre a **massimo 7, tipicamente 3-4** le voci di navigazione visibili contemporaneamente.
- Separare visivamente ciò che si **fa** da ciò che si **guarda**.
- Un unico posto, sempre lo stesso, che dice qual è l'azione successiva e — se è bloccata —
  perché.
- Rendere `/analysis` raggiungibile dentro la pratica.

## Non obiettivi

- Scomporre il monolite `app/pratica/page.tsx` (5.940 righe). Resta il follow-up già tracciato
  in CLAUDE.md e in `.superpowers/sdd/2026-08-08-percorso-unico-pratica/progress.md`.
- Cambiare la semantica dei gate o qualunque logica di backend.
- Cambiare il contenuto di un qualsiasi step. Solo la navigazione fra step e il modo in cui
  si conferma l'avanzamento.

## Il modello: tre fasi, azioni e viste

Le fasi passano da 2 a 3. Dentro ogni fase, gli step sono divisi in due gruppi da un
separatore sottile: a sinistra le **azioni** (che sbloccano il seguito), a destra le **viste**
(libere, in qualsiasi ordine, appena esiste il dato).

| Fase | Azioni | Viste |
|---|---|---|
| 1 · DATI | Anagrafiche · Import · Rettifiche | — |
| 2 · ANALISI | Confronto · Proiezione | Indicatori · Stampa |
| 3 · PREVISIONALE | Budget | Indici · CE Prev. · SP Prev. · Riclassificato · Rendiconto · Report |

Nessuno step viene rimosso e nessuna funzione cambia. `Indici` (`/analysis`) è l'unica voce
nuova e non richiede modifiche alla sua pagina.

### Composizione per workflow

- **bilancio** — tutte e tre le fasi. Lo step `Proiezione` continua a comparire solo con
  `periodMonths !== 12`.
- **startup** — fase 1 con il solo `Anagrafiche` (che è il form business plan su `/budget`),
  nessuna fase ANALISI, fase 3 completa. Lo stepper mostra 2 chip.
- **legacy budget resume** (`budgetScenarioId !== null && infrannualeScenarioId === null`) —
  solo la fase PREVISIONALE, 1 chip. Invariato rispetto a oggi.

Le fasi senza step non vengono disegnate: nessun caso speciale nel componente, cade fuori dal
filtro che già esiste.

## Lo stepper a due livelli

```
╭──────────────────────────────────────────────────────────────────────╮
│  ACME COSTRUZIONI SRL · Bil. verifica 9M 2025            Esci ⏻      │
│                                                                      │
│   ✓━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━○                                  │
│   1 DATI          2 ANALISI       3 PREVISIONALE                     │
├──────────────────────────────────────────────────────────────────────┤
│   Confronto │ Proiezione  ┊  Indicatori │ Stampa                     │
│   ─────────                                                          │
╰──────────────────────────────────────────────────────────────────────╯
```

- **Chip di fase**, quattro stati, valutati in quest'ordine:

  | Stato | Quando | Resa | Cliccabile |
  |---|---|---|---|
  | `active` | contiene lo step corrente | `●` pieno, testo in evidenza | sì |
  | `done` | precede la fase attiva | `✓` | sì |
  | `locked` | nessuno dei suoi step è abilitato | `○` grigio | no, tooltip col motivo |
  | `todo` | segue la fase attiva e ha almeno uno step abilitato | `○` | sì |

  Cliccare un chip cliccabile porta al **primo step abilitato** di quella fase. Il tooltip di
  un chip `locked` riporta il `gateReason` del suo primo step.
- **Sotto-barra:** solo gli step della fase attiva. Uno step disabilitato resta **visibile in
  grigio** — il percorso deve restare prevedibile, non apparire e sparire.
- La riga in alto porta identità della pratica (ragione sociale, tipo e periodo del bilancio)
  e `Esci dalla pratica`, come oggi.

## La barra azioni

Fissa in fondo alla pagina, identica in ogni step, presente anche sulle pagine-rotta
(`/budget`, `/analysis`, `/forecast/*`, `/cashflow`, `/report`):

```
╭──────────────────────────────────────────────────────────────────────╮
│  ‹ Import          2 schede da confermare                            │
│                              [ Conferma e vai al Confronto  › ]      │
╰──────────────────────────────────────────────────────────────────────╯
```

Un solo bottone primario per step, che **salva e avanza insieme**. Quando il gate non è
soddisfatto il bottone è disabilitato e il motivo è scritto accanto — non in un toast che
sparisce.

| Step | Azione primaria | Motivo tipico se bloccata |
|---|---|---|
| Anagrafiche | Salva e prosegui | Manca la ragione sociale |
| Import | Vai alle Rettifiche | Nessun bilancio importato |
| Rettifiche | Conferma e vai al Confronto | *n* schede da confermare |
| Confronto | Vai alla Proiezione *(12M: Vai agli Indicatori)* | — |
| Proiezione | Calcola e vai agli Indicatori | — |
| Indicatori | Vai alla Stampa | Proiezione non calcolata |
| Stampa | Prosegui al Budget | — |
| Budget | Salva e calcola il previsionale | — |
| Indici · CE · SP · Riclassificato · Rendiconto | Avanti: *(nome step successivo)* | Previsionale non generato |
| Report | Chiudi la pratica | — |

I CTA inline elencati nel *Problema* vengono rimossi e i loro handler passati alla barra:
nessuna logica di salvataggio viene riscritta.

**Beneficio non estetico.** Oggi il gate è applicato solo in navigazione: `PraticaStepper`
disabilita il bottone, ma le render guard del wizard (`{activeTab === "projection" && …}`) e
il percorso di reidratazione non lo ricontrollano — è il residuo di difesa in profondità
tracciato nel refactor precedente. Con una sola barra azioni che deriva "step successivo +
gate" da `lib/pratica-steps.ts`, esiste **un unico punto** che decide l'avanzamento, e il
buco si chiude come effetto collaterale invece che come lavoro a parte.

## Architettura

Il principio: **la logica del percorso resta in un file puro; i componenti la disegnano.**

### a) `lib/pratica-steps.ts` — esteso, resta puro

```ts
type PraticaPhase = "dati" | "analisi" | "previsionale"   // era 2, ora 3

interface PraticaStep {
  …campi esistenti,
  group: "azione" | "vista"        // posiziona il separatore ┊
}

// funzioni pure, tutte derivate dall'array di buildPraticaSteps()
nextStep(steps, currentId): PraticaStep | null
prevStep(steps, currentId): PraticaStep | null
phaseStatus(steps, phase, currentId): "done" | "active" | "todo" | "locked"
gateReason(step, gates, pratica): string | null
```

`gateReason` è l'unica fonte dei messaggi "perché è bloccato", consumata sia dal tooltip dei
chip sia dalla barra azioni.

### b) `components/PraticaStepper.tsx` — riscritto a due livelli

Stessa posizione (lo monta `Navigation.tsx:52`) e stesso contratto verso l'esterno. Legge
`phaseStatus` per i chip e filtra la sotto-barra sulla fase attiva.

### c) `contexts/PraticaActionContext.tsx` — nuovo

Le pagine-rotta sono file separati e la loro azione primaria ha bisogno del loro stato locale.
La registrano con un hook:

```ts
usePrimaryAction({
  label: "Salva e calcola il previsionale",
  onClick: handleSave,
  disabled: !canSave,
  reason: null,
})
```

`onClick` è tenuto in un **ref** aggiornato a ogni render, e l'effetto di registrazione dipende
solo dai primitivi (`label`, `disabled`, `reason`). Senza questa accortezza l'oggetto nuovo a
ogni render rifà partire l'effetto in ciclo — è lo stesso inciampo già documentato per
`hooks/use-rettifiche-year.ts` ("mai l'oggetto intero in un dependency array").

Il provider sta sotto `PraticaProvider` in `app/layout.tsx`.

### d) `components/pratica/PraticaActionBar.tsx` — nuovo

Montata in `app/layout.tsx` subito dopo `<main>`, dentro un wrapper `print:hidden`; ritorna
`null` fuori da una pratica. Se nessuno ha registrato un'azione, il **fallback** è pura
navigazione: `Avanti: <label di nextStep()>`, abilitata se `nextStep().enabled`, altrimenti
disabilitata con `gateReason()` accanto. Così le viste di sola lettura non richiedono alcuna
modifica alle loro pagine.

### File toccati

| File | Natura |
|---|---|
| `lib/pratica-steps.ts` | esteso |
| `lib/pratica-steps.test.ts` | nuovo |
| `components/PraticaStepper.tsx` | riscritto |
| `contexts/PraticaActionContext.tsx` | nuovo |
| `components/pratica/PraticaActionBar.tsx` | nuovo |
| `app/layout.tsx` | monta provider + barra |
| `app/pratica/page.tsx` | 7 CTA inline → `usePrimaryAction` |
| `app/budget/page.tsx` | 1 CTA inline → `usePrimaryAction` |
| `vitest.config.ts`, `package.json` | nuovi / script `test` |

Le 6 pagine di sola vista non vengono toccate.

## Casi limite

- **Bilancio annuale (12M):** lo step `Proiezione` non esiste; `nextStep` da `Confronto` deve
  restituire `Indicatori`, e l'azione primaria del Confronto diventa "Vai agli Indicatori"
  (con lo stesso `saveProjection12M()` che fa oggi).
- **Import senza anno di raffronto:** `rettificheConfirmed.storico` è già scritto `true` dal
  wizard; nessun cambiamento, il conteggio "*n* schede da confermare" deve dire 1, non 2.
- **Reidratazione dopo F5:** l'`analysisStep` persistito può puntare a uno step ora disabilitato
  (es. dopo un "Ripristina originale"). La barra azioni non deve proporre un avanzamento da uno
  step irraggiungibile: se lo step corrente non è abilitato, mostra come azione primaria il
  ritorno al primo step abilitato della sua fase.
- **Stampa e Report** sono pagine da stampare: barra azioni e stepper restano `print:hidden`.
- **Fuori dalla pratica** (`pratica === null` o path `/`): né stepper né barra, la nav piatta
  resta esattamente com'è oggi.

## Verifica

- **Vitest su `lib/pratica-steps.ts`** — primo test frontend del progetto, isolato, senza React
  né rete. Copre: composizione delle 3 fasi nel percorso bilancio; startup senza fase ANALISI;
  legacy resume con la sola PREVISIONALE; assenza di `Proiezione` a 12M; `nextStep`/`prevStep`
  che saltano correttamente quello step; `nextStep` che ritorna `null` sull'ultimo;
  `gateReason` che dà un motivo a gate non soddisfatto e `null` quando è soddisfatto.
- **Verifica manuale nel browser** dei quattro percorsi (bilancio 9M, bilancio 12M, startup,
  pratica legacy), perché lo stepper e la barra sono componenti visivi e il modello dei gate va
  visto muoversi.

## Rischi

- **Il rischio principale è la migrazione dei CTA inline.** Ognuno degli 8 bottoni ha
  condizioni di `disabled` proprie (es. `Conferma e prosegui` ne ha sei) che vanno trasferite
  intatte nella registrazione, non riscritte a memoria.
- La barra fissa in fondo consuma altezza su schermi bassi: va tenuta compatta (una riga) e
  non deve coprire l'ultima riga delle tabelle lunghe (padding di compensazione sul `<main>`).
