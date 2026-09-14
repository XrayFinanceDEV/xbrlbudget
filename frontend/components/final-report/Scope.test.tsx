import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../../tests/fixtures/final_report/startup.json";
import type { FinalReportModel } from "@/types/final-report";
import { ReportScope } from "./Scope";

const render = (report: FinalReportModel): string =>
  renderToStaticMarkup(
    <ReportScope
      company={report.company}
      practice={report.practice}
      generated_at={report.generated_at}
      readiness={report.readiness}
    />,
  );

const INFRANNUALE = infrannuale as unknown as FinalReportModel;
const BILANCIO = bilancio as unknown as FinalReportModel;
const STARTUP = startup as unknown as FinalReportModel;

describe("ReportScope (copertina e perimetro)", () => {
  it("infrannuale: scenario sorgente, periodo parziale e anno di chiusura compaiono", () => {
    const html = render(INFRANNUALE);
    expect(html).toContain("Percorso infrannuale");
    expect(html).toContain("Scenario sorgente");
    expect(html).toContain("Infrannuale settembre");
    expect(html).toContain("9 mesi su 12");
    expect(html).toContain("Anno di chiusura attesa");
    expect(html).toContain("2026");
    expect(html).toContain("Documento: Bozza");
    expect(html).toContain("Budget 2027-2029");
    expect(html).toContain("2027, 2028, 2029");
  });

  it("bilancio: nessun scenario sorgente, storico dichiarato, nessuna chiusura infrannuale", () => {
    const html = render(BILANCIO);
    expect(html).toContain("Percorso da bilancio");
    expect(html).not.toContain("Scenario sorgente");
    expect(html).toContain("Anno storico di riferimento");
    expect(html).toContain("2026");
    expect(html).not.toContain("Anno di chiusura attesa");
    expect(html).toContain("Documento: Definitivo");
    // tax_id null: assenza dichiarata, non campo saltato.
    expect(html).toContain("codice fiscale non dichiarato");
  });

  it("startup: assenza dello storico detta con parole sue, stato bloccato leggibile", () => {
    const html = render(STARTUP);
    expect(html).toContain("Percorso startup");
    expect(html).not.toContain("Scenario sorgente");
    expect(html).toContain("Nessuno storico: il piano parte dai saldi di apertura");
    expect(html).toContain("Documento: Bloccato");
    expect(html).toContain("IT003");
  });

  it("il documento generato porta data e ora col marcatore di fuso del modello", () => {
    const html = render(INFRANNUALE);
    expect(html).toMatch(/generato il \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}(Z|[+-]\d{2}:\d{2})/);
  });

  it("tabella semantica: caption, intestazioni di colonna e riga", () => {
    const html = render(INFRANNUALE);
    expect(html).toContain("<caption");
    expect(html).toContain("Perimetro del documento");
    // Ogni etichetta di riga è un th scope="row": mai celle di sola resa visiva.
    expect(html).toContain('<th scope="row"');
    expect(html).toContain('aria-labelledby="final-report-scope-title"');
  });

  it("stato del documento: testo sempre presente accanto all'icona, per ciascun stato", () => {
    for (const [status, label] of [
      ["ready", "Documento: Definitivo"],
      ["draft", "Documento: Bozza"],
      ["blocked", "Documento: Bloccato"],
    ] as const) {
      const report = structuredClone(BILANCIO) as FinalReportModel;
      report.readiness = { status };
      const html = render(report);
      expect(html).toContain(label);
      expect(html).toContain(`data-testid="stato-${status}"`);
    }
  });

  it("bilancio con source_scenario valorizzato lo mostra: niente righe inventate, niente righe perse", () => {
    const report = structuredClone(BILANCIO) as FinalReportModel & {
      practice: { source_scenario?: { id: number; name: string; base_year: number } };
    };
    report.practice.source_scenario = { id: 77, name: "Infrannuale residuo", base_year: 2025 };
    const html = render(report);
    expect(html).toContain("Scenario sorgente");
    expect(html).toContain("Infrannuale residuo");
  });
});
