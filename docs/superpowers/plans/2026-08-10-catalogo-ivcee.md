# Catalogo IV-CEE unico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire i sei elenchi paralleli di righe IV-CEE con un catalogo unico ad albero, da cui ogni vista proietta il livello di sintesi che già mostra oggi.

**Architecture:** `frontend/lib/ivcee-catalog.ts` sostituisce `ivcee-balance-catalog.ts` e copre SP e CE. Contiene una tabella `VOCI` (codice → padre, sezione, ordine, etichetta autonoma, etichetta contestuale) e sopra di essa le funzioni di proiezione che le viste consumano. Il catalogo dice *cosa esiste e come si chiama*; ogni vista continua a decidere *come appare*.

**Tech Stack:** Next.js 15 (app router), React 19, TypeScript 5, Vitest 3, shadcn/ui, Tailwind v3.

Spec: `docs/superpowers/specs/2026-08-10-catalogo-ivcee-design.md`

## Global Constraints

- **Branch: `refactor/catalogo-ivcee`.** Deroga voluta alla convenzione del progetto: Jenkins builda da `main`, quindi il branch separato tiene lo staging fuori finché il lavoro non è pronto. **Non fare merge su `main` e non pushare** — decide il controller a fine lavoro.
- **I server dev girano già** (backend :8000, frontend :3000), avviati dall'utente. **Non avviarli, non fermarli, non riavviarli, non toccare quelle porte.**
- **Terminare ogni messaggio di commit con:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Line endings:** il repo ha file con terminatori misti. `app/pratica/page.tsx`, i `lib/pratica-*.ts` e i file in `components/pratica/` sono **CRLF**; i `lib/*.test.ts` sono **LF**. Verificare il file che si tocca invece di assumere, ed eseguire `git diff --stat` prima di ogni commit: un file che risulta riscritto per intero significa che un tool ha normalizzato i terminatori — va ripristinato, non committato.
- **Solo componenti shadcn/ui** nel codice che si scrive; niente `<button>`/`<table>`/`<input>` grezzi.
- **Niente emoji.** Icone da `lucide-react`. **Testo UI in italiano.** Colori semantici (`text-foreground`, `bg-card`), mai esadecimali.
- **Dipendenza unidirezionale:** `lib/` non importa mai da `app/` o `components/`.
- **Comandi frontend da `/home/peter/DEV/budget/frontend`**, comandi git da `/home/peter/DEV/budget`.
- `npx tsc --noEmit` pulito, `npm test` verde, `npm run build` completata prima di ogni commit di codice.
- `npm run lint` ha warning preesistenti in `app/pratica/page.tsx`: non sono di questo lavoro. Un *errore* di lint sì.

### L'invariante che governa tutto il lavoro

**Per ciascuna delle sei viste, l'elenco dei codici resi e il loro ordine devono restare identici prima e dopo.** Il Task 1 lo fissa come test; ogni task successivo deve tenerlo verde. L'unica eccezione consentita, ed è esplicita nel Task 8, sono le **etichette** di 38 codici nella scheda Rettifiche — mai i codici, mai l'ordine.

### La regola delle etichette

Ogni voce ha un'etichetta **autonoma** (auto-esplicativa, usabile senza contesto) e, dove serve, una **contestuale** (breve, presuppone l'intestazione sopra).

Derivazione dalle fonti attuali, in quest'ordine di precedenza:

```
autonoma  = COUNTERPART_PICKER_LABELS[code]        // solo i 14 sotto-conti dei debiti
          ?? relabel[code]                          // grafia del Confronto: vince
          ?? RETTIFICHE_LABELS[code]                // per i codici che solo Rettifiche etichetta

contestuale = relabel[code], se diversa dall'autonoma; altrimenti assente
```

`relabel` sono le due mappe in `lib/pratica-statement-rows.ts` (righe 52 e 341).
`RETTIFICHE_LABELS` e `COUNTERPART_PICKER_LABELS` stanno in `lib/pratica-rettifiche-rules.ts`.

Le etichette vanno **senza** spazi di indentazione iniziali: l'indentazione è resa, non testo. Le fonti attuali le incorporano (`"  1) Verso clienti"`); il catalogo le memorizza pulite (`"1) Verso clienti"`) e chi rende applica il proprio rientro.

---

## Struttura dei file

**Creati:**

| File | Responsabilità |
|---|---|
| `frontend/lib/ivcee-catalog.ts` | tabella `VOCI` + funzioni di proiezione |
| `frontend/lib/ivcee-catalog.test.ts` | test strutturali del catalogo |
| `frontend/lib/ivcee-catalog-parity.test.ts` | l'invariante prima/dopo delle sei viste + il cross-check delle etichette contro le fonti vecchie |

**Modificati:**

| File | Modifica |
|---|---|
| `frontend/app/forecast/balance/page.tsx` | consuma le righe dal nuovo catalogo |
| `frontend/components/report/report-appendices.tsx` | idem |
| `frontend/app/forecast/income/page.tsx` | elenco CE inline → catalogo |
| `frontend/components/report/report-composition.tsx` | aggregazioni a mano → proiezione |
| `frontend/lib/pratica-statement-rows.ts` | mappe `relabel` → catalogo |
| `frontend/components/pratica/RettificheTab.tsx` | array + `RETTIFICHE_LABELS` → catalogo |
| `frontend/lib/pratica-rettifiche-rules.ts` | rimozione delle mappe etichette |
| `CLAUDE.md` | nuova mappa dei moduli, procedura "aggiungere una voce" |

**Eliminati:** `frontend/lib/ivcee-balance-catalog.ts` (assorbito dal nuovo).

---

### Task 1: L'invariante prima/dopo

Nessuna modifica al codice di produzione. Questo task fotografa lo stato attuale delle sei viste, così ogni adozione successiva è verificabile.

**Files:**
- Create: `frontend/lib/ivcee-catalog-parity.test.ts`

**Interfaces:**
- Consumes: `BALANCE_STATEMENT_ROWS` da `@/lib/ivcee-balance-catalog`; `RETTIFICHE_BS_ATTIVO`, `RETTIFICHE_BS_PN`, `RETTIFICHE_BS_OTHER_PASSIVO`, `DEBT_GROUPS`, `CE_A`, `CE_B`, `CE_C`, `CE_D`, `CE_E`, `CE_IMPOSTE` da `@/lib/pratica-rettifiche-rules`; `buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda` da `@/lib/pratica-statement-rows`; `IntraYearComparisonItem` da `@/types/api`.
- Produces: niente — è solo una rete.

