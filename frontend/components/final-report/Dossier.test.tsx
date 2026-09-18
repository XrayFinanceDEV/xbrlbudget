import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import annual from "../../../tests/fixtures/final_report/v2/bilancio.json";
import type { FinalReportModelV2 } from "@/types/final-report-v2";
import { DossierContent } from "./Dossier";

describe("DossierContent", () => {
  it("prints every chart, indicator value and full CE/SP/CF attachments", () => {
    const html = renderToStaticMarkup(<DossierContent report={annual as FinalReportModelV2} />);
    expect((html.match(/data-testid="final-report-chart-/g) ?? []).length).toBe(20); // +4 serie pagine executive (M2-02G fase 2: pag. 8/12/14/17)
    expect((html.match(/Convenzione:/g) ?? []).length).toBe(48); // + practice.quick_ratio/ebit_margin/opex_revenue/effective_tax_rate (M2-02E)
    expect(html).toContain("Allegati");
    expect(html).toContain("Conto economico");
    expect(html).toContain("Stato patrimoniale");
    expect(html).toContain("Rendiconto finanziario");
  });
  it("renders null reasons and exact zero values as distinct output", () => {
    const report = structuredClone(annual);
    const row = report.detailed_statements[0].rows.find((item) => item.kind === "detail")!;
    row.values[0] = null; row.unavailable_reasons[0] = "Dato non applicabile";
    row.values[1] = "0"; row.unavailable_reasons[1] = null;
    const html = renderToStaticMarkup(<DossierContent report={report as FinalReportModelV2} />);
    expect(html).toContain("Dato non applicabile");
    expect(html).toContain("0,00 €");
  });
});
