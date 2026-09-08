import { describe, expect, it } from "vitest";
import {
  ingressoNuovaPratica,
  ingressoRiprendi,
  rifiutoIngressoStartup,
  type IngressoPratica,
} from "@/lib/pratica-ingresso";
import type { ScenarioSummary } from "@/types/api";

/**
 * I TRE soli ingressi al percorso, e l'unica cosa che li accomuna: l'azienda
 * e' gia' decisa. Il duplicato che il tester ha creato nasceva da un ingresso
 * con `companyId: null` — Anagrafiche in quel ramo e' un form di sola
 * creazione, quindi chi ci arrivava dopo aver premuto «Nuova pratica»
 * riscriveva il nome dell'azienda su cui voleva lavorare e ne nasceva una
 * seconda.
 *
 * Qui il caso e' impossibile per TIPO, non per guardia: `companyId` e'
 * `number`, e non esiste una firma che accetti `null`. Una guardia a valle
 * avrebbe presidiato l'effetto lasciando in piedi la causa.
 */

function scenario(over: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: 7,
    name: "Infrannuale 9M",
    scenario_type: "infrannuale",
    base_year: 2024,
    period_months: 9,
    is_active: 1,
    has_forecast: true,
    created_at: null,
    ...over,
  };
}

describe("ingressoNuovaPratica", () => {
  it("«Da bilancio» apre il percorso pratica sullo step Anagrafiche", () => {
    const i: IngressoPratica = ingressoNuovaPratica(42, "bilancio");
    expect(i.route).toBe("/pratica");
    expect(i.startupMode).toBe(false);
    expect(i.pratica.workflow).toBe("bilancio");
    expect(i.pratica.analysisStep).toBe("anagrafiche");
    expect(i.pratica.companyId).toBe(42);
  });

  it("«Startup» apre il workflow startup su /budget", () => {
    const i = ingressoNuovaPratica(42, "startup");
    expect(i.route).toBe("/budget");
    expect(i.startupMode).toBe(true);
    expect(i.pratica.workflow).toBe("startup");
    expect(i.pratica.companyId).toBe(42);
  });

  it("l'azienda della riga resta quella, in entrambi i tipi", () => {
    // «Nuova azienda» in testata e «Nuova pratica» sotto una riga chiamano
    // questa stessa funzione: e' il punto in cui prima cambiava solo il
    // `companyId`, `null` nel primo caso e l'id nel secondo.
    for (const workflow of ["bilancio", "startup"] as const) {
      expect(ingressoNuovaPratica(3, workflow).pratica.companyId).toBe(3);
      expect(ingressoNuovaPratica(99, workflow).pratica.companyId).toBe(99);
    }
  });

  it("una pratica nuova non porta con se' nessuno scenario", () => {
    // Se un id di scenario sopravvivesse qui, «Nuova pratica» riaprirebbe la
    // pratica precedente invece di crearne una.
    const i = ingressoNuovaPratica(42, "bilancio");
    expect(i.pratica.infrannualeScenarioId ?? null).toBeNull();
    expect(i.pratica.budgetScenarioId ?? null).toBeNull();
  });
});

describe("ingressoRiprendi", () => {
  it("uno scenario infrannuale riapre /pratica sulle Rettifiche", () => {
    const i = ingressoRiprendi(42, scenario());
    expect(i.route).toBe("/pratica");
    expect(i.pratica.analysisStep).toBe("rettifiche");
    // L'infrannuale proietta l'anno SUCCESSIVO a quello di riferimento.
    expect(i.pratica.fiscalYear).toBe(2025);
    expect(i.pratica.periodMonths).toBe(9);
    expect(i.pratica.infrannualeScenarioId).toBe(7);
    expect(i.pratica.budgetScenarioId).toBeNull();
    expect(i.startupMode).toBe(false);
  });

  it("uno scenario budget legacy riapre /budget", () => {
    // Senza `infrannualeScenarioId` non c'e' una fase ANALISI ricostruibile:
    // lo stepper la nasconde del tutto invece di mostrarla abilitata-ma-rotta.
    const i = ingressoRiprendi(42, scenario({ scenario_type: "budget", period_months: null }));
    expect(i.route).toBe("/budget");
    expect(i.pratica.analysisStep).toBe("anagrafiche");
    expect(i.pratica.fiscalYear).toBe(2024);
    expect(i.pratica.periodMonths).toBe(12);
    expect(i.pratica.infrannualeScenarioId).toBeNull();
    expect(i.pratica.budgetScenarioId).toBe(7);
  });

  it("un infrannuale senza `period_months` vale un anno intero", () => {
    const i = ingressoRiprendi(42, scenario({ period_months: null }));
    expect(i.pratica.periodMonths).toBe(12);
  });
});

/**
 * #37 — l'ingresso Startup su un'azienda che ha gia' uno storico.
 *
 * Il wizard del business plan sta dietro un cancello che chiede ZERO anni
 * (`app/budget/page.tsx`), quindi su un'azienda con `FinancialYear` la pagina
 * cadeva sull'elenco scenari ordinario, intestato «Previsionale Startup» e
 * muto: nessuna schermata per capitale, periodo e driver, e nessuna spiegazione.
 *
 * Il rifiuto arriva PRIMA di navigare, non dopo: il percorso Startup semina un
 * bilancio di apertura sull'anno precedente al piano, e su un'azienda con
 * storico quell'anno esiste gia' — quel che se ne ricavava era un 400 che non
 * diceva nemmeno quale fosse il problema.
 */
describe("rifiutoIngressoStartup", () => {
  it("un'azienda senza anni non viene rifiutata: il percorso resta identico", () => {
    expect(rifiutoIngressoStartup([])).toBeNull();
  });

  it("un'azienda con storico viene rifiutata, e il motivo nomina gli anni", () => {
    const motivo = rifiutoIngressoStartup([2024, 2023, 2026]);
    expect(motivo).not.toBeNull();
    expect(motivo).toContain("2023");
    expect(motivo).toContain("2024");
    expect(motivo).toContain("2026");
    // Ordinati: l'elenco si legge, non si indovina.
    expect(motivo!.indexOf("2023")).toBeLessThan(motivo!.indexOf("2026"));
  });

  it("un solo anno basta a rifiutare, e il messaggio dice dove andare", () => {
    const motivo = rifiutoIngressoStartup([2025]);
    expect(motivo).toContain("2025");
    expect(motivo).toContain("Da bilancio");
  });

  it("non muta l'elenco che riceve", () => {
    const anni = [2026, 2024];
    rifiutoIngressoStartup(anni);
    expect(anni).toEqual([2026, 2024]);
  });
});