- [ ] **Step 1: Scrivere il test dell'invariante**

Crea `frontend/lib/ivcee-catalog-parity.test.ts` (terminatori **LF**, come gli altri `lib/*.test.ts`).

Le liste attese **non vanno trascritte a mano**: si generano una volta eseguendo il test in modalità "stampa" e si incollano. Scrivi prima questa versione, che stampa e fallisce di proposito:

```ts
import { describe, expect, it } from "vitest";
import { BALANCE_STATEMENT_ROWS } from "@/lib/ivcee-balance-catalog";
import {
  CE_A, CE_B, CE_C, CE_D, CE_E, CE_IMPOSTE,
  DEBT_GROUPS,
  RETTIFICHE_BS_ATTIVO, RETTIFICHE_BS_OTHER_PASSIVO, RETTIFICHE_BS_PN,
} from "@/lib/pratica-rettifiche-rules";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";
import type { IntraYearComparisonItem } from "@/types/api";

/** Una riga di prospetto: il campo se c'è, altrimenti un marcatore stabile. */
const rowKey = (r: { field?: string; label: string }) => r.field ?? `computed:${r.label}`;

/** Ordine di resa di RettificheTab: attivo, PN, altri passivi, gruppi debiti, CE. */
const rettificheCodes = (): string[] => [
  ...RETTIFICHE_BS_ATTIVO,
  ...RETTIFICHE_BS_PN,
  ...RETTIFICHE_BS_OTHER_PASSIVO,
  ...DEBT_GROUPS.flatMap((g) => [...g.entro, ...g.oltre]),
  ...CE_A, ...CE_B, ...CE_C, ...CE_D, ...CE_E, ...CE_IMPOSTE,
];

const item = (code: string): IntraYearComparisonItem => ({
  code, label: code,
  partial_value: 1000, reference_value: 900, prior_value: 800,
  pct_of_reference: 0, annualized_value: 0,
});

/** Fixture: ogni codice che le viste possono ricevere dal server. */
const BS_FIXTURE = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi", "sp11_capitale", "sp12_riserve",
  "sp13_utile_perdita", "sp14_fondi_rischi", "sp15_tfr",
  "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
].map(item);

const CE_FIXTURE = [
  "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni",
  "ce04_altri_ricavi", "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti", "ce12_oneri_diversi", "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari", "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
  "ce17_rettifiche_attivita_fin", "ce18_proventi_straordinari",
  "ce19_oneri_straordinari", "ce20_imposte",
].map(item);

describe("STAMPA delle liste attuali — rimuovere dopo aver generato le costanti", () => {
  it("stampa", () => {
    const dump = {
      balance: BALANCE_STATEMENT_ROWS.map(rowKey),
      rettifiche: rettificheCodes(),
      confrontoBS: buildBalanceItemsWithTotals(BS_FIXTURE).map((i) => i.code),
      confrontoCE: buildIncomeItemsWithEbitda(CE_FIXTURE, 9).map((i) => i.code),
    };
    console.log(JSON.stringify(dump, null, 2));
    expect(true).toBe(true);
  });
});
```

- [ ] **Step 2: Generare le liste attese**

Run: `npx vitest run lib/ivcee-catalog-parity.test.ts`
Expected: PASS, con il JSON stampato a console.

Copia il JSON stampato. Sarà il contenuto delle costanti attese al passo successivo.

- [ ] **Step 3: Sostituire la stampa con le asserzioni**

Elimina il `describe("STAMPA …")` e mettici al suo posto le costanti generate più le asserzioni. La forma è questa — i valori dentro gli array vengono **dal JSON che hai appena stampato**, non da questo piano:

```ts
// Generato al Task 1 dallo stato pre-refactoring. Questi elenchi NON vanno
// aggiornati per far passare un test: se cambiano, una vista ha perso o
// riordinato una riga, ed è quello il difetto.
const ATTESI_BALANCE: string[] = [ /* incolla qui dump.balance */ ];
const ATTESI_RETTIFICHE: string[] = [ /* incolla qui dump.rettifiche */ ];
const ATTESI_CONFRONTO_BS: string[] = [ /* incolla qui dump.confrontoBS */ ];
const ATTESI_CONFRONTO_CE: string[] = [ /* incolla qui dump.confrontoCE */ ];

describe("invariante: nessuna vista perde o riordina righe", () => {
  it("prospetto SP (forecast/balance e report-appendices)", () => {
    expect(BALANCE_STATEMENT_ROWS.map(rowKey)).toEqual(ATTESI_BALANCE);
  });

  it("Rettifiche: ordine di resa completo", () => {
    expect(rettificheCodes()).toEqual(ATTESI_RETTIFICHE);
  });

  it("Confronto: righe SP costruite dal server", () => {
    expect(buildBalanceItemsWithTotals(BS_FIXTURE).map((i) => i.code)).toEqual(ATTESI_CONFRONTO_BS);
  });

  it("Confronto: righe CE costruite dal server", () => {
    expect(buildIncomeItemsWithEbitda(CE_FIXTURE, 9).map((i) => i.code)).toEqual(ATTESI_CONFRONTO_CE);
  });
});
```

