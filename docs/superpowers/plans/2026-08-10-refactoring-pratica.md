# Refactoring di `app/pratica/page.tsx` + gate al render — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare `frontend/app/pratica/page.tsx` da 6.019 a ~1.850 righe spostando (non riscrivendo) sei moduli puri in `lib/` e sei componenti in `components/pratica/`, e rendere strutturale il gate di percorso applicandolo al render invece che ai soli siti di navigazione.

**Architecture:** Estrazione meccanica. I moduli puri vanno in file piatti `lib/pratica-*.ts` accanto al `lib/pratica-steps.ts` esistente; i componenti in `components/pratica/`. Dipendenza unidirezionale: `lib/pratica-*` non importa mai da `app/` o `components/`. Il gate diventa una funzione pura `blockedStep()` in `lib/pratica-steps.ts`, testata con Vitest e consumata da una guardia unica che avvolge i sette rami `activeTab` del wizard.

**Tech Stack:** Next.js 15 (app router), React 19, TypeScript 5, Vitest 3, shadcn/ui, Tailwind v3, lucide-react, sonner.

Spec: `docs/superpowers/specs/2026-08-10-refactoring-pratica-design.md`

## Global Constraints

- **Il server dev gira già.** Backend su :8000 e frontend su :3000 sono avviati dall'utente. **Non avviarli, non fermarli, non riavviarli, non toccare quelle porte.**
- **Commit diretti su `main`.** Nessun feature branch: Jenkins builda da main al push. Non pushare — al push pensa il controller a fine lavoro.
- **Terminare ogni messaggio di commit con:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Line endings:** il repo ha file con terminatori misti. Prima di ogni commit eseguire `git diff --stat` e verificare che il numero di righe modificate sia plausibile; un file che risulta interamente riscritto significa che un tool ha normalizzato CRLF→LF, e va ripristinato invece che committato.
- **Solo componenti shadcn/ui.** Niente `<button>`, `<table>`, `<input>` grezzi: usare `Button`, `Table`, `Input` da `@/components/ui/*`.
- **Niente emoji.** Icone da `lucide-react`.
- **Testo UI in italiano.**
- **Colori semantici** (`text-foreground`, `bg-card`, `border-border`), mai esadecimali.
- **Commit base per i diff verbatim: `a981ac8`.** È il commit della spec, l'ultimo prima che questo lavoro tocchi `page.tsx`. Tutti gli intervalli di riga citati nei task si riferiscono a `git show a981ac8:frontend/app/pratica/page.tsx`, e restano validi anche dopo che i task precedenti hanno spostato righe.
- **Comandi eseguiti da `frontend/`**, salvo indicazione diversa.

### Procedura di diff verbatim (usata dai task 2, 4, 6, 7, 8)

Ogni estrazione è un *move*: il codice spostato deve restare identico all'originale, a meno della keyword `export` aggiunta in testa alle dichiarazioni. Il controllo è questo, da eseguire da `frontend/`:

```bash
# 1. estrai il blocco originale dal commit base (sostituire gli intervalli)
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '119,142p;222,248p' > /tmp/orig.txt

# 2. estrai il corpo del nuovo modulo, saltando le righe di import iniziali.
#    L'ancora e' la PRIMA RIGA del blocco spostato, nota e citata in ogni task:
#    cosi' il comando e' deterministico e non dipende dal contare le righe.
sed -n '/^export const MONTH_LABELS/,$p' lib/pratica-format.ts | sed 's/^export //' > /tmp/new.txt

# 3. devono essere identici
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```

Se `diff` produce output, il blocco **non** è stato spostato verbatim: correggere il nuovo file finché il diff è vuoto. Non "sistemare" l'originale per far tornare il diff.

### Verifica di fine task (tutti i task)

```bash
npx tsc --noEmit          # atteso: 0 errori
npm test                  # atteso: tutti i test verdi
npm run build             # atteso: build completata
```

`npm run lint` produce warning preesistenti (dipendenze di `useMemo`/`useCallback` in `app/pratica/page.tsx`): non sono regressioni e non vanno "corretti" in questo lavoro. Un **errore** di lint invece sì.

---

## Struttura dei file

**Creati:**

| File | Responsabilità |
|---|---|
| `frontend/lib/pratica-format.ts` | formattazione numeri/valuta italiana ed etichette mese/settore |
| `frontend/lib/pratica-codes.ts` | tabelle di codici IV-CEE e mappe campo→aggregato |
| `frontend/lib/pratica-reconcile.ts` | riconciliazione sotto-voci ↔ aggregati |
| `frontend/lib/pratica-indicators.ts` | calcolo indicatori, scoring, rating di crisi |
| `frontend/lib/pratica-statement-rows.ts` | costruzione righe SP/CE con totali e subtotali |
| `frontend/lib/pratica-rettifiche-rules.ts` | regole di partita doppia e layout delle rettifiche |
| `frontend/lib/pratica-reconcile.test.ts` | caratterizzazione di `reconcileSubfields` |
| `frontend/lib/pratica-indicators.test.ts` | caratterizzazione di indicatori e scoring |
| `frontend/lib/pratica-statement-rows.test.ts` | caratterizzazione dei builder di righe |
| `frontend/components/pratica/RettificheTab.tsx` | tab Rettifiche |
| `frontend/components/pratica/ComparisonTable.tsx` | tabella Confronto |
| `frontend/components/pratica/ProjectionTable.tsx` | tabella Proiezione editabile |
| `frontend/components/pratica/ExtraAccountingAlerts.tsx` | segnali extracontabili |
| `frontend/components/pratica/IndicatoriTable.tsx` | tabella indicatori + grafici |
| `frontend/components/pratica/StampaContent.tsx` | vista di stampa |

**Modificati:**

| File | Modifica |
|---|---|
| `frontend/lib/pratica-steps.ts` | aggiunta di `blockedStep()` |
| `frontend/lib/pratica-steps.test.ts` | test di `blockedStep()` |
| `frontend/app/pratica/page.tsx` | guardia al render; rimozione dei blocchi spostati; import dai nuovi moduli |
| `frontend/hooks/use-rettifiche-year.ts` | (task 9, opzionale) rimozione del parametro `reconcile` |
| `CLAUDE.md` | mappa dei moduli, correzione della nota sulle costanti condivise, stato del gate |

---

### Task 1: Gate al render

Il gate di percorso vive in `lib/pratica-steps.ts` ma è consultato solo da chi naviga (stepper e barra azioni). I rami `{activeTab === "x" && …}` del wizard si rendono senza controllarlo. Questo task aggiunge la funzione pura che decide, la testa, e la applica al render.

**Files:**
- Modify: `frontend/lib/pratica-steps.ts` (in coda, dopo `gateReason`)
- Modify: `frontend/lib/pratica-steps.test.ts` (in coda)
- Modify: `frontend/app/pratica/page.tsx` (dentro `InfraannualePage`: import in testa; `useMemo` prima del `return`; guardia nel JSX)

**Interfaces:**
- Consumes: da `./pratica-steps` — `praticaGates(pratica: PraticaState): PraticaGates`, `buildPraticaSteps(pratica: PraticaState, gates: PraticaGates): PraticaStep[]`, `gateReason(step: PraticaStep, gates: PraticaGates, pratica: PraticaState): string | null`, `type PraticaStep`, `type PraticaState`.
- Produces: `export interface StepBlock { reason: string | null; back: PraticaStep | null }` e `export function blockedStep(pratica: PraticaState | null, stepId: string): StepBlock | null`.

- [ ] **Step 1: Scrivere i test che falliscono**

In coda a `frontend/lib/pratica-steps.test.ts`. Le fixture `PRATICA`, `NO_GATES`, `ALL_GATES` esistono già in cima al file; aggiungere `blockedStep` alla lista di import da `./pratica-steps`.

