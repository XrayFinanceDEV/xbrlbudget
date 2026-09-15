import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../../tests/fixtures/final_report/startup.json";
import type { FinalReportModel, SourceRevision } from "@/types/final-report";
import { ReportSources } from "./Sources";

const INFRANNUALE = infrannuale as unknown as FinalReportModel;
const BILANCIO = bilancio as unknown as FinalReportModel;
const STARTUP = startup as unknown as FinalReportModel;

const render = (report: FinalReportModel): string =>
  renderToStaticMarkup(
    <ReportSources
      workflow={report.practice.workflow_type}
      budgetScenarioName={report.practice.budget_scenario.name}
      sourceRevisions={report.source_revisions}
      sourceDataQuality={report.source_data_quality}
    />,
  );

describe("ReportSources (origine e qualità dei dati)", () => {
  it("infrannuale: la fonte storica con revisione e data ISO emerge in chiaro", () => {
    const html = render(INFRANNUALE);
    expect(html).toContain("Percorso infrannuale");
    expect(html).toContain("Budget 2027-2029");
    expect(html).toContain("Bilancio storico");
    expect(html).toContain("fy-10");
    expect(html).toContain("r3");
    expect(html).toContain("01/09/2026 08:00Z");
    // `available` assente nel fixture: «non dichiarato», mai «disponibile».
    expect(html).toContain("stato non dichiarato");
  });

  it("bilancio: revisione null è «non disponibile», mai una data inventata", () => {
    const html = render(BILANCIO);
    expect(html).toContain("Previsionale persistita");
    expect(html).toContain("non disponibile");
    expect(html).toContain("Disponibile");
    expect(html).toContain("Completezza delle fonti: Completo");
  });

  it("startup: fonte senza revisione temporizzata resta leggibile e il censimento è uno", () => {
    const html = render(STARTUP);
    expect(html).toContain("Motore di calcolo");
    expect(html).toContain("forecast-v1");
    expect(html).toContain("1 fonte censita");
    expect(html).toContain("Completezza delle fonti: Dati legacy");
  });

  it("fonte marcata non disponibile lo dice con testo e icona, non col solo colore", () => {
    const report = structuredClone(BILANCIO) as FinalReportModel;
    const rev: SourceRevision = { source: "adjustments", available: false };
    report.source_revisions = [rev];
    const html = render(report);
    expect(html).toContain("Log rettifiche");
    expect(html).toContain("Non disponibile");
    expect(html).toContain("<svg"); // icona accanto alla parola
  });

  it("le diagnostiche sulla qualità escono con gravità in testo italiano", () => {
    const report = structuredClone(BILANCIO) as FinalReportModel;
    report.source_data_quality = {
      status: "partial",
      diagnostics: [
        {
          code: "source_revision_missing",
          severity: "warning",
          section: "sources",
          message: "Revisione non tracciata per dati storici legacy",
        },
        {
          code: "engine_version_unknown",
          severity: "info",
          section: "sources",
          message: "Versione del motore non disponibile",
        },
      ],
    };
    const html = render(report);
    expect(html).toContain("Completezza delle fonti: Parziale");
    expect(html).toContain("source_revision_missing");
    expect(html).toContain("Avviso");
    expect(html).toContain("Notizia");
    expect(html).toContain("Revisione non tracciata per dati storici legacy");
  });

  it("nessuna diagnostica: «Nessun avviso dalle fonti», non una tabella vuota", () => {
    const html = render(BILANCIO);
    expect(html).toContain("Nessun avviso dalle fonti");
  });

  it("tabella accessibili: didascalie, th di colonna e th di riga per ogni fonte", () => {
    const html = render(INFRANNUALE);
    expect(html).toContain("<caption");
    expect(html).toContain("Identificativi e revisioni delle fonti da cui deriva il documento");
    for (const heading of ["Fonte", "Identificativo", "Revisione", "Aggiornata al", "Disponibilità"]) {
      expect(html).toContain(`>${heading}<`);
    }
    expect(html).toContain('<th scope="row"');
    expect(html.match(/<th scope="col"/g)?.length).toBeGreaterThanOrEqual(5);
    expect(html).toContain('aria-labelledby="final-report-sources-title"');
  });
});
