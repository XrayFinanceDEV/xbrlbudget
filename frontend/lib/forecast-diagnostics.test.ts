import { describe, expect, it } from "vitest";
import { diagnosticAmount, hasDiagnosticErrors } from "./forecast-diagnostics";

describe("diagnostiche del previsionale", () => {
  it("distingue gli errori dagli avvisi", () => {
    expect(hasDiagnosticErrors([{ code: "x", severity: "warning", message: "x" }])).toBe(false);
    expect(hasDiagnosticErrors([{ code: "x", severity: "error", message: "x" }])).toBe(true);
  });

  it("formatta gli importi stringa del backend in euro", () => {
    expect(diagnosticAmount({
      code: "tax_settlement_reclass_below_zero",
      severity: "warning",
      message: "Residuo",
      amount: "-14306.93",
    })).toMatch(/-14\.306,93\s*€/);
  });

  it("non inventa un importo quando il diagnostico non lo porta", () => {
    expect(diagnosticAmount({ code: "x", severity: "warning", message: "x" })).toBeNull();
  });
});