Nota che `forecast/income` e `report-composition` non compaiono qui: i loro elenchi sono ancora inline nei componenti e non importabili. Il Task 5 e il Task 6 li aggiungono a questo file **nel momento in cui li estraggono**, che è il primo istante in cui diventano osservabili.

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test`
Expected: 0 errori; il conteggio test sale di 4 rispetto ai 61 attuali (65).

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog-parity.test.ts
git commit -m "$(cat <<'EOF'
test(ivcee): fissa l'elenco righe delle viste prima del refactoring

Fotografia dello stato attuale: se una vista perde o riordina una riga
durante l'adozione del catalogo, questi test lo dicono nel task che l'ha
causato invece che a lavoro finito.

forecast/income e report-composition non sono ancora osservabili (elenchi
inline nei componenti): entrano in questo file quando verranno estratti.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Il catalogo — la tabella delle voci

**Files:**
- Create: `frontend/lib/ivcee-catalog.ts`
- Create: `frontend/lib/ivcee-catalog.test.ts`

**Interfaces:**
- Consumes: niente (è una foglia).
- Produces:
  ```ts
  export type IvceeSection = "attivo" | "passivo" | "patrimonio" | "ce";
  export interface Voce {
    code: string;
    /** codice dell'aggregato che la contiene; null per una voce di primo livello */
    parent: string | null;
    section: IvceeSection;
    /** ordine fra pari sotto lo stesso padre */
    order: number;
    /** auto-esplicativa: usabile senza contesto (giornale, selettore, dialoghi) */
    label: string;
    /** breve: presuppone l'intestazione sopra. Assente = usa `label`. */
    shortLabel?: string;
  }
  export const VOCI: readonly Voce[];
  export function voce(code: string): Voce | undefined;
  export function labelOf(code: string, role?: "autonoma" | "contestuale"): string;
  ```
  `labelOf` con `role` assente o `"autonoma"` restituisce `label`; con `"contestuale"` restituisce `shortLabel ?? label`. Per un codice sconosciuto restituisce il codice stesso (mai `undefined`: un'etichetta mancante non deve rendere una riga vuota).

- [ ] **Step 1: Scrivere i test strutturali**

`frontend/lib/ivcee-catalog.test.ts` (LF):

```ts
import { describe, expect, it } from "vitest";
import { VOCI, labelOf, voce } from "./ivcee-catalog";
import { ATTIVO_CODES, PASSIVO_CODES } from "./pratica-codes";

describe("catalogo IV-CEE", () => {
  it("ogni codice compare una volta sola", () => {
    const codes = VOCI.map((v) => v.code);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it("nessun padre punta a un codice inesistente", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const orfani = VOCI.filter((v) => v.parent !== null && !known.has(v.parent));
    expect(orfani.map((v) => v.code)).toEqual([]);
  });

  it("nessuna voce è padre di sé stessa", () => {
    expect(VOCI.filter((v) => v.parent === v.code).map((v) => v.code)).toEqual([]);
  });

  it("l'ordine è totale: nessun pari condivide indice sotto lo stesso padre", () => {
    const visti = new Set<string>();
    const collisioni: string[] = [];
    for (const v of VOCI) {
      const k = `${v.section}|${v.parent ?? "-"}|${v.order}`;
      if (visti.has(k)) collisioni.push(v.code);
      visti.add(k);
    }
    expect(collisioni).toEqual([]);
  });

  it("ogni voce ha un'etichetta autonoma non vuota e senza rientri", () => {
    const cattive = VOCI.filter((v) => v.label.trim() === "" || v.label !== v.label.trim());
    expect(cattive.map((v) => v.code)).toEqual([]);
  });

  it("l'etichetta contestuale, quando c'è, è diversa dall'autonoma", () => {
    const inutili = VOCI.filter((v) => v.shortLabel !== undefined && v.shortLabel === v.label);
    expect(inutili.map((v) => v.code)).toEqual([]);
  });

  it("copre ogni aggregato di primo livello dello stato patrimoniale", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const mancanti = [...ATTIVO_CODES, ...PASSIVO_CODES].filter((c) => !known.has(c));
    expect(mancanti).toEqual([]);
  });

  it("labelOf sceglie il ruolo giusto e non restituisce mai vuoto", () => {
    expect(labelOf("sp16d_debiti_fornitori_breve")).toBe("Debiti vs fornitori (entro)");
    expect(labelOf("sp16d_debiti_fornitori_breve", "contestuale")).toBe("entro 12 mesi");
    expect(labelOf("sp02_immob_immateriali")).toBe("I - Immobilizzazioni immateriali");
    expect(labelOf("codice_inventato")).toBe("codice_inventato");
  });

  it("voce() trova per codice", () => {
    expect(voce("sp09_disponibilita_liquide")?.section).toBe("attivo");
    expect(voce("codice_inventato")).toBeUndefined();
  });
});
```

- [ ] **Step 2: Eseguire i test e verificarne il fallimento**

Run: `npx vitest run lib/ivcee-catalog.test.ts`
Expected: FAIL — `Cannot find module './ivcee-catalog'`.

- [ ] **Step 3: Costruire il catalogo**

Crea `frontend/lib/ivcee-catalog.ts` (CRLF, come gli altri `lib/pratica-*.ts` — verifica con `file lib/pratica-codes.ts`).

**Non inventare i dati.** Ricavali dalle fonti attuali applicando la regola delle etichette dei Global Constraints:

- **quali codici e in che ordine:** `RETTIFICHE_BS_ATTIVO`, `RETTIFICHE_BS_PN`, `RETTIFICHE_BS_OTHER_PASSIVO`, `DEBT_GROUPS`, `CE_A`…`CE_IMPOSTE` in `lib/pratica-rettifiche-rules.ts` — sono l'elenco più completo dei sei, perché Rettifiche mostra tutto;
- **il padre:** `DETAIL_PARENTS` in `lib/pratica-codes.ts` mappa già ogni sotto-voce al suo aggregato. Le voci non presenti lì hanno `parent: null`;
- **la sezione:** `attivo` per i codici in `ATTIVO_CODES` e le loro sotto-voci; `patrimonio` per `sp11`/`sp12*`/`sp13`; `passivo` per il resto degli `sp`; `ce` per i `ce*`;
- **le etichette:** applica la regola di derivazione. `COUNTERPART_PICKER_LABELS` vince per i 14 sotto-conti dei debiti; altrimenti vince `relabel` (grafia del Confronto); `RETTIFICHE_LABELS` è l'ultima risorsa;
- **`shortLabel`:** valorizzata **solo** dove `relabel[code]` differisce dall'etichetta autonoma scelta. In pratica: i 14 sotto-conti dei debiti (`entro 12 mesi` / `oltre 12 mesi`). Se ne trovi altri, elencali nel report.

Le funzioni:

```ts
const BY_CODE = new Map(VOCI.map((v) => [v.code, v] as const));

export function voce(code: string): Voce | undefined {
  return BY_CODE.get(code);
}

export function labelOf(code: string, role: "autonoma" | "contestuale" = "autonoma"): string {
  const v = BY_CODE.get(code);
  if (!v) return code;
  return role === "contestuale" ? v.shortLabel ?? v.label : v.label;
}
```

- [ ] **Step 4: Scrivere il cross-check contro le fonti vecchie**

Questo test vive finché esistono le fonti vecchie, e muore con loro nel Task 9. Aggiungilo in coda a `frontend/lib/ivcee-catalog-parity.test.ts`:

```ts
import { VOCI, labelOf } from "./ivcee-catalog";
import { COUNTERPART_PICKER_LABELS, RETTIFICHE_LABELS } from "./pratica-rettifiche-rules";

