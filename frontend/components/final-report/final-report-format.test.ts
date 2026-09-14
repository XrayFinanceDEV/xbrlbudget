import { describe, expect, it } from "vitest";
import {
  formatDateTimeItalian,
  formatDateItalian,
  formatEuro,
  formatNumber,
  formatSignedEuro,
  MISSING_VALUE,
  periodMonthsLabel,
  QUALITY_LABELS,
  READINESS_LABELS,
  SEVERITY_LABELS,
  SOURCE_LABELS,
  WORKFLOW_LABELS,
} from "./final-report-format";

// Intl it-IT separa l'importo dal simbolo con NBSP (U+00A0), non con spazio.
const eur = (body: string): string => `${body}\u00A0€`;

describe("final-report-format", () => {
  it("formatEuro: segno, zero e assenza non si confondono", () => {
    expect(formatEuro("1200.00")).toBe(eur("1.200,00"));
    expect(formatEuro("-120.5")).toBe(eur("-120,50"));
    expect(formatEuro("0")).toBe(eur("0,00"));
    expect(formatEuro("0")).not.toBe(MISSING_VALUE);
    expect(formatEuro(null)).toBe(MISSING_VALUE);
    expect(formatEuro(undefined)).toBe(MISSING_VALUE);
  });

  it("formatEuro: un valore malformato esce tal quale, non taciuto da un trattino", () => {
    // Il trattino è riservato all'assenza: mascherare un numero illeggibile
    // dietro «—» sarebbe inventarsi puliti, non essere onesti.
    expect(formatEuro("NonUnNumero" as never)).toBe("NonUnNumero");
    expect(formatEuro(Number.NaN as never)).toBe("NaN");
  });

  it("formatSignedEuro: + esplicito sul positivo, - dell'Intl sul negativo, nessun segno sullo zero", () => {
    expect(formatSignedEuro("120.00")).toBe(`+${eur("120,00")}`);
    expect(formatSignedEuro("-120.00")).toBe(eur("-120,00"));
    expect(formatSignedEuro("0")).toBe(eur("0,00"));
    expect(formatSignedEuro(null)).toBe(MISSING_VALUE);
  });

  it("formatNumber: separatore italiano senza simbolo di valuta", () => {
    expect(formatNumber("45")).toBe("45,00");
    expect(formatNumber("-90.25")).toBe("-90,25");
    expect(formatNumber(null)).toBe(MISSING_VALUE);
  });

  it("formatDateItalian: spezza l'ISO senza fuso, il giorno non si sposta", () => {
    expect(formatDateItalian("2026-09-30")).toBe("30/09/2026");
    expect(formatDateItalian("2026-01-01")).toBe("01/01/2026");
    expect(formatDateItalian(null)).toBe(MISSING_VALUE);
    expect(formatDateItalian("broglio")).toBe("broglio");
  });

  it("formatDateTimeItalian: conserva il marcatore di fuso dichiarato", () => {
    expect(formatDateTimeItalian("2026-09-01T08:00:00Z")).toBe("01/09/2026 08:00Z");
    expect(formatDateTimeItalian("2026-09-01T08:30:00+02:00")).toBe("01/09/2026 08:30+02:00");
    // Solo data: niente ora inventata.
    expect(formatDateTimeItalian("2026-09-01")).toBe("01/09/2026");
    expect(formatDateTimeItalian(null)).toBe(MISSING_VALUE);
  });

  it("periodMonthsLabel: null e 12 sono entrambi anno pieno", () => {
    expect(periodMonthsLabel(null)).toBe("Anno pieno (12 mesi)");
    expect(periodMonthsLabel(12)).toBe("Anno pieno (12 mesi)");
    expect(periodMonthsLabel(undefined)).toBe("Anno pieno (12 mesi)");
    expect(periodMonthsLabel(9)).toBe("9 mesi su 12");
  });

  it("le etichette coprono ogni valore del contratto, senza buchi", () => {
    expect(Object.keys(WORKFLOW_LABELS).sort()).toEqual(["bilancio", "infrannuale", "startup"]);
    expect(Object.keys(SOURCE_LABELS).sort()).toEqual(
      [
        "adjustments",
        "budget_assumptions",
        "calculation_engine",
        "forecast",
        "historical_financial_year",
        "narrative",
        "source_scenario",
      ].sort(),
    );
    expect(Object.keys(READINESS_LABELS).sort()).toEqual(["blocked", "draft", "ready"]);
    expect(Object.keys(QUALITY_LABELS).sort()).toEqual(["complete", "legacy", "partial"]);
    expect(Object.keys(SEVERITY_LABELS).sort()).toEqual(["error", "info", "warning"]);
    // Ogni etichetta è testo leggibile in italiano: nessun stato è solo colore.
    for (const map of [
      WORKFLOW_LABELS,
      SOURCE_LABELS,
      READINESS_LABELS,
      QUALITY_LABELS,
      SEVERITY_LABELS,
    ]) {
      for (const label of Object.values(map)) expect(label.trim().length).toBeGreaterThan(1);
    }
  });
});