```ts
describe("blockedStep", () => {
  it("nessuna pratica attiva: non blocca", () => {
    expect(blockedStep(null, "stampa")).toBeNull();
  });

  it("step raggiungibile: non blocca", () => {
    expect(blockedStep(PRATICA, "anagrafiche")).toBeNull();
  });

  it("step sconosciuto: non blocca (i workflow ne omettono di proposito)", () => {
    expect(blockedStep(PRATICA, "questo-step-non-esiste")).toBeNull();
  });

  it("Import senza azienda: blocca e riporta ad Anagrafiche", () => {
    // fiscalYear azzerato insieme a companyId: senza azienda non può esistere
    // un anno fiscale importato — altrimenti gates.imported (che guarda solo
    // fiscalYear) lascerebbe "rettifiche" abilitata da uno stato irrealizzabile.
    const p: PraticaState = { ...PRATICA, companyId: null, fiscalYear: null };
    const block = blockedStep(p, "import");
    expect(block?.reason).toBe("Completa prima l'anagrafica");
    expect(block?.back?.id).toBe("anagrafiche");
  });

  it("Stampa con rettifiche non confermate: blocca e riporta a Rettifiche", () => {
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: 7,
      rettificheConfirmed: { storico: false, verifica: false },
    };
    const block = blockedStep(p, "stampa");
    expect(block?.reason).toBe("Rettifiche non confermate");
    expect(block?.back?.id).toBe("rettifiche");
  });

  it("Proiezione senza confronto: riporta al Confronto, l'ultima tab raggiungibile", () => {
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: null,
      rettificheConfirmed: { storico: true, verifica: true },
    };
    const block = blockedStep(p, "projection");
    expect(block?.reason).toBe("Confronto non caricato");
    expect(block?.back?.id).toBe("comparison");
  });

  it("il ritorno resta dentro il wizard, mai su una rotta previsionale", () => {
    // infrannualeScenarioId DEVE essere valorizzato: `budgetScenarioId !== null`
    // insieme a `infrannualeScenarioId === null` è esattamente il trigger di
    // isLegacyBudgetResume in buildPraticaSteps, che fa sparire "projection"
    // dalla lista — lo step diventerebbe sconosciuto e blockedStep tornerebbe
    // null per il motivo 1 del suo JSDoc, vanificando il test. Le rettifiche
    // restano non confermate (default della fixture) così "projection" è
    // comunque bloccata, mentre budgetScenarioId abilita gli step-rotta del
    // previsionale che il "back" deve scartare in favore di una tab.
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: 7,
      budgetScenarioId: 3,
    };
    const block = blockedStep(p, "projection");
    expect(block?.back?.kind).toBe("tab");
  });
});
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `npm test`
Expected: FAIL — `blockedStep is not exported` / `is not a function`.

- [ ] **Step 3: Implementare `blockedStep`**

In coda a `frontend/lib/pratica-steps.ts`:

```ts
export interface StepBlock {
  /** Perché lo step non è raggiungibile. */
  reason: string | null;
  /** Dove riportare l'utente. Sempre una tab del wizard, mai una rotta. */
  back: PraticaStep | null;
}

/**
 * Lo step è raggiungibile? `null` = sì (o non c'è nulla da decidere).
 *
 * Difesa in profondità per il RENDER: i rami `{activeTab === …}` del wizard non
 * consultano i gate, quindi finora l'invariante dipendeva dal fatto che ogni
 * sito di navigazione se la ricordasse.
 *
 * Due comportamenti deliberati, da non "correggere":
 *
 * 1. Uno step SCONOSCIUTO non blocca. `buildPraticaSteps` omette di proposito
 *    degli step in certi workflow (startup, legacy budget resume): bloccare
 *    sull'assenza creerebbe vicoli ciechi nuovi.
 * 2. Si legge lo stesso stato persistito che legge lo stepper, senza
 *    interrogare il server. Essere più severi dello stepper produrrebbe falsi
 *    blocchi: gli hook `useRettificheYear` partono a `confirmed: false` e
 *    caricano SOLO sulla tab Rettifiche, quindi altrove la verità server non è
 *    disponibile. Conseguenza dichiarata: se la cache dice "confermato" e il
 *    server dice il contrario, qui si passa — esattamente come prima di questo
 *    controllo. Non è un confine di autorizzazione.
 */
export function blockedStep(
  pratica: PraticaState | null,
  stepId: string,
): StepBlock | null {
  if (!pratica) return null;
  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const step = steps.find((s) => s.id === stepId);
  if (!step || step.enabled) return null;
  // L'ultima tab raggiungibile in ordine di percorso: è il punto più avanzato
  // dove l'utente è legittimamente arrivato. Filtrata su `kind === "tab"` per
  // non spedirlo fuori dal wizard su una rotta previsionale.
  const back =
    [...steps].reverse().find((s) => s.enabled && s.kind === "tab") ?? null;
  return { reason: gateReason(step, gates, pratica), back };
}
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `npm test`
Expected: PASS — tutti i test, inclusi i 7 nuovi.

- [ ] **Step 5: Applicare la guardia al render**

In `frontend/app/pratica/page.tsx`, aggiungere all'import da `@/lib/pratica-steps` (se il file non importa ancora da lì, creare l'import):

```ts
import { blockedStep } from "@/lib/pratica-steps";
```

Subito prima di `usePrimaryAction(primary);` aggiungere:

```tsx
  // Difesa in profondità: i rami `activeTab === …` qui sotto non consultano i
  // gate del percorso. Vedi blockedStep() in lib/pratica-steps.ts per cosa
  // questo controllo copre e cosa deliberatamente non copre.
  const blocked = useMemo(() => blockedStep(pratica, activeTab), [pratica, activeTab]);
```

Nel JSX, subito **dopo** il blocco `{rehydrationFailed && (…)}` e **prima** di `{/* STEP 0: ANAGRAFICHE */}`, aggiungere la guardia. I sette rami `activeTab === …` esistenti vanno lasciati esattamente come sono: li si avvolge in un `{!blocked && (<>…</>)}`.

```tsx
        {blocked && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="h-5 w-5" /> Passaggio non ancora raggiungibile
              </CardTitle>
              <CardDescription>
                {blocked.reason ?? "Completa prima i passaggi precedenti."}
              </CardDescription>
            </CardHeader>
            {blocked.back && (
              <CardContent>
                <Button
                  onClick={() => {
                    if (blocked.back) setActiveTab(blocked.back.id);
                  }}
                >
                  Torna a {blocked.back.label}
                </Button>
              </CardContent>
            )}
          </Card>
        )}
```

Poi aprire `{!blocked && (<>` subito prima del commento `{/* STEP 0: ANAGRAFICHE */}` e chiudere `</>)}` subito dopo la fine dell'ultimo ramo (`{activeTab === "stampa" && …}`). `AlertTriangle` è già importato da `lucide-react`; `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent` e `Button` sono già importati.

- [ ] **Step 6: Verificare compilazione e build**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori, test verdi, build completata.

- [ ] **Step 7: Commit**