describe("cross-check: il catalogo riproduce la regola delle etichette", () => {
  it("ogni codice etichettato dalle fonti vecchie esiste nel catalogo", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const mancanti = Object.keys(RETTIFICHE_LABELS).filter((c) => !known.has(c));
    expect(mancanti).toEqual([]);
  });

  it("i 14 sotto-conti dei debiti usano il testo del selettore come etichetta autonoma", () => {
    for (const [code, atteso] of Object.entries(COUNTERPART_PICKER_LABELS)) {
      expect(labelOf(code)).toBe(atteso);
    }
  });

  it("nessuna etichetta del catalogo conserva i rientri delle fonti vecchie", () => {
    const conRientro = VOCI.filter((v) => v.label.startsWith(" "));
    expect(conRientro.map((v) => v.code)).toEqual([]);
  });
});
```

- [ ] **Step 5: Eseguire i test e verificarne il successo**

Run: `npx tsc --noEmit && npm test`
Expected: tutti verdi. Se il cross-check fallisce su un codice, **il catalogo è sbagliato, non il test**: correggi il catalogo.

- [ ] **Step 6: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog.ts frontend/lib/ivcee-catalog.test.ts frontend/lib/ivcee-catalog-parity.test.ts
git commit -m "$(cat <<'EOF'
feat(ivcee): la tabella delle voci con le etichette a due ruoli

Un codice, un padre, una sezione, un ordine, e DUE etichette: autonoma
(giornale, selettore, dialoghi, Rettifiche) e contestuale (riga di tabella
sotto un'intestazione che la spiega). I 14 sotto-conti dei debiti sono
l'unico caso in cui servono entrambe, ed e' il caso che COUNTERPART_PICKER_LABELS
gia' trattava a parte.

Nessun consumatore ancora: il catalogo entra in servizio dal Task 4.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Le proiezioni

Le funzioni che le viste useranno. Ricavate da ciò che i sei consumatori chiedono davvero — nessun parametro "che servirà".

**Files:**
- Modify: `frontend/lib/ivcee-catalog.ts` (in coda)
- Modify: `frontend/lib/ivcee-catalog.test.ts` (in coda)

**Interfaces:**
- Consumes: `VOCI`, `Voce`, `voce`, `labelOf` dal Task 2.
- Produces:
  ```ts
  /** I figli diretti di un aggregato, in ordine. */
  export function childrenOf(code: string): Voce[];
  /** Il codice e tutta la sua discendenza, in ordine di resa. */
  export function subtree(code: string): Voce[];
  /** Somma i valori delle FOGLIE del sottoalbero; se non ha figli, il valore del codice. */
  export function aggregate(values: Record<string, number>, code: string): number;
  /** Le voci di una sezione, in ordine di resa, fino alla profondità indicata. */
  export function sectionRows(section: IvceeSection, maxDepth?: number): Voce[];
  ```
  `maxDepth` assente = tutte le profondità. `depth` di una voce = 0 se `parent === null`, altrimenti `depth(parent) + 1`.

- [ ] **Step 1: Scrivere i test**

In coda a `frontend/lib/ivcee-catalog.test.ts`:

```ts
import { aggregate, childrenOf, sectionRows, subtree } from "./ivcee-catalog";

describe("proiezioni", () => {
  it("childrenOf restituisce i figli diretti in ordine", () => {
    const figli = childrenOf("sp16_debiti_breve").map((v) => v.code);
    expect(figli).toEqual([
      "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
      "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
      "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
      "sp16g_altri_debiti_breve",
    ]);
  });

  it("childrenOf su una foglia restituisce l'elenco vuoto", () => {
    expect(childrenOf("sp09_disponibilita_liquide")).toEqual([]);
  });

  it("subtree include il codice stesso e la discendenza", () => {
    const t = subtree("sp16_debiti_breve").map((v) => v.code);
    expect(t[0]).toBe("sp16_debiti_breve");
    expect(t).toHaveLength(8);
  });

  it("aggregate somma le foglie, non il padre", () => {
    const values = {
      sp16_debiti_breve: 999,          // ignorato: il padre ha figli
      sp16a_debiti_banche_breve: 100,
      sp16d_debiti_fornitori_breve: 250,
    };
    expect(aggregate(values, "sp16_debiti_breve")).toBe(350);
  });

  it("aggregate su una foglia restituisce il suo valore", () => {
    expect(aggregate({ sp09_disponibilita_liquide: 42 }, "sp09_disponibilita_liquide")).toBe(42);
  });

  it("aggregate su valori assenti vale zero, non NaN", () => {
    expect(aggregate({}, "sp16_debiti_breve")).toBe(0);
  });

  it("sectionRows limita la profondità", () => {
    const primoLivello = sectionRows("passivo", 0).map((v) => v.code);
    expect(primoLivello).toContain("sp16_debiti_breve");
    expect(primoLivello).not.toContain("sp16a_debiti_banche_breve");

    const tutto = sectionRows("passivo").map((v) => v.code);
    expect(tutto).toContain("sp16a_debiti_banche_breve");
  });
});
```

- [ ] **Step 2: Eseguire i test e verificarne il fallimento**

Run: `npx vitest run lib/ivcee-catalog.test.ts`
Expected: FAIL — le quattro funzioni non esistono.

- [ ] **Step 3: Implementare le proiezioni**

In coda a `frontend/lib/ivcee-catalog.ts`:

```ts
const CHILDREN = new Map<string, Voce[]>();
for (const v of VOCI) {
  if (v.parent === null) continue;
  const list = CHILDREN.get(v.parent) ?? [];
  list.push(v);
  CHILDREN.set(v.parent, list);
}
for (const list of CHILDREN.values()) list.sort((a, b) => a.order - b.order);

export function childrenOf(code: string): Voce[] {
  return CHILDREN.get(code) ?? [];
}

export function subtree(code: string): Voce[] {
  const root = BY_CODE.get(code);
  if (!root) return [];
  const out: Voce[] = [root];
  for (const child of childrenOf(code)) out.push(...subtree(child.code));
  return out;
}

/**
 * Somma le FOGLIE del sottoalbero. Sommare anche i nodi intermedi
 * conterebbe due volte lo stesso importo: un aggregato È la somma dei figli.
 */
export function aggregate(values: Record<string, number>, code: string): number {
  const figli = childrenOf(code);
  if (figli.length === 0) return values[code] ?? 0;
  return figli.reduce((s, f) => s + aggregate(values, f.code), 0);
}

