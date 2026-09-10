import { describe, expect, it } from "vitest";
import { previewStateFromError, previewStateFromResponse } from "./budget-preview-state";
import type { ForecastPreviewResponse } from "@/types/api";

const RESPONSE_WITH_ERROR: ForecastPreviewResponse = {
  scenario_id: 1,
  base_year: 2024,
  forecast_years: [
    {
      year: 2025,
      income_statement: { ce01_ricavi_vendite: 1000 },
      balance_sheet: { sp09_disponibilita_liquide: 50 },
      details: {
        ce05_fixed: null,
        ce05_variable: null,
        ce06_fixed: null,
        ce06_variable: null,
        dso_applied: 60,
        dio_applied: 30,
        dpo_applied: 45,
        pregresso: { crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } },
        imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" },
        degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [], pregresso_writeoff_ignored: [],
      },
    },
  ],
  // Il motore si e' fermato al 2026 (fabbisogno scoperto), ma il 2025 e' valido.
  error: { year: 2026, message: "Unfunded financing requirement 12.345,67" },
};

describe("previewStateFromResponse", () => {
  it("una 200 con error valorizzato non svuota data: porta la risposta INTERA", () => {
    const state = previewStateFromResponse(RESPONSE_WITH_ERROR);

    expect(state.data).toEqual(RESPONSE_WITH_ERROR);
    expect(state.data?.forecast_years).toHaveLength(1);
    expect(state.data?.forecast_years[0].year).toBe(2025);
    expect(state.data?.error).toEqual({ year: 2026, message: "Unfunded financing requirement 12.345,67" });
  });

  it("il canale di trasporto resta null: una 200 non e' un guasto di rete", () => {
    const state = previewStateFromResponse(RESPONSE_WITH_ERROR);
    expect(state.error).toBeNull();
  });

  it("spegne loading", () => {
    const state = previewStateFromResponse(RESPONSE_WITH_ERROR);
    expect(state.loading).toBe(false);
  });

  it("una risposta senza error valorizzato si comporta allo stesso modo (nessun trattamento speciale)", () => {
    const clean: ForecastPreviewResponse = { ...RESPONSE_WITH_ERROR, error: null };
    const state = previewStateFromResponse(clean);
    expect(state.data).toEqual(clean);
    expect(state.error).toBeNull();
    expect(state.loading).toBe(false);
  });
});

describe("previewStateFromError", () => {
  it("conserva la data precedente (l'ultima anteprima valida resta a schermo)", () => {
    const prev = { data: RESPONSE_WITH_ERROR, error: null, loading: true };
    const state = previewStateFromError(prev, "Anteprima non disponibile");
    expect(state.data).toEqual(RESPONSE_WITH_ERROR);
  });

  it("accende il messaggio di errore di trasporto", () => {
    const prev = { data: null, error: null, loading: true };
    const state = previewStateFromError(prev, "Scenario inesistente");
    expect(state.error).toBe("Scenario inesistente");
  });

  it("spegne loading", () => {
    const prev = { data: null, error: null, loading: true };
    const state = previewStateFromError(prev, "boom");
    expect(state.loading).toBe(false);
  });
});
