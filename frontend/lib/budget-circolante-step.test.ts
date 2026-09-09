import { describe, expect, it } from "vitest";
import {
  boolAssumption,
  circolantePreview,
  giorniMediAuto,
  giorniMediRows,
  minorFieldsRows,
} from "./budget-circolante-step";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement } from "@/types/api";

const income = (over: Partial<Record<string, unknown>> = {}): IncomeStatement =>
  ({ ce01_ricavi_vendite: "3600", ce05_materie_prime: "900", ce06_servizi: "0", ...over } as unknown as IncomeStatement);

const balance = (over: Partial<Record<string, unknown>> = {}): BalanceSheet =>
  ({
    sp05_rimanenze: "200", sp06_crediti_breve: "600", sp06e_crediti_tributari_breve: "0",
    sp06f_imposte_anticipate_breve: "0", sp16d_debiti_fornitori_breve: "300",
    sp07_crediti_lungo: "50", sp01_crediti_soci: "10", sp04_immob_finanziarie: "20",
    sp08_attivita_finanziarie: "30", sp10_ratei_risconti_attivi: "5", sp14_fondi_rischi: "40",
    sp16f_debiti_previdenza_breve: "15", sp16g_altri_debiti_breve: "25", sp17d_debiti_fornitori_lungo: "0",
    sp17f_debiti_previdenza_lungo: "0", sp17g_altri_debiti_lungo: "0", sp18_ratei_risconti_passivi: "8",
    ...over,
  } as unknown as BalanceSheet);

const previewYear = (year: number): ForecastPreviewYear =>
  ({ year, income_statement: { ce01_ricavi_vendite: 3800 }, balance_sheet: { sp06_crediti_breve: 620, sp05_rimanenze: 210, sp16d_debiti_fornitori_breve: 310 }, details: { dso_applied: 60, dio_applied: 20, dpo_applied: 30 } } as unknown as ForecastPreviewYear);

const response = (years: ForecastPreviewYear[]): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2024, forecast_years: years, error: null });

describe("giorniMediAuto + giorniMediRows", () => {
  it("i tre giorni derivano da computeAutoDays, con baseLabel e placeholder coerenti", () => {
    const auto = giorniMediAuto(income(), balance());
    expect(auto.dso).not.toBeNull();
    const rows = giorniMediRows(auto);
    expect(rows).toHaveLength(3);
    expect(rows[0].field).toBe("dso_days");
    expect(rows[0].baseLabel).toBe(`${auto.dso} gg`);
    expect(rows[0].placeholder?.(2025)).toBe(`auto ${auto.dso}`);
  });

  it("senza anno base i tre giorni sono null: baseLabel 'n/d', placeholder 'auto' senza numero", () => {
    const auto = giorniMediAuto(undefined, undefined);
    expect(auto).toEqual({ dso: null, dio: null, dpo: null });
    const rows = giorniMediRows(auto);
    expect(rows[0].baseLabel).toBe("n/d");
    expect(rows[0].placeholder?.(2025)).toBe("auto");
  });
});

describe("minorFieldsRows", () => {
  it("le 14 righe, ciascuna col proprio importo base", () => {
    const rows = minorFieldsRows(balance());
    expect(rows).toHaveLength(14);
    expect(rows.find((r) => r.field === "sp01_growth_pct")?.label).toBe("Crediti verso soci");
    expect(rows.every((r) => r.baseLabel !== "—")).toBe(true);
  });

  it("anno base assente ⇒ '—' su tutte le righe, mai '€ 0'", () => {
    const rows = minorFieldsRows(undefined);
    expect(rows.every((r) => r.baseLabel === "—")).toBe(true);
  });
});

describe("boolAssumption", () => {
  it("legge il valore del primo anno previsto", () => {
    const a: AssumptionsMap = { 2025: { previdenza_scales_with_personnel: true }, 2026: { previdenza_scales_with_personnel: false } };
    expect(boolAssumption(a, [2025, 2026], "previdenza_scales_with_personnel")).toBe(true);
  });

  it("assente ⇒ false, il default del motore", () => {
    expect(boolAssumption({}, [2025], "tfr_accrual_suspended")).toBe(false);
  });
});

describe("circolantePreview", () => {
  it("senza SP o CE base, o senza risposta, non c'e' anteprima", () => {
    expect(circolantePreview(undefined, income(), null)).toEqual({ years: [], rows: [] });
    expect(circolantePreview(balance(), undefined, null)).toEqual({ years: [], rows: [] });
    expect(circolantePreview(balance(), income(), null)).toEqual({ years: [], rows: [] });
  });

  it("gli anni sono quelli che il motore ha davvero prodotto", () => {
    const data = response([previewYear(2025)]);
    const p = circolantePreview(balance(), income(), data);
    expect(p.years).toEqual([2025]);
    expect(p.rows.length).toBeGreaterThan(0);
  });
});