const depthOf = (v: Voce): number => {
  let d = 0;
  let cur = v;
  while (cur.parent !== null) {
    const p = BY_CODE.get(cur.parent);
    if (!p) break;
    cur = p;
    d += 1;
  }
  return d;
};

export function sectionRows(section: IvceeSection, maxDepth?: number): Voce[] {
  const roots = VOCI.filter((v) => v.section === section && v.parent === null)
    .sort((a, b) => a.order - b.order);
  const out: Voce[] = [];
  const walk = (v: Voce) => {
    if (maxDepth !== undefined && depthOf(v) > maxDepth) return;
    out.push(v);
    for (const c of childrenOf(v.code)) walk(c);
  };
  roots.forEach(walk);
  return out;
}
```

- [ ] **Step 4: Eseguire i test e verificarne il successo**

Run: `npx tsc --noEmit && npm test`
Expected: tutti verdi.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog.ts frontend/lib/ivcee-catalog.test.ts
git commit -m "$(cat <<'EOF'
feat(ivcee): proiezioni dell'albero (figli, sottoalbero, aggregato, sezione)

Le quattro funzioni che le viste chiedono davvero, ricavate dai consumatori
esistenti e non inventate in anticipo. aggregate() somma le FOGLIE: sommare
anche i nodi intermedi conterebbe due volte lo stesso importo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Adozione in `forecast/balance` e `report-appendices`

I due consumatori che già usano `BALANCE_STATEMENT_ROWS`: cambia solo da dove arriva.

**Files:**
- Modify: `frontend/lib/ivcee-catalog.ts` (aggiunge `BALANCE_STATEMENT_ROWS`)
- Modify: `frontend/app/forecast/balance/page.tsx:8`
- Modify: `frontend/components/report/report-appendices.tsx:13`
- Modify: `frontend/lib/ivcee-catalog-parity.test.ts`
- Delete: `frontend/lib/ivcee-balance-catalog.ts`

**Interfaces:**
- Consumes: `VOCI`, `labelOf`, `childrenOf`, `sectionRows` dai Task 2-3.
- Produces: `BALANCE_STATEMENT_ROWS: BalanceStatementRow[]`, `BalanceValues`, `BalanceStatementRow`, `balanceRowValue` — **gli stessi nomi e le stesse forme** che `ivcee-balance-catalog.ts` esporta oggi, così i due consumatori cambiano solo la riga di import.

- [ ] **Step 1: Spostare il tipo e la lista nel nuovo catalogo**

Copia in `frontend/lib/ivcee-catalog.ts` i tipi `BalanceValues`/`BalanceStatementRow`, gli helper `n`/`sum`, la lista `BALANCE_STATEMENT_ROWS` e `balanceRowValue` dall'attuale `lib/ivcee-balance-catalog.ts`, **senza modificarne il contenuto**.

Una sola sostituzione, alle righe 161-168 dell'originale: la catena di ternari che ricostruisce i nomi dei campi da un suffisso va rimpiazzata usando l'albero, che quei nomi già li contiene:

```ts
...(() => {
  const entroList = childrenOf("sp16_debiti_breve");
  const oltreList = childrenOf("sp17_debiti_lungo");
  if (entroList.length !== oltreList.length) {
    throw new Error(
      `catalogo incoerente: ${entroList.length} debiti entro vs ${oltreList.length} oltre`,
    );
  }
  return entroList.flatMap((entro, i) => {
    const oltre = oltreList[i];
    return [
      { label: labelOf(entro.code).replace(/ \(entro\)$/, ""),
        computed: (b: BalanceValues) => n(b, entro.code) + n(b, oltre.code), indent: true },
      { label: "  entro 12 mesi", field: entro.code, indent: true },
      { label: "  oltre 12 mesi", field: oltre.code, indent: true },
    ];
  });
})(),
```

L'accoppiamento entro/oltre per posizione regge perché i due gruppi hanno gli stessi sette tipi di creditore nello stesso ordine — condizione che il Task 2 ha già fissato con il test sull'ordine totale. **Se `childrenOf("sp16_debiti_breve").length !== childrenOf("sp17_debiti_lungo").length`, fermati e segnalalo**: significa che il catalogo è incompleto.

- [ ] **Step 2: Aggiornare i due import**

`frontend/app/forecast/balance/page.tsx:8` e `frontend/components/report/report-appendices.tsx:13`:

```ts
import { BALANCE_STATEMENT_ROWS } from "@/lib/ivcee-catalog";
```

Verifica con `grep -rn "ivcee-balance-catalog" app components lib` che non resti alcun riferimento, poi elimina `frontend/lib/ivcee-balance-catalog.ts`.

- [ ] **Step 3: Puntare l'invariante al nuovo modulo**

In `frontend/lib/ivcee-catalog-parity.test.ts`, cambia l'import di `BALANCE_STATEMENT_ROWS` da `@/lib/ivcee-balance-catalog` a `@/lib/ivcee-catalog`. **Non toccare `ATTESI_BALANCE`**: è esattamente il test.

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: tutti verdi, `ATTESI_BALANCE` compreso. Se quel test fallisce, la sostituzione dei ternari ha cambiato una riga: correggi finché torna identico.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog.ts frontend/lib/ivcee-catalog-parity.test.ts frontend/app/forecast/balance/page.tsx frontend/components/report/report-appendices.tsx
git rm frontend/lib/ivcee-balance-catalog.ts
git commit -m "$(cat <<'EOF'
refactor(ivcee): forecast/balance e report-appendices leggono dal catalogo unico

Il vecchio ivcee-balance-catalog.ts viene assorbito. Unica modifica al
contenuto: la catena di ternari che ricostruiva i nomi dei campi da un
suffisso ora li prende dall'albero, che gia' li contiene. L'invariante
sull'elenco righe resta verde.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Adozione in `forecast/income`

**Files:**
- Modify: `frontend/lib/ivcee-catalog.ts` (aggiunge `INCOME_STATEMENT_ROWS`)
- Modify: `frontend/app/forecast/income/page.tsx` (rimuove l'elenco inline a ~riga 558)
- Modify: `frontend/lib/ivcee-catalog-parity.test.ts`

**Interfaces:**
- Consumes: `BalanceValues`, `BalanceStatementRow`, `labelOf` dal Task 4.
- Produces: `INCOME_STATEMENT_ROWS: BalanceStatementRow[]` — stessa forma della lista SP, così i due prospetti si rendono con lo stesso codice.

- [ ] **Step 1: Estrarre l'elenco inline**

In `frontend/app/forecast/income/page.tsx`, l'array assegnato a `const rows` dentro `IncomeStatementTable` (intorno a riga 558) ha già la forma `{ label, field?, isTotal?, isSubtotal?, indent? }`. Spostalo **verbatim** in `frontend/lib/ivcee-catalog.ts` come `export const INCOME_STATEMENT_ROWS: BalanceStatementRow[]`, adattando solo `indent: 1` in `indent: true` se il tipo lo richiede — e se lo fa, annota nel report ogni riga toccata.

Nel componente, sostituisci l'array con l'import e l'uso.

- [ ] **Step 2: Estendere l'invariante alla nuova lista**

In `frontend/lib/ivcee-catalog-parity.test.ts`, aggiungi `INCOME_STATEMENT_ROWS` all'import esistente da `@/lib/ivcee-catalog`, poi la costante generata e l'asserzione. Genera la costante come nel Task 1: aggiungi temporaneamente un `console.log(JSON.stringify(INCOME_STATEMENT_ROWS.map(rowKey)))`, esegui, incolla, rimuovi la stampa.

```ts
const ATTESI_INCOME: string[] = [ /* incolla qui */ ];

