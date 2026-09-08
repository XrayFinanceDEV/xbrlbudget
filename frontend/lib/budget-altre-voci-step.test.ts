import { describe, expect, it } from "vitest";
import {
  altreVociCalculated,
  altreVociPreview,
  altreVociTableRows,
  effectiveTaxRateLabel,
} from "./budget-altre-voci-step";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement } from "@/types/api";

const income = (over: Partial<Record<string, unknown>> = {}): IncomeStatement =>
  ({ ce01_ricavi_vendite: "1000", ce12_oneri_diversi: "50", ce09_ammortamenti: "80", ce15_oneri_finanziari: "20", ...over } as unknown as IncomeStatement);

const previewYear = (year: number, ce09: number, ce15: number): ForecastPreviewYear =>
  ({ year, income_statement: { ce09_ammortamenti: ce09, ce15_oneri_finanziari: ce15 }, balance_sheet: {}, details: {} } as unknown as ForecastPreviewYear);

const response = (years: ForecastPreviewYear[]): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2024, forecast_years: years, error: null });

describe("altreVociTableRows", () => {
  it("la sola riga porta il ce12 dell'anno base come baseLabel", () => {
    const rows = altreVociTableRows(income());
    expect(rows).toHaveLength(1);
    expect(rows[0].field).toBe("other_costs_growth_pct");
    expect(rows[0].baseLabel).not.toBe("—");
  });

  it("anno base assente ⇒ '—', mai '€ 0' (zero e assente non sono la stessa cosa)", () => {
    expect(altreVociTableRows(undefined)[0].baseLabel).toBe("—");
    expect(altreVociTableRows(null)[0].baseLabel).toBe("—");
  });
});

describe("effectiveTaxRateLabel", () => {
  it("formatta l'aliquota derivata", () => {
    expect(effectiveTaxRateLabel(25)).toBe("25,0%");
  });

  it("cade sul fallback del motore (27,9%, non il 24 di schema) quando non derivabile", () => {
    expect(effectiveTaxRateLabel(null)).toBe("27,9%");
  });
});

describe("altreVociCalculated", () => {
  const assumptions: AssumptionsMap = { 2025: { depreciation_rate: 15 }, 2026: { depreciation_rate: 15 } };

  it("ammortamenti e oneri finanziari vanno da base a ultimo anno dell'anteprima", () => {
    const data = response([previewYear(2025, 90, 22), previewYear(2026, 95, 24)]);
    const c = altreVociCalculated(2024, income(), 25, assumptions, [2025, 2026], data);
    expect(c.ammortamenti.value).toContain("→");
    expect(c.oneriFinanziari.value).toContain("→");
    expect(c.ammortamenti.small).toContain("2024");
    expect(c.ammortamenti.small).toContain("15%");
  });

  it("senza anteprima ancora arrivata il valore non ha la freccia (solo la base)", () => {
    const c = altreVociCalculated(2024, income(), null, assumptions, [2025, 2026], null);
    expect(c.ammortamenti.value).not.toContain("→");
  });

  it("l'aliquota mostrata e' quella passata dal chiamante, col fallback se null", () => {
    const data = response([]);
    expect(altreVociCalculated(2024, income(), 28, assumptions, [2025], data).imposte.value).toBe("28,0%");
    expect(altreVociCalculated(2024, income(), null, assumptions, [2025], data).imposte.value).toBe("27,9%");
  });

  it("un anno non ancora idratato dal passo 6 usa il default di schema (20%), non zero", () => {
    const data = response([]);
    const c = altreVociCalculated(2024, income(), null, {}, [2025], data);
    expect(c.ammortamenti.small).toContain("20%");
  });

  it("un depreciation_rate esplicito a 0 resta 0, non il default", () => {
    const data = response([]);
    const c = altreVociCalculated(2024, income(), null, { 2025: { depreciation_rate: 0 } }, [2025], data);
    expect(c.ammortamenti.small).toContain("0%");
  });
});

describe("altreVociPreview", () => {
  it("senza anno base o senza risposta non c'e' anteprima: nessuna riga, non righe a zero", () => {
    expect(altreVociPreview(undefined, null)).toEqual({ years: [], rows: [] });
    expect(altreVociPreview(income(), null)).toEqual({ years: [], rows: [] });
  });

  it("gli anni sono quelli che il motore ha davvero prodotto", () => {
    const data = response([previewYear(2025, 90, 22)]);
    const p = altreVociPreview(income(), data);
    expect(p.years).toEqual([2025]);
    expect(p.rows.length).toBeGreaterThan(0);
  });
});
