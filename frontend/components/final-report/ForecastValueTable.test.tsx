import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import type { FinalReportModel } from "@/types/final-report";
import { ForecastValueTable, formatStatementValue } from "./ForecastValueTable";

describe("ForecastValueTable", () => {
  it("renders report statement values in Italian without losing DecimalString precision", () => {
    const report = structuredClone(bilancio) as FinalReportModel;
    report.forecast.years[0].income_statement[0].value = "9007199254740993.000000000000000001";
    const html = renderToStaticMarkup(<ForecastValueTable report={report} statement="income_statement" />);

    expect(html).toContain("9.007.199.254.740.993,000000000000000001 €");
    expect(html).toContain("Conto economico previsionale per anno di previsione");
    expect(html).toContain('<th scope="row"');
  });

  it("uses monetary formatting for all statements and honest unit-neutral formatting for calculations", () => {
    expect(formatStatementValue("1000", "income_statement")).toBe("1.000,00 €");
    expect(formatStatementValue("1000", "balance_sheet")).toBe("1.000,00 €");
    expect(formatStatementValue("1000", "cashflow")).toBe("1.000,00 €");
    expect(formatStatementValue("1000", "calculations")).toBe("1.000,00");
    expect(formatStatementValue(null, "calculations")).toBe("—");
  });
});
