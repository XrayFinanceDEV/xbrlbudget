import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
// `report-types.ts` è un modulo di soli dati (nessun React, nessun import):
// leggerlo da qui non introduce dipendenze verso l'alto. Il test vive in
// `lib/` perché è lì che `vitest.config.ts` cerca (`include: lib/**/*.test.ts`).
import { REPORT_SECTIONS } from "@/components/report/report-types";

/**
 * Il sommario del report è generato da `REPORT_SECTIONS` (`report-toc.tsx` la
 * itera) mentre l'ordine dei blocchi è scritto a mano in `app/report/page.tsx`.
 * Sono due elenchi che devono dire la stessa cosa, e nulla lo verifica a
 * runtime: spostare un blocco senza spostare la voce fa puntare il sommario a
 * pagine sbagliate, e non produce alcun errore.
 *
 * L'altra metà è l'ANCORAGGIO: ogni voce del sommario cerca
 * `document.getElementById(section.id)`, quindi un id che nessun `<section>`
 * dichiara è un bottone che non scorre da nessuna parte. È già successo — la
 * voce «Appendici» aveva id `appendices` mentre la pagina rendeva
 * `appendices-bs` e `appendices-is`.
 */

const RADICE = join(__dirname, "..");
const PAGINA = readFileSync(join(RADICE, "app", "report", "page.tsx"), "utf-8");

/** Da quale componente (e quale `section=`) viene ciascun id del sommario. */
const RESA: Record<string, { componente: string; section?: string }> = {
  cover: { componente: "ReportCover" },
  "appendices-bs": { componente: "ReportAppendices", section: "bs" },
  "appendices-is": { componente: "ReportAppendices", section: "is" },
  cashflow: { componente: "ReportCashflow" },
  dashboard: { componente: "ReportDashboard" },
  composition: { componente: "ReportComposition" },
  "income-margins": { componente: "ReportIncomeMargins" },
  structural: { componente: "ReportStructural" },
  ratios: { componente: "ReportRatios" },
  scoring: { componente: "ReportScoring" },
  "break-even": { componente: "ReportBreakEven" },
  notes: { componente: "ReportNotes" },
};

/** L'ordine in cui la pagina rende i blocchi, letto dal sorgente. */
function ordineDellaPagina(): string[] {
  const perIndice = Object.entries(RESA).map(([id, { componente, section }]) => {
    const re = section
      ? new RegExp(`<${componente}\\b[^>]*section="${section}"`)
      : new RegExp(`<${componente}\\b`);
    return { id, indice: PAGINA.search(re) };
  });
  expect(perIndice.filter((x) => x.indice < 0)).toEqual([]);
  return perIndice.sort((a, b) => a.indice - b.indice).map((x) => x.id);
}

describe("ordine del report", () => {
  it("la pagina rende i blocchi nell'ordine del sommario", () => {
    expect(ordineDellaPagina()).toEqual(REPORT_SECTIONS.map((s) => s.id));
  });

  it("i prospetti completi e il rendiconto seguono la copertina", () => {
    expect(REPORT_SECTIONS.slice(0, 4).map((s) => s.id)).toEqual([
      "cover",
      "appendices-bs",
      "appendices-is",
      "cashflow",
    ]);
  });

  it("le due appendici sono due voci distinte del sommario", () => {
    const ids = REPORT_SECTIONS.map((s) => s.id);
    expect(ids).toContain("appendices-bs");
    expect(ids).toContain("appendices-is");
    // l'id unico di prima non esisteva in nessun `<section>`
    expect(ids).not.toContain("appendices");
  });

  it("le note restano l'ultima sezione", () => {
    expect(REPORT_SECTIONS[REPORT_SECTIONS.length - 1].id).toBe("notes");
  });

  // Ogni voce del sommario deve trovare un elemento con quell'id, altrimenti
  // `scrollTo` non scorre e l'IntersectionObserver non la evidenzia mai.
  it("ogni voce del sommario ha un ancoraggio che esiste davvero", () => {
    const dir = join(RADICE, "components", "report");
    const sorgenti = readdirSync(dir)
      .filter((f) => f.endsWith(".tsx"))
      .map((f) => readFileSync(join(dir, f), "utf-8"))
      .join("\n");

    for (const s of REPORT_SECTIONS) {
      const letterale = new RegExp(`<section id="${s.id}"`);
      // `report-appendices.tsx` costruisce l'id: `appendices-${section}`
      const costruito =
        s.id.startsWith("appendices-") &&
        /<section id=\{section \? `appendices-\$\{section\}`/.test(sorgenti);
      expect(
        letterale.test(sorgenti) || costruito,
        `nessun <section> dichiara l'id "${s.id}"`,
      ).toBe(true);
    }
  });

  // Salti pagina forzati, coerenti col nuovo ordine: i tre prospetti aprono
  // ciascuno una pagina, e le note pure.
  it("i tre prospetti in testa hanno un salto pagina ciascuno", () => {
    const blocchi = PAGINA.split("<div className=");
    const conSalto = blocchi.filter((b) => b.includes("print:break-before-page"));
    for (const componente of ["ReportAppendices", "ReportCashflow", "ReportNotes"]) {
      expect(
        conSalto.some((b) => b.includes(`<${componente}`)),
        `${componente} non apre una pagina nuova`,
      ).toBe(true);
    }
    // entrambe le appendici, non solo la prima
    expect(
      conSalto.filter((b) => b.includes("<ReportAppendices")).length,
    ).toBe(2);
  });
});