```bash
cd /home/peter/DEV/budget
git add frontend/lib/pratica-steps.ts frontend/lib/pratica-steps.test.ts frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
feat(pratica): il gate di percorso e' applicato anche al render

I rami {activeTab === …} del wizard non consultavano i gate: l'invariante
dipendeva dal fatto che ogni sito di navigazione se la ricordasse. Ora una
guardia unica, basata sulla funzione pura blockedStep(), rende una card con
il motivo e il ritorno all'ultima tab raggiungibile.

Due comportamenti deliberati, documentati nella funzione: uno step
sconosciuto non blocca (i workflow ne omettono di proposito), e il controllo
legge la stessa cache dello stepper senza interrogare il server — non e' un
confine di autorizzazione, e non chiude un exploit noto.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Moduli foglia — format, codes, reconcile

Tre moduli senza dipendenze fra loro né verso altro codice del progetto.

**Files:**
- Create: `frontend/lib/pratica-format.ts`
- Create: `frontend/lib/pratica-codes.ts`
- Create: `frontend/lib/pratica-reconcile.ts`
- Modify: `frontend/app/pratica/page.tsx` (rimozione dei blocchi, aggiunta degli import)

**Interfaces:**
- Consumes: niente (sono foglie).
- Produces:
  - da `pratica-format`: `MONTH_LABELS: Record<number, string>`, `SECTOR_OPTIONS: Record<number, string>`, `formatEuro(value: number): string`, `formatPct(value: number): string`, `formatInputNumber(value: string): string`, `parseInputNumber(formatted: string): string`
  - da `pratica-codes`: `EDITABLE_CE_CODES`, `CE_OVERRIDE_FIELD_BY_CODE: Record<string, string>`, `buildCeOverridePayload(values: Record<string, string>): Record<string, number | null>`, `KEY_BS_CODES`, `VP_CODES`, `EBITDA_COST_CODES`, `ALWAYS_SHOW_CODES: Set<string>`, `ATTIVO_CODES`, `PASSIVO_CODES`, `DETAIL_PARENTS: Record<string, string>`, `EXTRA_ALERT_DEFS: Array<{ key: string; label: string }>`
  - da `pratica-reconcile`: `reconcileSubfields(data: Record<string, number>): void`

- [ ] **Step 1: Creare `lib/pratica-format.ts`**

Il file non ha bisogno di import. Copiare **verbatim** da `git show a981ac8:frontend/app/pratica/page.tsx` gli intervalli `119,142` e `222,248`, in quest'ordine, e aggiungere `export ` davanti a `const MONTH_LABELS`, `const SECTOR_OPTIONS`, `function formatEuro`, `function formatPct`, `function formatInputNumber`, `function parseInputNumber`.

```bash
cd /home/peter/DEV/budget/frontend
{ git show a981ac8:frontend/app/pratica/page.tsx | sed -n '119,142p;222,248p'; } > lib/pratica-format.ts
```

Poi aggiungere `export ` alle sei dichiarazioni con un editor (non con `sed` cieco: le righe interne dei letterali non vanno toccate).

- [ ] **Step 2: Verificare il diff verbatim di `pratica-format.ts`**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '119,142p;222,248p' > /tmp/orig.txt
sed 's/^export //' lib/pratica-format.ts > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`. Qui non serve alcuna ancora: il file non ha import in testa, quindi il confronto parte dalla prima riga.

- [ ] **Step 3: Creare `lib/pratica-codes.ts`**

Copiare **verbatim** gli intervalli `143,221`, `249,287`, `1397,1455`, `5027,5065`, in quest'ordine, e aggiungere `export ` a: `EDITABLE_CE_CODES`, `CE_OVERRIDE_FIELD_BY_CODE`, `buildCeOverridePayload`, `KEY_BS_CODES`, `VP_CODES`, `EBITDA_COST_CODES`, `ALWAYS_SHOW_CODES`, `ATTIVO_CODES`, `PASSIVO_CODES`, `DETAIL_PARENTS`, `EXTRA_ALERT_DEFS`.

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '143,221p;249,287p;1397,1455p;5027,5065p' > lib/pratica-codes.ts
```

`DETAIL_PARENTS` nasce nel blocco delle rettifiche ma non è usato dentro `RettificheTab`: i suoi due consumatori sono `ComparisonTable` e `ProjectionTable`. È una mappa campo→aggregato, quindi la sua casa è qui. `EXTRA_ALERT_DEFS` è usato sia da `ExtraAccountingAlerts` sia da `StampaContent`, e non contiene JSX: anche questa è una tabella di dati.

- [ ] **Step 4: Verificare il diff verbatim di `pratica-codes.ts`**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '143,221p;249,287p;1397,1455p;5027,5065p' > /tmp/orig.txt
sed 's/^export //' lib/pratica-codes.ts > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 5: Creare `lib/pratica-reconcile.ts`**

Copiare **verbatim** l'intervallo `2839,2918` (che include il commento introduttivo) e aggiungere `export ` a `function reconcileSubfields`.

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '2839,2918p' > lib/pratica-reconcile.ts
```

- [ ] **Step 6: Verificare il diff verbatim di `pratica-reconcile.ts`**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '2839,2918p' > /tmp/orig.txt
sed 's/^export //' lib/pratica-reconcile.ts > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 7: Rimuovere i blocchi da `page.tsx` e importare**

Cancellare da `frontend/app/pratica/page.tsx` gli intervalli spostati. **Attenzione: cancellare dal fondo verso l'alto**, altrimenti i numeri di riga slittano sotto le mani. Nell'ordine: `5027–5065`, `2839–2918`, `1397–1455`, `249–287`, `222–248`, `143–221`, `119–142`.

Aggiungere in testa, dopo gli altri import:

```ts
import {
  MONTH_LABELS,
  SECTOR_OPTIONS,
  formatEuro,
  formatPct,
  formatInputNumber,
  parseInputNumber,
} from "@/lib/pratica-format";
import {
  EDITABLE_CE_CODES,
  CE_OVERRIDE_FIELD_BY_CODE,
  buildCeOverridePayload,
  KEY_BS_CODES,
  VP_CODES,
  EBITDA_COST_CODES,
  ALWAYS_SHOW_CODES,
  ATTIVO_CODES,
  PASSIVO_CODES,
  DETAIL_PARENTS,
  EXTRA_ALERT_DEFS,
} from "@/lib/pratica-codes";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
```

- [ ] **Step 8: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori. Se `tsc` segnala un identificatore non usato fra quelli importati, **non** rimuoverlo dall'import senza prima verificare con `grep -n` che davvero non compaia in `page.tsx`: potrebbe essere usato da un blocco che i task successivi sposteranno.

- [ ] **Step 9: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat   # controllo line-endings: nessun file dev'essere riscritto per intero
git add frontend/lib/pratica-format.ts frontend/lib/pratica-codes.ts frontend/lib/pratica-reconcile.ts frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
refactor(pratica): estrai i moduli foglia format/codes/reconcile

Spostamento verbatim, verificato con diff contro a981ac8. DETAIL_PARENTS
passa fra i codici e non fra le regole rettifiche: nasce in quel blocco ma
i suoi unici consumatori sono ComparisonTable e ProjectionTable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Caratterizzazione di `reconcileSubfields`

Prima rete automatica. Non giudica se il comportamento è giusto: fissa quello attuale, così i task successivi non possono cambiarlo di nascosto.

**Files:**
- Create: `frontend/lib/pratica-reconcile.test.ts`

**Interfaces:**
- Consumes: `reconcileSubfields(data: Record<string, number>): void` da `./pratica-reconcile`. Muta l'oggetto in place e non restituisce nulla.
- Produces: niente.

- [ ] **Step 1: Scrivere i test**