it("prospetto CE (forecast/income)", () => {
  expect(INCOME_STATEMENT_ROWS.map(rowKey)).toEqual(ATTESI_INCOME);
});
```

Attenzione all'ordine dei passi: la costante va generata **dopo** lo spostamento verbatim e **prima** di qualunque altra modifica alla lista, altrimenti fotografa uno stato già alterato.

- [ ] **Step 3: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: tutti verdi.

- [ ] **Step 4: Verificare a occhio la pagina**

I server girano già. Apri `http://localhost:3000/forecast/income` su uno scenario esistente e confronta il prospetto con quello che vedi ora: stesse righe, stesso ordine, stesse etichette. Se non hai uno scenario a portata, dillo nel report invece di dichiarare la verifica fatta.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog.ts frontend/lib/ivcee-catalog-parity.test.ts frontend/app/forecast/income/page.tsx
git commit -m "$(cat <<'EOF'
refactor(ivcee): il prospetto CE esce dal componente ed entra nel catalogo

L'elenco righe di forecast/income era gia' scritto nella forma esatta del
catalogo: gli mancava solo di essere importabile. Ora e' osservabile,
quindi coperto dall'invariante come gli altri.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Adozione in `report-composition`

**Files:**
- Modify: `frontend/components/report/report-composition.tsx:47-51`
- Modify: `frontend/lib/ivcee-catalog-parity.test.ts`

**Interfaces:**
- Consumes: `aggregate` dal Task 3.
- Produces: niente.

- [ ] **Step 1: Fissare i valori attuali prima di toccarli**

`report-composition.tsx` somma a mano quattro aggregati (righe 47-51): `immob`, `rimanenze`, `crediti`, `liquidita`. Prima di cambiarli, aggiungi in `frontend/lib/ivcee-catalog-parity.test.ts` un test che fissa la stessa aritmetica su una fixture, così la sostituzione è verificabile:

```ts
import { aggregate } from "./ivcee-catalog";

describe("report-composition: le aggregazioni non cambiano valore", () => {
  const BS: Record<string, number> = {
    sp01_crediti_soci: 10, sp02_immob_immateriali: 100, sp03_immob_materiali: 200,
    sp04_immob_finanziarie: 50, sp05_rimanenze: 300,
    sp06_crediti_breve: 400, sp07_crediti_lungo: 60,
    sp08_attivita_finanziarie: 20, sp09_disponibilita_liquide: 80,
  };

  it("immobilizzazioni", () => {
    const aMano = BS.sp02_immob_immateriali + BS.sp03_immob_materiali
      + BS.sp04_immob_finanziarie + BS.sp01_crediti_soci;
    expect(aMano).toBe(360);
    expect(aggregate(BS, "sp02_immob_immateriali")
      + aggregate(BS, "sp03_immob_materiali")
      + aggregate(BS, "sp04_immob_finanziarie")
      + aggregate(BS, "sp01_crediti_soci")).toBe(aMano);
  });

  it("crediti", () => {
    const aMano = BS.sp06_crediti_breve + BS.sp07_crediti_lungo;
    expect(aggregate(BS, "sp06_crediti_breve") + aggregate(BS, "sp07_crediti_lungo")).toBe(aMano);
  });

  it("liquidità", () => {
    const aMano = BS.sp09_disponibilita_liquide + BS.sp08_attivita_finanziarie;
    expect(aggregate(BS, "sp09_disponibilita_liquide")
      + aggregate(BS, "sp08_attivita_finanziarie")).toBe(aMano);
  });
});
```

Nota bene: `aggregate` somma le foglie. Con una fixture che valorizza **solo gli aggregati** e non le sotto-voci, `aggregate(BS, "sp06_crediti_breve")` restituirebbe **0**, non 400, perché `sp06` ha figli nel catalogo. Se il test lo mostra, è un'informazione vera e importante: significa che `report-composition` non può usare `aggregate` sui dati che riceve (che sono aggregati, non dettagli). **In quel caso non forzare la sostituzione**: lascia `report-composition` com'è, annota il perché nel report, e salta al Task 7. Un aggregatore che restituisce zero su dati reali è peggio della somma a mano che sostituisce.

- [ ] **Step 2: Eseguire il test e decidere**

Run: `npx vitest run lib/ivcee-catalog-parity.test.ts`
Expected: o passa (e si procede alla sostituzione), o mostra lo zero descritto sopra (e si documenta la rinuncia).

- [ ] **Step 3: Se il test passa, sostituire le somme a mano**

In `frontend/components/report/report-composition.tsx`, sostituisci le quattro somme letterali con le chiamate ad `aggregate`, lasciando invariato tutto il resto del componente.

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: tutti verdi.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/ivcee-catalog-parity.test.ts frontend/components/report/report-composition.tsx
git commit -m "$(cat <<'EOF'
refactor(ivcee): report-composition non somma piu' i codici a mano

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

Se lo Step 2 ha mostrato la rinuncia, committa il solo file di test con un messaggio che la documenta.

---

### Task 7: Adozione in `pratica-statement-rows`

