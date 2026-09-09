import { describe, expect, it } from "vitest";
import type { ForecastPreviewResponse } from "@/types/api";
import type { PreviewState } from "./budget-preview-state";
import { previewNotice } from "./budget-preview-notice";

const withData = (error: ForecastPreviewResponse["error"]): PreviewState => ({
  loading: false,
  error: null,
  data: { scenario_id: 1, base_year: 2024, forecast_years: [], error },
});

describe("previewNotice", () => {
  it("nessun errore -> null", () => {
    expect(previewNotice({ loading: false, error: null, data: null })).toBeNull();
    expect(previewNotice(withData(null))).toBeNull();
  });

  it("errore di trasporto vince sempre, anche con un data.error valorizzato", () => {
    const preview: PreviewState = {
      loading: false,
      error: "Rete non raggiungibile",
      data: { scenario_id: 1, base_year: 2024, forecast_years: [],
        error: { year: 2028, message: "Unfunded financing requirement 1,000.00: add a financing assumption" } },
    };
    expect(previewNotice(preview)).toBe("Rete non raggiungibile");
  });

  it("fabbisogno scoperto riconosciuto: importo e anno, non il messaggio inglese del motore", () => {
    const notice = previewNotice(withData({
      year: 2028, message: "Unfunded financing requirement 84,120.50: add a financing assumption",
    }));
    expect(notice).not.toBeNull();
    expect(notice).toContain("2028");
    expect(notice).toMatch(/84\.1|84120/); // formatCurrency arrotonda, ma l'importo resta leggibile
    expect(notice).not.toContain("Unfunded financing requirement");
  });

  it("data.error che la regex non riconosce -> il messaggio grezzo, mai null in silenzio", () => {
    const notice = previewNotice(withData({ year: 2028, message: "Errore generico del motore" }));
    expect(notice).toBe("Errore generico del motore");
  });

  it("data.error con year null (regex su unfundedFromError esce comunque null) -> messaggio grezzo", () => {
    const notice = previewNotice(withData({ year: null, message: "Errore senza anno" }));
    expect(notice).toBe("Errore senza anno");
  });
});