```ts
import { describe, expect, it } from "vitest";
import { reconcileSubfields } from "./pratica-reconcile";

describe("reconcileSubfields", () => {
  it("bilancio abbreviato: il gap dell'aggregato finisce nel campo plug", () => {
    const data: Record<string, number> = {
      sp16_debiti_breve: 100_000,
      sp16a_debiti_banche_breve: 40_000,
      sp16d_debiti_fornitori_breve: 25_000,
    };
    reconcileSubfields(data);
    expect(data.sp16g_altri_debiti_breve).toBe(35_000);
  });

  it("dettaglio gia' quadrato: nessun plug", () => {
    const data: Record<string, number> = {
      sp05_rimanenze: 50_000,
      sp05a_materie_prime: 20_000,
      sp05d_prodotti_finiti: 30_000,
      sp05e_acconti: 0,
    };
    reconcileSubfields(data);
    expect(data.sp05e_acconti).toBe(0);
  });

  it("gap negativo: il plug puo' diventare negativo", () => {
    const data: Record<string, number> = {
      sp12_riserve: 10_000,
      sp12c_riserva_legale: 15_000,
    };
    reconcileSubfields(data);
    expect(data.sp12e_altre_riserve).toBe(-5_000);
  });

  it("scarto sotto il centesimo: ignorato", () => {
    const data: Record<string, number> = {
      sp06_crediti_breve: 1_000,
      sp06a_crediti_clienti_breve: 999.995,
    };
    reconcileSubfields(data);
    expect(data.sp06g_crediti_altri_breve).toBeUndefined();
  });

  it("sbilancio attivo/passivo <= 5 EUR: assorbito dalla cassa", () => {
    const data: Record<string, number> = {
      sp03_immob_materiali: 60_000,
      sp09_disponibilita_liquide: 40_003,
      sp11_capitale: 10_000,
      sp16_debiti_breve: 90_000,
      sp16g_altri_debiti_breve: 90_000,
    };
    reconcileSubfields(data);
    expect(data.sp09_disponibilita_liquide).toBe(40_000);
  });

  it("sbilancio attivo/passivo > 5 EUR: NON assorbito, resta visibile", () => {
    const data: Record<string, number> = {
      sp03_immob_materiali: 60_000,
      sp09_disponibilita_liquide: 40_050,
      sp11_capitale: 10_000,
      sp16_debiti_breve: 90_000,
      sp16g_altri_debiti_breve: 90_000,
    };
    reconcileSubfields(data);
    expect(data.sp09_disponibilita_liquide).toBe(40_050);
  });

  it("riconcilia tutti e nove gli aggregati in una sola passata", () => {
    const data: Record<string, number> = {
      sp04_immob_finanziarie: 1_000,
      sp05_rimanenze: 2_000,
      sp06_crediti_breve: 3_000,
      sp07_crediti_lungo: 4_000,
      sp12_riserve: 5_000,
      sp16_debiti_breve: 6_000,
      sp17_debiti_lungo: 7_000,
      ce08_costi_personale: 8_000,
      ce09_ammortamenti: 9_000,
    };
    reconcileSubfields(data);
    expect(data.sp04a_partecipazioni).toBe(1_000);
    expect(data.sp05e_acconti).toBe(2_000);
    expect(data.sp06g_crediti_altri_breve).toBe(3_000);
    expect(data.sp07g_crediti_altri_lungo).toBe(4_000);
    expect(data.sp12e_altre_riserve).toBe(5_000);
    expect(data.sp16g_altri_debiti_breve).toBe(6_000);
    expect(data.sp17g_altri_debiti_lungo).toBe(7_000);
    expect(data.ce08b_salari_stipendi).toBe(8_000);
    expect(data.ce09c_svalutazioni).toBe(9_000);
  });
});
```

- [ ] **Step 2: Eseguire i test**

Run: `npm test`
Expected: PASS. Se un test fallisce, **non modificare la funzione**: il compito qui è descrivere il comportamento reale. Correggere il valore atteso nel test e annotare nel report la differenza fra ciò che ci si aspettava e ciò che la funzione fa.

- [ ] **Step 3: Commit**

```bash
cd /home/peter/DEV/budget
git add frontend/lib/pratica-reconcile.test.ts
git commit -m "$(cat <<'EOF'
test(pratica): caratterizzazione di reconcileSubfields

Fissa il comportamento attuale (plug per aggregato, soglia 0,01 EUR,
assorbimento in cassa dello sbilancio <= 5 EUR) senza giudicarlo: e' la
rete che protegge le estrazioni successive.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Moduli di calcolo — indicators e statement-rows

**Files:**
- Create: `frontend/lib/pratica-indicators.ts`
- Create: `frontend/lib/pratica-statement-rows.ts`
- Modify: `frontend/app/pratica/page.tsx`

**Interfaces:**
- Consumes: **`pratica-indicators` non dipende da nulla** (l'unica occorrenza di `reconcileSubfields` nel suo intervallo è dentro un commento, riga 402). **`pratica-statement-rows`** consuma `reconcileSubfields` da `@/lib/pratica-reconcile`; `VP_CODES`, `ATTIVO_CODES`, `PASSIVO_CODES` da `@/lib/pratica-codes`; `IntraYearComparisonItem` da `@/types/api`. Non usa `ALWAYS_SHOW_CODES` né `EBITDA_COST_CODES`: `buildIncomeItemsWithEbitda` dichiara al proprio interno un `COST_CODES_ALL` locale.
- Produces:
  - da `pratica-indicators`: `safeDivide(a: number, b: number): number`, `IndicatorSet` (interfaccia, 19 campi), `linearScore(value: number, low: number, high: number): number`, `invertedScore(value: number, goodBelow: number, badAbove: number): number`, `computeIndicators(bs: Record<string, number>, is_: Record<string, number>): IndicatorSet`, `scoreIndicator(key: keyof IndicatorSet, ind: IndicatorSet): number`, `INDICATOR_DEFS`, `scoreDotColor(score: number): string`, `computeCrisisRating(scores: number[], alertCount: number): { code: string; label: string; color: string }`
  - da `pratica-statement-rows`: `buildBalanceItemsWithTotals(rawItems: IntraYearComparisonItem[]): IntraYearComparisonItem[]`, `buildIncomeItemsWithEbitda(items: IntraYearComparisonItem[], periodMonths: number): IntraYearComparisonItem[]`

- [ ] **Step 1: Creare `lib/pratica-indicators.ts`**

Copiare **verbatim** gli intervalli `288,519` e `532,579`. Le righe `520–531` sono i due `ChartConfig` (`economicIncidenceChartConfig`, `financialMarginsChartConfig`): **non** vanno in questo file — sono configurazione di presentazione, usati solo da `IndicatoriTable`, e li sposterà il Task 8. Restano in `page.tsx` fino ad allora.

```bash
cd /home/peter/DEV/budget/frontend
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '288,519p;532,579p' > lib/pratica-indicators.ts
```

Aggiungere `export ` a: `safeDivide`, `IndicatorSet`, `linearScore`, `invertedScore`, `computeIndicators`, `scoreIndicator`, `INDICATOR_DEFS`, `scoreDotColor`, `computeCrisisRating`.

- [ ] **Step 2: Verificare il diff verbatim**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '288,519p;532,579p' > /tmp/orig.txt
sed 's/^export //' lib/pratica-indicators.ts > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 3: Creare `lib/pratica-statement-rows.ts`**

Copiare **verbatim** l'intervallo `580,1008` e aggiungere `export ` a `buildBalanceItemsWithTotals` e `buildIncomeItemsWithEbitda`. Poi anteporre il blocco di import:

```ts
import type { IntraYearComparisonItem } from "@/types/api";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
import { VP_CODES, ATTIVO_CODES, PASSIVO_CODES } from "@/lib/pratica-codes";
```

Questi tre sono gli identificatori esterni realmente usati nell'intervallo, verificati con `grep`. Se `tsc` ne segnala altri, aggiungerli.

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '580,1008p' > /tmp/body.txt
```

- [ ] **Step 4: Verificare il diff verbatim**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '580,1008p' > /tmp/orig.txt
sed -n '/^export function buildBalanceItemsWithTotals(/,$p' lib/pratica-statement-rows.ts | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 5: Rimuovere i blocchi da `page.tsx` e importare**

Cancellare **dal fondo verso l'alto**: `580–1008`, poi `532–579`, poi `288–519`. Le righe `520–531` (i due `ChartConfig`) **restano**.

Aggiungere:

```ts
import {
  safeDivide,
  linearScore,
  invertedScore,
  computeIndicators,
  scoreIndicator,
  INDICATOR_DEFS,
  scoreDotColor,
  computeCrisisRating,
  type IndicatorSet,
} from "@/lib/pratica-indicators";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";
```

- [ ] **Step 6: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori, test verdi, build completata.

