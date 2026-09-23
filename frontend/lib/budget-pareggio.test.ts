import { describe, expect, it } from "vitest";
import type { ForecastPreviewYear } from "@/types/api";
import { pareggioAnnoBase, pareggioBarre, pareggioFormula, rowsPareggio } from "./budget-pareggio";
import type { IncomeStatement } from "@/types/api";

const anno = (year: number, pareggio: Record<string, number | null>, ce01 = 600000): ForecastPreviewYear => ({
  year, income_statement: { ce01_ricavi_vendite: ce01, ce04_altri_ricavi: 0 }, balance_sheet: {},
  details: { pareggio } as never,
} as unknown as ForecastPreviewYear);
const ok = { costi_variabili: 210000, costi_fissi: 275000, costi_fissi_operativi: 275000, margine_contribuzione_pct: 65, fatturato_pareggio: 423076.92, margine_sicurezza: 176923.08, margine_sicurezza_pct: 29.49 };
const nd = { costi_variabili: null, costi_fissi: null, costi_fissi_operativi: null, margine_contribuzione_pct: null, fatturato_pareggio: null, margine_sicurezza: null, margine_sicurezza_pct: null };
// Lo stesso caso "ok", ma con ogni valore serializzato come stringa — cio' che arriva
// davvero quando il motore manda un `Decimal` nidificato dentro `details` (regole comuni
// del lotto: solo il primo livello di `details` diventa float, i sotto-dizionari no).
const okStringa = Object.fromEntries(Object.entries(ok).map(([k, v]) => [k, String(v)])) as unknown as Record<string, number | null>;

describe("budget-pareggio", () => {
  it("calcola anche l'anno base con slider e voci operative del bilancio storico", () => {
    const income = {
      ce01_ricavi_vendite: 600000, ce05_materie_prime: 200000, ce06_servizi: 100000,
      ce07_godimento_beni: 30000, ce08_costi_personale: 200000, ce12_oneri_diversi: 20000,
      ce04_altri_ricavi: 50000, ce02_variazioni_rimanenze: 10000,
      ce10_var_rimanenze_mat_prime: 5000, ce11b_altri_accantonamenti: 2000,
    } as unknown as IncomeStatement;
    const base = pareggioAnnoBase(2026, income, { materials: 25, services: 50 });
    expect(base.details?.pareggio).toMatchObject({
      costi_variabili: 200000, costi_fissi: 350000, costi_fissi_operativi: 297000,
      margine_contribuzione_pct: 66.67, fatturato_pareggio: 445500,
      margine_sicurezza: 154500, margine_sicurezza_pct: 25.75,
    });
    const rows = rowsPareggio([anno(2027, ok)], base);
    expect(rows.find((r) => r.key === "ricavi")?.base.value).toBe(600000);
    expect(rows.find((r) => r.key === "pareggio")?.base.value).toBe(445500);
    expect(rows.find((r) => r.key === "mdc")?.base.pct).toBe(66.67);
    expect(pareggioBarre([base, anno(2027, ok)]).map((b) => b.year)).toEqual([2026, 2027]);
    expect(pareggioFormula(base)?.anno).toBe(2026);
  });

  it("con ricavi o margine di contribuzione non positivi non inventa un pareggio", () => {
    const income = { ce01_ricavi_vendite: 100, ce05_materie_prime: 150 } as unknown as IncomeStatement;
    const base = pareggioAnnoBase(2026, income, { materials: 0, services: 0 });
    expect(base.details?.pareggio?.fatturato_pareggio).toBeNull();
    expect(rowsPareggio([], base).find((r) => r.key === "pareggio")?.base.value).toBeNull();
  });

  it("le barre: ricavi, tacca del pareggio e segmento del margine, sulla scala del massimo", () => {
    const [b] = pareggioBarre([anno(2027, ok)]);
    expect(b.ok).toBe(true);
    expect(b.ricaviPct).toBeCloseTo(100 / 1.04, 2);
    expect(b.pareggioPct).toBeCloseTo(423076.92 / 624000 * 100, 2);
    expect(b.margineDaPct).toBe(b.pareggioPct);
    expect(b.margineAPct).toBe(b.ricaviPct);
    expect(b.marginePct).toBe(29.49);
  });
  it("sotto il pareggio il segmento va dai ricavi alla tacca e ok e' falso", () => {
    const [b] = pareggioBarre([anno(2027, { ...ok, fatturato_pareggio: 700000, margine_sicurezza: -100000, margine_sicurezza_pct: -16.67 })]);
    expect(b.ok).toBe(false);
    expect(b.margineDaPct).toBe(b.ricaviPct);
    expect(b.margineAPct).toBe(b.pareggioPct);
  });
  it("un anno non definito e' marcato nd", () => {
    const [b] = pareggioBarre([anno(2027, nd)]);
    expect(b.nd).toBe(true);
    expect(rowsPareggio([anno(2027, nd)]).find((r) => r.key === "pareggio")?.years[0].note).toBe("Non definito: materie prime o servizi forzati in CE Prev.");
  });
  it("la formula dell'anno 1", () => {
    const f = pareggioFormula(anno(2027, ok));
    expect(f?.anno).toBe(2027);
    expect(f?.righe[0]).toEqual({ testo: "Margine di contribuzione % = (ricavi − costi variabili) / ricavi", calcolo: "(600.000 − 210.000) / 600.000 = 65,0%" });
    expect(f?.righe[2].calcolo).toBe("275.000 / 65,0% = 423.077");
    expect(f?.righe[1].calcolo).toBe("275.000 − 0 = 275.000");
    expect(pareggioFormula(anno(2027, nd))).toBeNull();
  });
  it("le righe della tabella", () => {
    const rows = rowsPareggio([anno(2027, ok)]);
    expect(rows.map((r) => r.key)).toEqual(["ricavi", "mdc", "pareggio", "margine-pct", "margine"]);
    expect(rows[2].years[0].value).toBe(423076.92);
    expect(rows[2].label).toBe("Fatturato di BEP");
    expect(rows[2].hint).toBe("Fatturato minimo per coprire i costi arrivando a MOL = 0");
  });

  // Deviazione dichiarata dal coordinatore (dispatch Task 11): `details.pareggio` e'
  // `Decimal` nel motore e puo' arrivare come stringa. Le tre funzioni pubbliche devono
  // dare lo STESSO risultato sia coi numeri sia con le stringhe.
  it("i valori di details.pareggio come stringa danno lo stesso risultato dei numeri", () => {
    expect(pareggioBarre([anno(2027, okStringa)])).toEqual(pareggioBarre([anno(2027, ok)]));
    expect(pareggioFormula(anno(2027, okStringa))).toEqual(pareggioFormula(anno(2027, ok)));
    expect(rowsPareggio([anno(2027, okStringa)])).toEqual(rowsPareggio([anno(2027, ok)]));
  });
});
