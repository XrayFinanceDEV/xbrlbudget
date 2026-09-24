import { describe, expect, it } from "vitest";
import { previewRowsForStep } from "@/lib/budget-preview-stage";

describe("anteprima prima del Patrimoniale pregresso", () => {
  const rows: Record<string, unknown>[] = [
    { forecast_year: 2027, bank_lines_amount: null, other_lenders: [{ name: "Finanziatore 1", opening_residual: 36503.74 }] },
    { forecast_year: 2028, other_lenders: null },
  ];

  it("non applica la lista prematura nei passi economici e conserva le ipotesi da salvare", () => {
    for (const step of ["fatturato", "costi", "circolante"] as const) {
      const preview = previewRowsForStep(rows, step);
      expect(preview[0].other_lenders).toBeNull();
      expect(rows[0].other_lenders).toHaveLength(1);
      expect(preview[1]).toBe(rows[1]);
    }
  });

  it("nel Patrimoniale pregresso espone l'ipotesi da completare", () => {
    expect(previewRowsForStep(rows, "patrimoniale-pregresso")).toBe(rows);
  });

  it("non altera una divisione dei fidi già presente", () => {
    const complete = [{ ...rows[0], bank_lines_amount: 0 }];
    expect(previewRowsForStep(complete, "fatturato")).toBe(complete);
  });
});