- [ ] **Step 7: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/pratica-indicators.ts frontend/lib/pratica-statement-rows.ts frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
refactor(pratica): estrai indicatori e costruzione righe SP/CE

Spostamento verbatim, verificato con diff contro a981ac8. I due ChartConfig
restano in page.tsx: sono configurazione di presentazione e seguiranno
IndicatoriTable, unico consumatore.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Caratterizzazione di indicatori e righe di bilancio

**Files:**
- Create: `frontend/lib/pratica-indicators.test.ts`
- Create: `frontend/lib/pratica-statement-rows.test.ts`

**Interfaces:**
- Consumes: le funzioni prodotte dal Task 4. `IntraYearComparisonItem` ha forma `{ code: string; label: string; partial_value: number; reference_value: number; prior_value: number; pct_of_reference: number; annualized_value: number }`.
- Produces: niente.

- [ ] **Step 1: Scrivere `lib/pratica-indicators.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import {
  computeCrisisRating,
  computeIndicators,
  invertedScore,
  linearScore,
  safeDivide,
  scoreDotColor,
  scoreIndicator,
} from "./pratica-indicators";

/** Azienda sana: utile, poco debito, buona liquidita'. */
const BS_SANA: Record<string, number> = {
  sp02_immob_immateriali: 20_000,
  sp03_immob_materiali: 300_000,
  sp05_rimanenze: 150_000,
  sp06_crediti_breve: 250_000,
  sp09_disponibilita_liquide: 80_000,
  sp11_capitale: 100_000,
  sp12_riserve: 250_000,
  sp13_utile_perdita: 90_000,
  sp16_debiti_breve: 260_000,
  sp16a_debiti_banche_breve: 60_000,
  sp17_debiti_lungo: 100_000,
  sp17a_debiti_banche_lungo: 100_000,
};

const IS_SANA: Record<string, number> = {
  ce01_ricavi_vendite: 1_200_000,
  ce05_materie_prime: 400_000,
  ce06_servizi: 300_000,
  ce08_costi_personale: 250_000,
  ce09_ammortamenti: 50_000,
  ce15_oneri_finanziari: 12_000,
  ce20_imposte: 30_000,
};

describe("linearScore / invertedScore", () => {
  it("clampa agli estremi", () => {
    expect(linearScore(0, 1, 2)).toBe(0);
    expect(linearScore(5, 1, 2)).toBe(1);
  });

  it("interpola linearmente a meta' scala", () => {
    expect(linearScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
  });

  it("invertedScore e' il complemento a 1", () => {
    expect(invertedScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
    expect(invertedScore(0, 1, 2)).toBe(1);
  });
});

describe("safeDivide", () => {
  it("divide normalmente", () => {
    expect(safeDivide(10, 4)).toBe(2.5);
  });

  it("denominatore zero: restituisce 0, non Infinity", () => {
    expect(safeDivide(10, 0)).toBe(0);
  });
});

describe("computeIndicators", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("produce tutti i campi dell'IndicatorSet", () => {
    for (const k of [
      "dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
      "copertura_immob", "indipendenza", "pfn", "pfn_ebitda",
      "roi", "roe", "ros", "of_mol", "materials_revenue", "services_revenue",
      "_ebitda_raw", "_quick_ratio", "_equity_over_fixed",
    ]) {
      expect(Number.isFinite(ind[k as keyof typeof ind])).toBe(true);
    }
  });

  it("EBITDA = VP - costi operativi, ammortamenti esclusi", () => {
    // 1.200.000 - (400.000 + 300.000 + 250.000) = 250.000
    expect(ind._ebitda_raw).toBeCloseTo(250_000, 2);
  });

  it("margine EBITDA in percentuale assoluta, non in decimali", () => {
    expect(ind.ebitda_margin).toBeGreaterThan(1);
    expect(ind.ebitda_margin).toBeCloseTo(250_000 / 1_200_000 * 100, 2);
  });

  it("bilancio vuoto: nessun NaN ne' Infinity", () => {
    const empty = computeIndicators({}, {});
    for (const value of Object.values(empty)) {
      expect(Number.isFinite(value)).toBe(true);
    }
  });
});

describe("scoreIndicator", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("ogni punteggio sta in [0,1]", () => {
    for (const k of ["dscr", "ebitda_margin", "current_ratio", "indipendenza",
                     "roi", "roe", "ros", "pfn_ebitda", "of_mol"] as const) {
      const s = scoreIndicator(k, ind);
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThanOrEqual(1);
    }
  });

  it("EBITDA negativo con PFN positiva: pfn_ebitda vale 0", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, pfn: 50_000, pfn_ebitda: -5 };
    expect(scoreIndicator("pfn_ebitda", bad)).toBe(0);
  });

  it("EBITDA negativo senza oneri finanziari: of_mol vale 0,5", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, of_mol: 0 };
    expect(scoreIndicator("of_mol", bad)).toBe(0.5);
  });
});

describe("computeCrisisRating", () => {
  it("nessun indicatore oltre soglia e nessun segnale: A3", () => {
    expect(computeCrisisRating([1, 1, 1, 0.9], 0).code).toBe("A3");
  });

  it("due indicatori oltre soglia e nessun segnale: A2", () => {
    expect(computeCrisisRating([0.1, 0.2, 1, 1], 0).code).toBe("A2");
  });

  it("i segnali extracontabili peggiorano il rating", () => {
    const senza = computeCrisisRating([1, 1, 1, 1], 0).code;
    const con = computeCrisisRating([1, 1, 1, 1], 3).code;
    expect(con).not.toBe(senza);
  });
});

describe("scoreDotColor", () => {
  it("verde sopra 0,67, giallo in mezzo, rosso sotto 0,33", () => {
    expect(scoreDotColor(0.9)).not.toBe(scoreDotColor(0.5));
    expect(scoreDotColor(0.5)).not.toBe(scoreDotColor(0.1));
  });
});
```

- [ ] **Step 2: Scrivere `lib/pratica-statement-rows.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import type { IntraYearComparisonItem } from "@/types/api";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "./pratica-statement-rows";

const item = (
  code: string,
  partial: number,
  reference = 0,
  prior = 0,
): IntraYearComparisonItem => ({
  code,
  label: code,
  partial_value: partial,
  reference_value: reference,
  prior_value: prior,
  pct_of_reference: 0,
  annualized_value: 0,
});

describe("buildBalanceItemsWithTotals", () => {
  const raw = [
    item("sp03_immob_materiali", 300_000, 280_000),
    item("sp09_disponibilita_liquide", 80_000, 60_000),
    item("sp11_capitale", 100_000, 100_000),
    item("sp16_debiti_breve", 280_000, 240_000),
  ];

  it("riconcilia ogni anno in modo indipendente", () => {
    const out = buildBalanceItemsWithTotals(raw);
    const altri = out.find((i) => i.code === "sp16g_altri_debiti_breve");
    expect(altri?.partial_value).toBe(280_000);
    expect(altri?.reference_value).toBe(240_000);
  });

  it("NON tocca annualized_value: la scrive la tab Proiezione", () => {
    const withAnn = raw.map((i) => ({ ...i, annualized_value: 999 }));
    const out = buildBalanceItemsWithTotals(withAnn);
    for (const row of out) {
      if (raw.some((r) => r.code === row.code)) {
        expect(row.annualized_value).toBe(999);
      }
    }
  });

  it("emette righe di totale oltre alle voci di partenza", () => {
    const out = buildBalanceItemsWithTotals(raw);
    expect(out.length).toBeGreaterThan(raw.length);
  });
});

describe("buildIncomeItemsWithEbitda", () => {
  const raw = [
    item("ce01_ricavi_vendite", 900_000, 1_200_000),
    item("ce05_materie_prime", 300_000, 400_000),
    item("ce06_servizi", 225_000, 300_000),
    item("ce08_costi_personale", 187_500, 250_000),
    item("ce09_ammortamenti", 37_500, 50_000),
  ];

  it("inserisce una riga EBITDA", () => {
    const out = buildIncomeItemsWithEbitda(raw, 9);
    expect(out.some((i) => i.code.toLowerCase().includes("ebitda"))).toBe(true);
  });

  it("il fattore di annualizzazione dipende da periodMonths", () => {
    const a = buildIncomeItemsWithEbitda(raw, 9);
    const b = buildIncomeItemsWithEbitda(raw, 6);
    const ricaviA = a.find((i) => i.code === "ce01_ricavi_vendite");
    const ricaviB = b.find((i) => i.code === "ce01_ricavi_vendite");
    expect(ricaviA?.partial_value).toBe(ricaviB?.partial_value);
    expect(a.length).toBe(b.length);
  });

  it("elenco vuoto: non lancia", () => {
    expect(() => buildIncomeItemsWithEbitda([], 12)).not.toThrow();
  });
});
```