Le mappe `relabel` (89 voci fra le due) diventano una chiamata al catalogo. Confronto, Proiezione e Stampa consumano tutte questo modulo.

**Files:**
- Modify: `frontend/lib/pratica-statement-rows.ts:52` e `:341`

**Interfaces:**
- Consumes: `labelOf` dal Task 2.
- Produces: niente di nuovo — `buildBalanceItemsWithTotals` e `buildIncomeItemsWithEbitda` mantengono firma e comportamento.

- [ ] **Step 1: Sostituire le due mappe**

In entrambi i punti, la forma attuale è:

```ts
const relabel: Record<string, string> = { /* ~45 voci */ };
...
return { ...orig, label: relabel[code] ?? orig.label };
```

Sostituiscila con:

```ts
// Etichetta CONTESTUALE: qui le righe stanno in un prospetto, sotto
// l'intestazione del proprio aggregato, quindi la forma breve basta.
// L'etichetta autonoma serve altrove (giornale rettifiche, selettore).
return { ...orig, label: labelOf(code, "contestuale") };
```

Attenzione a due cose:
1. Il `?? orig.label` sparisce perché `labelOf` non restituisce mai vuoto — su un codice sconosciuto restituisce il codice stesso. **Questo cambia il comportamento** per i codici che il server invia e il catalogo non conosce: prima si vedeva l'etichetta del server, ora il codice. Verifica con l'invariante che non accada per nessun codice reale; se accade, il codice va **aggiunto al catalogo**, non ripristinato il fallback.
2. Le etichette del catalogo sono senza rientri, mentre `relabel` li incorporava (`"  1) Verso clienti"`). Se le righe di dettaglio perdono il rientro visivo, applicalo dove si rende, non rimettendolo nel dato.

- [ ] **Step 2: Verificare l'invariante e i rientri**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: `ATTESI_CONFRONTO_BS` e `ATTESI_CONFRONTO_CE` verdi (i **codici** non cambiano; le etichette non sono in quel test).

- [ ] **Step 3: Verificare a occhio le tre viste**

I server girano già. Su una pratica esistente controlla Confronto, Proiezione e Stampa: stesse righe, stesso ordine, etichette invariate rispetto a prima (queste tre viste già usavano la grafia vincente). Se una riga di dettaglio ha perso il rientro, sistemalo nella resa.

- [ ] **Step 4: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/pratica-statement-rows.ts
git commit -m "$(cat <<'EOF'
refactor(ivcee): Confronto/Proiezione/Stampa prendono le etichette dal catalogo

Le due mappe relabel (89 voci) diventano labelOf(code, "contestuale"): qui
le righe stanno sotto l'intestazione del proprio aggregato, quindi la forma
breve e' quella giusta.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Adozione in `RettificheTab` — l'unico cambiamento visibile

**Files:**
- Modify: `frontend/components/pratica/RettificheTab.tsx` (righe ~249, ~252, ~312-313, ~487, ~743, ~745)
- Modify: `frontend/lib/pratica-rettifiche-rules.ts:328-335`

**Interfaces:**
- Consumes: `labelOf` dal Task 2; `ATTIVO_CODES` da `@/lib/pratica-codes`.
- Produces: niente.

- [ ] **Step 1: Sostituire le letture di `RETTIFICHE_LABELS`**

Tre punti in `RettificheTab.tsx`, tutti con il ruolo **autonomo** — sono righe di giornale e dialoghi, senza intestazione sopra:

```ts
// riga ~249
editedLabel: labelOf(field),
// riga ~252
counterpartLabel: labelOf(counterpartField),
// righe ~312-313
{ field: "sp09_disponibilita_liquide", label: labelOf("sp09_disponibilita_liquide"), side: "attivo" },
{ field: "sp16g_altri_debiti_breve", label: labelOf("sp16g_altri_debiti_breve"), side: "passivo" },
```

E in `lib/pratica-rettifiche-rules.ts:328-335`, il selettore della contropartita: `COUNTERPART_PICKER_LABELS[field] ?? RETTIFICHE_LABELS[field].trim()` diventa `labelOf(field)` — che restituisce già il testo del selettore per i 14 sotto-conti dei debiti, perché il Task 2 lo ha reso l'etichetta autonoma. **`COUNTERPART_PICKER_LABELS` diventa così inutilizzata**; non eliminarla qui, lo fa il Task 9.

- [ ] **Step 2: Dare alle sotto-righe dei debiti l'etichetta autonoma**

È il cambiamento che l'utente ha approvato. Righe ~743 e ~745:

```tsx
{debtRow(labelOf(group.entro[0]), group.label + "_entro", refEntro, origEntro, corrEntro, true,
  isSingleEntro ? group.entro[0] : undefined)}
{debtRow(labelOf(group.oltre[0]), group.label + "_oltre", refOltre, origOltre, corrOltre, true,
  isSingleOltre ? group.oltre[0] : undefined)}
```

Le stringhe fisse `"entro 12 mesi"` / `"oltre 12 mesi"` spariscono: chi registra deve leggere quale debito sta toccando. Ogni `group.entro` e `group.oltre` ha un solo elemento (vedi `DEBT_GROUPS`), quindi `[0]` è sicuro — **verificalo** con un'asserzione a inizio task e segnala se non regge.

- [ ] **Step 3: Eliminare la terza copia dell'elenco attivo**

`ATTIVO_TOTAL_FIELDS`, dichiarata localmente a riga ~487, ha contenuto **identico** ad `ATTIVO_CODES` esportata da `@/lib/pratica-codes`. Eliminala e importa quella, aggiornando l'uso a riga ~493. Verifica con `grep -n "ATTIVO_TOTAL_FIELDS" components/pratica/RettificheTab.tsx` che non restino altri usi; se ne trovi a righe precedenti (esiste un riferimento intorno a riga 342), assicurati che puntino alla costante importata.

- [ ] **Step 4: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: tutti verdi. `ATTESI_RETTIFICHE` deve restare verde: **i codici non cambiano**, cambiano solo le etichette.

- [ ] **Step 5: Verificare a occhio, con attenzione**

Questo è l'unico task che cambia ciò che l'utente legge. Sui server già avviati, apri una pratica e la scheda Rettifiche:

