import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../../tests/fixtures/final_report/startup.json";
import type { ChartSeries, FinalReportModel } from "@/types/final-report";
import { ChartValueTooltip, FinalReportChart, formatChartValue } from "./ChartSeries";

const reports = [infrannuale, bilancio, startup] as unknown as FinalReportModel[];

describe("FinalReportChart", () => {
  it("renders all six server-provided chart containers, text legends, and adjacent accessible tables", () => {
    const report = reports[0];
    const html = renderToStaticMarkup(<>{report.chart_series.map((series) => <FinalReportChart key={series.id} series={series} />)}</>);

    expect((html.match(/data-testid="final-report-chart-/g) ?? []).length).toBe(6);
    expect((html.match(/aria-label="Grafico /g) ?? []).length).toBe(6);
    expect((html.match(/Dati accessibili del grafico/g) ?? []).length).toBe(6);
    for (const unit of ["Euro", "Percentuale", "Giorni", "Indice"]) expect(html).toContain(`Unità: ${unit}`);
    for (const series of report.chart_series) {
      expect(html).toContain(series.title);
      expect(html).toContain(`Legenda ${series.title}`);
      for (const metric of series.series) expect(html).toContain(metric.label);
    }
    expect(html).toContain('<th scope="col"');
    expect(html).toContain('<th scope="row"');
  });

  it("keeps high-precision DecimalString display formatting Italian and never uses geometry values as text", () => {
    const series = structuredClone(reports[0].chart_series[0]) as ChartSeries;
    series.categories = [2027];
    series.series = [{ key: "revenue", label: "Ricavi", values: ["9007199254740993.000000000000000001"] }];
    const html = renderToStaticMarkup(<FinalReportChart series={series} />);

    expect(html).toContain("9.007.199.254.740.993,000000000000000001 €");
    expect(html).not.toContain("9,007,199,254,740,992");

    const tooltip = renderToStaticMarkup(<ChartValueTooltip active unit="eur" payload={[{
      dataKey: "revenue", name: "Ricavi", payload: { category: 2027, raw: { revenue: "9007199254740993.000000000000000001" }, revenue: 9007199254740992 },
    }]} />);
    expect(tooltip).toContain("9.007.199.254.740.993,000000000000000001 €");
    expect(tooltip).not.toContain("9,007,199,254,740,992");
  });

  it("formats every frozen unit in Italian while preserving null as an em dash", () => {
    expect(formatChartValue("1234.5", "eur")).toBe("1.234,50 €");
    expect(formatChartValue("12.345", "percent")).toBe("12,345%");
    expect(formatChartValue("30", "days")).toBe("30,00 giorni");
    expect(formatChartValue("1.5", "ratio")).toBe("1,50");
    expect(formatChartValue(null, "days")).toBe("—");
  });

  it("consumes the canonical six series for infrannuale, bilancio, and startup without making workflow-specific chart data", () => {
    for (const report of reports) {
      expect(report.chart_series).toHaveLength(6);
      const html = renderToStaticMarkup(<>{report.chart_series.map((series) => <FinalReportChart key={series.id} series={series} />)}</>);
      expect((html.match(/data-testid="final-report-chart-/g) ?? []).length).toBe(6);
    }
  });
});