- [ ] **Step 3: Eseguire i test**

Run: `npm test`
Expected: PASS. Come nel Task 3: se un valore atteso non corrisponde, **correggere il test, non la funzione**, e annotare la differenza nel report. In particolare i nomi esatti delle righe sintetiche (EBITDA, totali) vanno letti dall'implementazione, non indovinati: se `code.includes("ebitda")` non trova nulla, ispezionare l'output di `buildIncomeItemsWithEbitda` e usare il codice reale.

- [ ] **Step 4: Commit**

```bash
cd /home/peter/DEV/budget
git add frontend/lib/pratica-indicators.test.ts frontend/lib/pratica-statement-rows.test.ts
git commit -m "$(cat <<'EOF'
test(pratica): caratterizzazione di indicatori e righe SP/CE

Fissa il comportamento attuale di computeIndicators, scoreIndicator,
computeCrisisRating e dei due builder di righe, inclusi i casi limite gia'
noti (EBITDA negativo, bilancio vuoto, annualized_value preservato).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Regole rettifiche + `RettificheTab`

Il pezzo più grande: ~450 righe di regole e ~1.320 di componente.

**Files:**
- Create: `frontend/lib/pratica-rettifiche-rules.ts`
- Create: `frontend/components/pratica/RettificheTab.tsx`
- Modify: `frontend/app/pratica/page.tsx`

**Interfaces:**
- Consumes: da `@/lib/pratica-format` — `formatEuro`, `formatInputNumber`, `parseInputNumber`; da `@/lib/pratica-reconcile` — `reconcileSubfields`; da `@/types/api` — `AdjustableFinancialYear`, `RettificaEntry`.
- Produces:
  - da `pratica-rettifiche-rules`: `ProposalRule`, `PROPOSAL_RULES`, `EDITABLE_RETTIFICHE: Set<string>`, `AUTO_ADJUSTED: Set<string>`, `NON_POSTABLE_FIELDS: Set<string>`, `RETTIFICHE_LABELS: Record<string, string>`, `AcctCategory`, `CE_POSITIVE_FIELDS`, `CE_NEGATIVE_FIELDS`, `fieldCategory`, `allowedCounterpartCategories`, `computeCpDelta`, `COUNTERPART_GROUPS`, `COUNTERPART_PICKER_LABELS`, `COUNTERPART_OPTIONS`, `RETTIFICHE_BS_ATTIVO`, `RETTIFICHE_BS_PN`, `RETTIFICHE_BS_OTHER_PASSIVO`, `DEBT_GROUPS`, `PASSIVO_TOTAL_FIELDS`, `CE_A`, `CE_B`, `CE_C`, `CE_D`, `CE_E`, `CE_IMPOSTE`, `ProposalMode`, `DoubleEntryProposal`, `RETTIFICHE_MAX`
  - da `components/pratica/RettificheTab`: `export function RettificheTab(props: RettificheTabProps)`, con `RettificheTabProps` definita nello stesso file.

- [ ] **Step 1: Creare `lib/pratica-rettifiche-rules.ts`**

Copiare **verbatim** gli intervalli `1009,1396`, `1456,1503` e `1520,1521`. Nota: `1397–1455` (`DETAIL_PARENTS`) è già in `pratica-codes.ts` dal Task 2, e `1504–1519` (`RettificheTabProps`) va invece nel file del componente.

```bash
cd /home/peter/DEV/budget/frontend
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '1009,1396p;1456,1503p;1520,1521p' > lib/pratica-rettifiche-rules.ts
```

Aggiungere `export ` a tutte le dichiarazioni di primo livello elencate in **Produces**. Il file non ha bisogno di import.

- [ ] **Step 2: Verificare il diff verbatim**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '1009,1396p;1456,1503p;1520,1521p' > /tmp/orig.txt
sed 's/^export //' lib/pratica-rettifiche-rules.ts > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 3: Creare `components/pratica/RettificheTab.tsx`**

Copiare **verbatim** gli intervalli `1504,1519` (l'interfaccia props) e `1522,2838` (il componente).

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '1504,1519p;1522,2838p' > /tmp/body.txt
```

Anteporre `"use client";`, una riga vuota, e il blocco di import. Aggiungere `export ` a `function RettificheTab`. Lasciare `interface RettificheTabProps` **senza** `export` se non serve fuori (`tsc` lo dirà).

Gli import necessari vanno ricavati dal corpo: `tsc` elencherà ogni identificatore mancante. I gruppi da cui provengono sono:
- `react` — `useState`, `useEffect`, `useMemo`, `useCallback`, `useRef` (solo quelli usati)
- `sonner` — `toast`
- `lucide-react` — le icone usate
- `@/components/ui/*` — `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `Button`, `Input`, `Label`, `Table` e affini, `Select` e affini, `Dialog` e affini, `AlertDialog` e affini, `Alert`, `Badge`, `Tabs` e affini, `Checkbox`
- `@/lib/utils` — `cn`, `getErrorMessage`
- `@/lib/pratica-format` — `formatEuro`, `formatInputNumber`, `parseInputNumber`
- `@/lib/pratica-reconcile` — `reconcileSubfields`
- `@/lib/pratica-rettifiche-rules` — tutte le costanti/funzioni usate
- `@/types/api` — i tipi usati

- [ ] **Step 4: Verificare il diff verbatim del componente**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '1504,1519p;1522,2838p' > /tmp/orig.txt
sed -n '/^interface RettificheTabProps {/,$p' components/pratica/RettificheTab.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 5: Rimuovere i blocchi da `page.tsx` e importare**

Cancellare **dal fondo verso l'alto**: `1522–2838`, `1504–1521`, `1456–1503`, `1009–1396`.

Aggiungere:

```ts
import { RettificheTab } from "@/components/pratica/RettificheTab";
```

più, da `@/lib/pratica-rettifiche-rules`, i soli identificatori che `page.tsx` usa ancora (verificarli con `tsc`, non importarli tutti a scatola chiusa).

- [ ] **Step 6: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori, test verdi, build completata.

- [ ] **Step 7: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/pratica-rettifiche-rules.ts frontend/components/pratica/RettificheTab.tsx frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
refactor(pratica): estrai le regole rettifiche e RettificheTab

Spostamento verbatim, verificato con diff contro a981ac8. CLAUDE.md dava
per condivise ~15 costanti fra RettificheTab e le tab Confronto/Proiezione:
verificate una per una, l'unica condivisa era DETAIL_PARENTS, gia' spostata
fra i codici. L'estrazione non ha richiesto alcun modulo ponte.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Tabelle Confronto, Proiezione e segnali extracontabili

**Files:**
- Create: `frontend/components/pratica/ComparisonTable.tsx`
- Create: `frontend/components/pratica/ProjectionTable.tsx`
- Create: `frontend/components/pratica/ExtraAccountingAlerts.tsx`
- Modify: `frontend/app/pratica/page.tsx`

**Interfaces:**
- Consumes: da `@/lib/pratica-codes` — `DETAIL_PARENTS` e `ALWAYS_SHOW_CODES` (usati da `ComparisonTable` e `ProjectionTable`), `VP_CODES` e `EDITABLE_CE_CODES` (solo `ProjectionTable`), `EXTRA_ALERT_DEFS` (solo `ExtraAccountingAlerts`); da `@/lib/pratica-format` — i formatter usati; `IntraYearComparisonItem` da `@/types/api`.
- Produces:
  - `export function ComparisonTable(props: { items: IntraYearComparisonItem[]; periodMonths: number; referenceYear: number; partialYear: number; priorYear: number | null; showAnnualized: boolean; showRevenuePct?: boolean })`
  - `export function ProjectionTable(props: { items: IntraYearComparisonItem[]; periodMonths: number; referenceYear: number; partialYear: number; showRevenuePct?: boolean; overrides: Record<string, string>; onOverrideChange: (code: string, value: string) => void })`
  - `export function ExtraAccountingAlerts(props: { alerts: Record<string, boolean>; onChange: (alerts: Record<string, boolean>) => void })`

- [ ] **Step 1: Creare i tre file**

Intervalli, tutti da `git show a981ac8:frontend/app/pratica/page.tsx`:

| File | Intervallo |
|---|---|
| `ComparisonTable.tsx` | `4580,4799` |
| `ProjectionTable.tsx` | `4800,5026` |
| `ExtraAccountingAlerts.tsx` | `5066,5115` |

Per ciascuno: `"use client";`, riga vuota, blocco di import, poi il corpo verbatim con `export ` davanti alla `function`.

```bash
cd /home/peter/DEV/budget/frontend
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '4580,4799p' > /tmp/comparison.txt
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '4800,5026p' > /tmp/projection.txt
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '5066,5115p' > /tmp/alerts.txt
```

- [ ] **Step 2: Verificare i tre diff verbatim**

Ogni ancora è la prima riga del blocco spostato:

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '4580,4799p' > /tmp/orig.txt
sed -n '/^\/\/ Comparison Table Component/,$p' components/pratica/ComparisonTable.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "COMPARISON OK"

git show a981ac8:frontend/app/pratica/page.tsx | sed -n '4800,5026p' > /tmp/orig.txt
sed -n '/^\/\/ Projection Table Component/,$p' components/pratica/ProjectionTable.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "PROJECTION OK"

git show a981ac8:frontend/app/pratica/page.tsx | sed -n '5066,5115p' > /tmp/orig.txt
sed -n '/^export function ExtraAccountingAlerts({/,$p' components/pratica/ExtraAccountingAlerts.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "ALERTS OK"
```
Expected: tre `OK`.