- le voci non-debito mostrano la grafia del Confronto (`I - Immobilizzazioni immateriali`, non `B.I) Immobilizzazioni immateriali`);
- le sotto-righe dei debiti mostrano `Debiti vs fornitori (entro)`, non `entro 12 mesi`;
- **tutte** le sotto-righe dei debiti restano visibili anche a zero (era già così: `RettificheTab.tsx:738` calcola `entroNonZero`/`oltreNonZero` e li scarta di proposito);
- registra una rettifica e controlla che la riga di giornale nomini la voce per esteso;
- apri il selettore della contropartita e controlla che le voci siano leggibili.

Riporta cosa hai visto, non cosa ti aspettavi.

- [ ] **Step 6: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/components/pratica/RettificheTab.tsx frontend/lib/pratica-rettifiche-rules.ts
git commit -m "$(cat <<'EOF'
refactor(ivcee): Rettifiche prende le etichette dal catalogo

Unico cambiamento visibile del lavoro: 38 etichette nella scheda Rettifiche.
Le 24 non-debito adottano la grafia del Confronto (gia' in uso in cinque
viste su sei); le 14 sotto-righe dei debiti passano da "entro 12 mesi" a
"Debiti vs fornitori (entro)" — chi registra deve leggere cosa tocca, e la
forma breve funziona solo sotto un'intestazione che la spiega.

Rimossa anche ATTIVO_TOTAL_FIELDS, terza copia byte-identica di ATTIVO_CODES.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Rimozione delle fonti morte e documentazione

**Files:**
- Modify: `frontend/lib/pratica-rettifiche-rules.ts`
- Modify: `frontend/lib/ivcee-catalog-parity.test.ts`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: niente.
- Produces: niente.

- [ ] **Step 1: Provare che le fonti sono morte, poi eliminarle**

Per ciascuna, esegui il grep e cancella **solo** se l'unica occorrenza è la dichiarazione:

```bash
cd /home/peter/DEV/budget/frontend
grep -rn "RETTIFICHE_LABELS" app components lib
grep -rn "COUNTERPART_PICKER_LABELS" app components lib
```

Se un grep trova un uso reale, **non cancellare**: annotalo nel report. Ricorda che `RETTIFICHE_LABELS` è usata anche a `lib/pratica-rettifiche-rules.ts:328` per costruire `COUNTERPART_OPTIONS` — quella riga è stata cambiata nel Task 8, quindi verifica che la nuova versione non la usi più.

- [ ] **Step 2: Rimuovere il cross-check che dipende dalle fonti morte**

Il `describe("cross-check: il catalogo riproduce la regola delle etichette", …)` aggiunto nel Task 2 importa `RETTIFICHE_LABELS` e `COUNTERPART_PICKER_LABELS`. Aveva un solo scopo — garantire che il catalogo riproducesse fedelmente le fonti durante la transizione — e muore con loro. Eliminalo insieme ai suoi import.

**Non eliminare** gli altri `describe` del file: l'invariante sulle viste resta, ed è quello che protegge il lavoro d'ora in poi.

- [ ] **Step 3: Verificare**

Run: `npx tsc --noEmit && npm test && npm run build`
Expected: tutti verdi.

- [ ] **Step 4: Aggiornare `CLAUDE.md`**

Nella sezione **Shared BS/IS Layout (Rettifiche, Confronto, /forecast/balance, /forecast/income)**, l'elenco che oggi impone di aggiungere una riga in quattro file va sostituito con la procedura reale:

> **Catalogo IV-CEE unico (2026-08-10).** Le righe dei prospetti SP/CE vivono in
> `frontend/lib/ivcee-catalog.ts`. Per aggiungere una sotto-voce si tocca **quel file e
> basta**: le sei viste la ricevono per costruzione. Ogni voce porta il codice, il padre,
> la sezione, l'ordine e **due etichette**: `label` (autonoma, auto-esplicativa — giornale
> rettifiche, selettore contropartita, dialoghi, e ogni riga di Rettifiche) e `shortLabel`
> (contestuale, breve — righe di tabella che stanno sotto l'intestazione del proprio
> aggregato). `labelOf(code, "contestuale")` cade sull'autonoma quando la breve non c'è.
> Le viste proiettano l'albero con `sectionRows`, `childrenOf`, `subtree` e `aggregate`;
> le regole di **resa** (filtro degli zeri, editabilità, totali, rientri) restano di
> ciascuna vista.
>
> `frontend/lib/ivcee-catalog-parity.test.ts` fissa, per ogni vista, l'elenco dei codici
> resi e il loro ordine. Se cambia, una vista ha perso o riordinato una riga: quegli
> elenchi non vanno aggiornati per far passare il test.

Aggiorna inoltre la sezione **Rettifiche** con il cambiamento visibile: le sotto-righe dei debiti mostrano ora l'etichetta autonoma (`Debiti vs fornitori (entro)`) invece di `entro 12 mesi`, perché la forma breve funziona solo sotto un'intestazione che la spieghi, e il giornale non ne ha.

- [ ] **Step 5: Commit**

```bash
cd /home/peter/DEV/budget
git diff --stat
git add frontend/lib/pratica-rettifiche-rules.ts frontend/lib/ivcee-catalog-parity.test.ts CLAUDE.md
git commit -m "$(cat <<'EOF'
chore(ivcee): rimuove le mappe etichette morte e aggiorna CLAUDE.md

RETTIFICHE_LABELS e COUNTERPART_PICKER_LABELS non hanno piu' consumatori: la
seconda esisteva solo come toppa al problema dei ruoli, che ora e' esplicito
nel catalogo. Cade anche il cross-check di transizione, che serviva a
garantire la fedelta' del catalogo alle fonti mentre esistevano entrambi.

CLAUDE.md: "aggiungere una voce" passa da quattro file a uno.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Verifica finale (a carico del controller)

- [ ] `npx tsc --noEmit` → 0 errori
- [ ] `npm test` → tutte le suite verdi
- [ ] `npm run build` → completata
- [ ] `grep -rn "ivcee-balance-catalog\|RETTIFICHE_LABELS\|COUNTERPART_PICKER_LABELS" frontend/app frontend/components frontend/lib` → nessun risultato
- [ ] Giro browser su `http://localhost:3000` (server già avviati dall'utente), su una pratica reale:
  - Rettifiche: grafia del Confronto sulle voci non-debito, etichette per esteso sulle sotto-righe dei debiti, sotto-righe visibili anche a zero, giornale leggibile dopo una rettifica
  - Confronto, Proiezione, Stampa: righe, ordine ed etichette invariati
  - `/forecast/balance` e `/forecast/income`: prospetti invariati
  - `/report`: appendici e composizione invariate
