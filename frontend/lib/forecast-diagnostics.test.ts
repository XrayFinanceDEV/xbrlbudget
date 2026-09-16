import { describe, expect, it } from "vitest";
import {
  diagnosticAmount,
  diagnosticsLabel,
  diagnosticsSignature,
  hasDiagnosticErrors,
} from "./forecast-diagnostics";

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

describe("chiusura della card", () => {
  const verifica = (code: string, message: string) => ({ code, severity: "warning" as const, message });

  it("la firma cambia quando cambiano le verifiche, così una proiezione nuova si rimostra", () => {
    const prima = [verifica("a", "uno")];
    expect(diagnosticsSignature(prima)).toBe(diagnosticsSignature([verifica("a", "uno")]));
    expect(diagnosticsSignature(prima)).not.toBe(diagnosticsSignature([verifica("a", "due")]));
    expect(diagnosticsSignature(prima)).not.toBe(diagnosticsSignature([verifica("b", "uno")]));
    expect(diagnosticsSignature(prima)).not.toBe(
      diagnosticsSignature([verifica("a", "uno"), verifica("b", "due")]),
    );
  });

  it("il numero si legge anche a card chiusa", () => {
    expect(diagnosticsLabel([verifica("a", "uno")])).toBe("1 verifica richiesta");
    expect(diagnosticsLabel([verifica("a", "uno"), verifica("b", "due")])).toBe("2 verifiche richieste");
  });
});