- [ ] **Step 3: Rimuovere i blocchi da `page.tsx` e importare**

Cancellare **dal fondo verso l'alto**: `5066–5115`, `4800–5026`, `4580–4799`.

```ts
import { ComparisonTable } from "@/components/pratica/ComparisonTable";
import { ProjectionTable } from "@/components/pratica/ProjectionTable";
import { ExtraAccountingAlerts } from "@/components/pratica/ExtraAccountingAlerts";
```

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori, test verdi, build completata.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/components/pratica/ComparisonTable.tsx frontend/components/pratica/ProjectionTable.tsx frontend/components/pratica/ExtraAccountingAlerts.tsx frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
refactor(pratica): estrai ComparisonTable, ProjectionTable e i segnali extracontabili

Spostamento verbatim, verificato con diff contro a981ac8.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `IndicatoriTable` e `StampaContent`

**Files:**
- Create: `frontend/components/pratica/IndicatoriTable.tsx`
- Create: `frontend/components/pratica/StampaContent.tsx`
- Modify: `frontend/app/pratica/page.tsx`

**Interfaces:**
- Consumes: da `@/lib/pratica-indicators` — `computeIndicators`, `scoreIndicator`, `INDICATOR_DEFS`, `scoreDotColor`, `computeCrisisRating`, `type IndicatorSet`; da `@/lib/pratica-statement-rows` — `buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda`; da `@/lib/pratica-codes` — `EXTRA_ALERT_DEFS`, `ALWAYS_SHOW_CODES`, `VP_CODES`, `EDITABLE_CE_CODES` (tutti usati da `StampaContent`); da `@/lib/pratica-format` — i formatter; da `@/contexts/PraticaActionContext` — `usePrimaryAction`.
- Produces:
  - `export function IndicatoriTable(props: { comparison: IntraYearComparison; forecastBs: Record<string, number>; forecastIs: Record<string, number>; extraAlerts: Record<string, boolean>; showRating?: boolean; hideProiezione?: boolean })`
  - `export function StampaContent(props: { comparison: IntraYearComparison; overrides: Record<string, string>; projectedBS: IntraYearComparisonItem[]; forecastBs: Record<string, number>; forecastIs: Record<string, number>; extraAlerts: Record<string, boolean>; companyName: string; fiscalYear: number; periodMonths: number; companyId?: number; scenarioId?: number; onBeforePromote?: () => Promise<void> })`

- [ ] **Step 1: Creare `components/pratica/IndicatoriTable.tsx`**

Il componente porta con sé i due `ChartConfig` rimasti in `page.tsx` dal Task 4: copiare **verbatim** l'intervallo `520,531` **e** `5116,5345`, in quest'ordine.

```bash
cd /home/peter/DEV/budget/frontend
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '520,531p;5116,5345p' > /tmp/indicatori.txt
```

`"use client";`, riga vuota, import, poi il corpo. `export ` davanti a `function IndicatoriTable`. I due `ChartConfig` restano non esportati.

- [ ] **Step 2: Verificare il diff verbatim**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '520,531p;5116,5345p' > /tmp/orig.txt
sed -n '/^const economicIncidenceChartConfig = {/,$p' components/pratica/IndicatoriTable.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 3: Creare `components/pratica/StampaContent.tsx`**

Copiare **verbatim** l'intervallo `5346,6019` (fino a fine file).

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '5346,6019p' > /tmp/stampa.txt
```

`StampaContent` **non** rende `IndicatoriTable` (verificato eseguendo il task: entrambi sono resi dal genitore `InfraannualePage`, e `StampaContent` costruisce le proprie tabelle di indicatori) — nessun import fra i due. Registra anche la propria azione primaria con `usePrimaryAction` — l'import va da `@/contexts/PraticaActionContext`. Usa `useRouter`, `useApp`, `useAuth`, `usePratica`: importarli rispettivamente da `next/navigation`, `@/contexts/AppContext`, `@/contexts/AuthContext`, `@/contexts/PraticaContext`.

- [ ] **Step 4: Verificare il diff verbatim**

```bash
git show a981ac8:frontend/app/pratica/page.tsx | sed -n '5346,6019p' > /tmp/orig.txt
sed -n '/^\/\/ Print-ready view for PDF generation/,$p' components/pratica/StampaContent.tsx | sed 's/^export //' > /tmp/new.txt
diff /tmp/orig.txt /tmp/new.txt && echo "VERBATIM OK"
```
Expected: `VERBATIM OK`

- [ ] **Step 5: Rimuovere i blocchi da `page.tsx` e importare**

Cancellare **dal fondo verso l'alto**: `5346–6019`, `5116–5345`, `520–531`.

```ts
import { IndicatoriTable } from "@/components/pratica/IndicatoriTable";
import { StampaContent } from "@/components/pratica/StampaContent";
```

Ripulire gli import ora inutilizzati in `page.tsx` (Recharts, `ChartContainer`, icone rimaste orfane): `tsc` con `noUnusedLocals` non è attivo, quindi vanno cercati con `npm run lint`, che li segnala come warning `@typescript-eslint/no-unused-vars`.

- [ ] **Step 6: Verificare, e misurare il risultato**

```bash
npx tsc --noEmit && npm test && npm run build
wc -l app/pratica/page.tsx
```
Expected: 0 errori, test verdi, build completata, `page.tsx` intorno alle 1.850 righe.

- [ ] **Step 7: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/components/pratica/IndicatoriTable.tsx frontend/components/pratica/StampaContent.tsx frontend/app/pratica/page.tsx
git commit -m "$(cat <<'EOF'
refactor(pratica): estrai IndicatoriTable e StampaContent

Spostamento verbatim, verificato con diff contro a981ac8. I due ChartConfig
seguono IndicatoriTable, unico consumatore. page.tsx passa da 6.019 a circa
1.850 righe.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Documentazione e rimozione dell'iniezione di `reconcileSubfields`

**Files:**
- Modify: `frontend/hooks/use-rettifiche-year.ts`
- Modify: `frontend/app/pratica/page.tsx` (le due chiamate a `useRettificheYear`)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `reconcileSubfields` da `@/lib/pratica-reconcile`.
- Produces: `useRettificheYear(companyId: number | null, year: number, periodMonths: number | undefined, onSaved: () => void): RettificheYear` — un parametro in meno.

- [ ] **Step 1: Rimuovere il parametro `reconcile`**

In `frontend/hooks/use-rettifiche-year.ts`, aggiungere in testa:

```ts
import { reconcileSubfields } from "@/lib/pratica-reconcile";
```

Rimuovere il parametro `reconcile` dalla firma e la sua riga di JSDoc (`@param reconcile reconcileSubfields, injected to avoid importing from a route module.` — il vincolo che la motivava non esiste più). Sostituire le tre chiamate a `reconcile(...)` con `reconcileSubfields(...)`, e togliere `reconcile` dalle dipendenze di `useCallback` di `load` e `reset`.

- [ ] **Step 2: Aggiornare i due call site**

In `frontend/app/pratica/page.tsx`, le chiamate diventano:

```tsx
  const verifica = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear,
    periodMonths < 12 ? periodMonths : undefined,
    invalidateDownstream,
  );
  const storico = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear - 1,
    undefined,               // full 12-month year
    invalidateDownstream,
  );
```

- [ ] **Step 3: Eliminare `KEY_BS_CODES`, codice morto**

`KEY_BS_CODES` (originariamente righe 213–221, ora in `lib/pratica-codes.ts`) **non ha alcun consumatore**: è stato spostato verbatim dai task precedenti perché quei task muovono e non giudicano. Qui va rimosso.

Prima la prova, poi la cancellazione:

```bash
cd /home/peter/DEV/budget/frontend
grep -rn "KEY_BS_CODES" app components lib
```
Expected: una sola occorrenza, la dichiarazione in `lib/pratica-codes.ts`.

Se e solo se il grep conferma, eliminare la dichiarazione (e il suo commento introduttivo) da `lib/pratica-codes.ts` e togliere `KEY_BS_CODES` dall'import in `app/pratica/page.tsx`, se presente. Se il grep trova altri usi, **non cancellare** e annotarlo nel report.

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: 0 errori, test verdi, build completata.

- [ ] **Step 5: Aggiornare `CLAUDE.md`**

Nella sezione **Rettifiche (BS/IS Adjustments Journal)**, la nota "Known follow-up" dice che `RettificheTab` vive dentro `page.tsx` perché si appoggia a ~15 costanti condivise. Sostituirla con lo stato reale:

> **Struttura (2026-08-10):** `RettificheTab` vive in `frontend/components/pratica/RettificheTab.tsx`; le sue regole di partita doppia e il layout righe stanno in `frontend/lib/pratica-rettifiche-rules.ts`. La vecchia nota parlava di ~15 costanti condivise con le tab Confronto e Proiezione: verificate una per una, l'unica davvero condivisa era `DETAIL_PARENTS`, che ora vive in `lib/pratica-codes.ts` ed è usata da `RettificheTab`, `ComparisonTable` e `ProjectionTable`. Non è servito alcun modulo ponte oltre a quello.

Nella sezione **Il percorso unico "Pratica"**, aggiungere in coda alla mappa dei file:

> **Moduli della pratica (2026-08-10).** `app/pratica/page.tsx` è sceso da 6.019 a ~1.850 righe. Le funzioni pure stanno in `lib/pratica-format.ts` (formattazione), `lib/pratica-codes.ts` (tabelle di codici IV-CEE, `DETAIL_PARENTS`, `EXTRA_ALERT_DEFS`), `lib/pratica-reconcile.ts` (`reconcileSubfields`), `lib/pratica-indicators.ts` (indicatori, scoring, `computeCrisisRating`) e `lib/pratica-statement-rows.ts` (costruzione righe SP/CE); i componenti in `components/pratica/`. Regola: `lib/pratica-*` non importa mai da `app/` o `components/`. Tre suite di caratterizzazione (`lib/pratica-reconcile.test.ts`, `lib/pratica-indicators.test.ts`, `lib/pratica-statement-rows.test.ts`) fissano il comportamento dei calcoli — fissano quello **attuale**, non lo giudicano corretto.

Nella stessa sezione, sostituire il primo dei due "follow-up differiti" (quello che dice che il gate è applicato solo in navigazione e che le render guard non lo ricontrollano) con:

> **Il gate è applicato anche al render (2026-08-10).** `blockedStep()` in `lib/pratica-steps.ts` decide se lo step corrente è raggiungibile, e una guardia unica in `app/pratica/page.tsx` avvolge i sette rami `activeTab`. Due comportamenti deliberati: uno step **sconosciuto non blocca** (i workflow ne omettono di proposito — bloccare creerebbe vicoli ciechi), e il controllo legge **la stessa cache dello stepper**, senza interrogare il server. Quindi se la cache dice "confermato" e il server dice il contrario, si passa: **non è un confine di autorizzazione** e non chiude un exploit noto (nessuna delle review del 2026-08-08 era riuscita a costruirne uno). Il guadagno è che l'invariante non dipende più dal fatto che ogni sito di navigazione se la ricordi.

Il secondo follow-up (il monolite) va aggiornato: `page.tsx` non è più da 5.900 righe, ma la decomposizione del componente wizard in tab-componenti resta esplicitamente non fatta.

- [ ] **Step 6: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/hooks/use-rettifiche-year.ts frontend/app/pratica/page.tsx frontend/lib/pratica-codes.ts CLAUDE.md
git commit -m "$(cat <<'EOF'
refactor(rettifiche): l'hook importa reconcileSubfields invece di riceverlo

Il parametro esisteva solo per non importare da un modulo di rotta (lo
diceva il suo stesso JSDoc); con la funzione in lib/pratica-reconcile.ts il
vincolo non c'e' piu'.

Rimosso KEY_BS_CODES, senza consumatori (spostato verbatim dai task
precedenti perche' quelli muovono e non giudicano).

CLAUDE.md aggiornato: mappa dei moduli della pratica, correzione della nota
sulle ~15 costanti condivise, e stato reale del gate al render.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Verifica finale (a carico del controller, dopo il Task 9)

- [ ] `npx tsc --noEmit` → 0 errori
- [ ] `npm test` → tutte le suite verdi (`pratica-steps`, `pratica-reconcile`, `pratica-indicators`, `pratica-statement-rows`)
- [ ] `npm run build` → completata
- [ ] `wc -l frontend/app/pratica/page.tsx` → ~1.850
- [ ] Giro browser su `http://localhost:3000` (server già avviato dall'utente), su una pratica reale:
  - le otto tab del wizard si aprono e mostrano gli stessi dati di prima
  - le rettifiche si applicano e il giornale si popola
  - il Confronto mostra le righe di dettaglio riconciliate
  - la Proiezione calcola e la Stampa rende le tabelle e i commenti
  - forzando `analysisStep` a `"stampa"` in `localStorage` su una pratica a rettifiche non confermate, appare la card "Passaggio non ancora raggiungibile" con il bottone di ritorno a Rettifiche
