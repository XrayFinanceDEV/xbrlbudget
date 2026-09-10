import { describe, expect, it } from "vitest";
import {
  boolAssumption,
  circolantePreview,
  giorniMediAuto,
  giorniMediRows,
  minorFieldsRows,
  pianiPregressoOf,
  spIndexingOf,
  DRIVERS,
} from "./budget-circolante-step";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement } from "@/types/api";

const income = (over: Partial<Record<string, unknown>> = {}): IncomeStatement =>
  ({ ce01_ricavi_vendite: "3600", ce05_materie_prime: "900", ce06_servizi: "0", ...over } as unknown as IncomeStatement);

const balance = (over: Partial<Record<string, unknown>> = {}): BalanceSheet =>
  ({
    sp05_rimanenze: "200", sp06_crediti_breve: "600", sp06e_crediti_tributari_breve: "0",
    sp06f_imposte_anticipate_breve: "0", sp16d_debiti_fornitori_breve: "300",
    sp07_crediti_lungo: "50", sp07f_imposte_anticipate_lungo: "7", sp01_crediti_soci: "10", sp04_immob_finanziarie: "20",
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
  it("le 15 righe, ciascuna col proprio importo base", () => {
    const rows = minorFieldsRows(balance());
    expect(rows).toHaveLength(15);
    expect(rows.find((r) => r.field === "sp01_growth_pct")?.label).toBe("Crediti verso soci");
    expect(rows.every((r) => r.baseLabel !== "—")).toBe(true);
  });

  it("anno base assente ⇒ '—' su tutte le righe, mai '€ 0'", () => {
    const rows = minorFieldsRows(undefined);
    expect(rows.every((r) => r.baseLabel === "—")).toBe(true);
  });

  it("senza aggancio ogni voce dichiara di restare costante, e la % resta viva", () => {
    // E' la frase che oggi non dice nessuno: una voce lasciata vuota resta
    // FERMA per tutto il piano, e nulla lo segnala.
    const riga = minorFieldsRows(balance()).find((r) => r.field === "sp16g_growth_pct");
    expect(riga?.andamento).toBe("Costante per tutto il piano, salvo variazione %");
    expect(riga?.agganciata).toBe(false);
    expect(riga?.driver).toBeNull();
    expect(riga?.off).toBeUndefined();
  });

  it("agganciata a un driver: lo dichiara, e spegne la casella della %", () => {
    const riga = minorFieldsRows(balance(), { sp16g: "ricavi" })
      .find((r) => r.field === "sp16g_growth_pct");
    expect(riga?.andamento).toBe("Cresce con i ricavi");
    expect(riga?.agganciata).toBe(true);
    expect(riga?.driver).toBe("ricavi");
    // Un driver vince sulla percentuale: lasciarla viva darebbe una casella
    // che accetta un numero senza alcun effetto.
    expect(riga?.off).toBe(true);
    expect(riga?.offNote).toContain("non viene applicata");
  });

  it("le voci governate altrove non offrono alcun driver, e dicono da chi", () => {
    const rows = minorFieldsRows(balance(), { sp06e: "ricavi", sp06f: "ricavi", sp07f: "ricavi" });
    const governate = rows.filter((r) => r.code === null);
    expect(governate.map((r) => r.field)).toEqual([
      "receivables_long_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct", "sp07f",
    ]);
    expect(rows.find((r) => r.field === "sp06e_growth_pct")?.andamento)
      .toBe("Governata dalla posizione tributaria");
    // La chiave c'e' ma il motore la ignorerebbe: l'interfaccia non la applica
    // e non la offre, invece di lasciarla scegliere e poi buttarla via.
    expect(rows.find((r) => r.field === "sp06e_growth_pct")?.driver).toBeNull();
    expect(rows.filter((r) => r.code !== null)).toHaveLength(11);
  });

  it("le imposte anticipate sono escluse per INTERO, entro e oltre", () => {
    // Mostrarne una sola meta' faceva sembrare che l'esclusione valesse per
    // meta' della coppia: `sp07f` non ha nemmeno una percentuale propria — la
    // scrive il kernel del deferred — quindi la sua riga e' di sola lettura.
    const rows = minorFieldsRows(balance());
    const coppia = rows.filter((r) => r.field.startsWith("sp06f") || r.field === "sp07f");
    expect(coppia).toHaveLength(2);
    for (const r of coppia) {
      expect(r.code).toBeNull();
      expect(r.andamento).toBe("Governata dalla posizione fiscale");
    }
    expect(coppia[0].off).toBeUndefined();          // sp06f ha ancora la sua %
    expect(coppia[1].off).toBe(true);               // sp07f no: riga inerte
  });

  it("una voce con piano di scadenziamento non offre alcun driver (Ruling 17)", () => {
    // Il motore ignorerebbe comunque la chiave e lo dichiarerebbe, ma un
    // selettore vivo che afferma «Cresce con i ricavi» mentre il motore sta
    // estinguendo la voce e' peggio del divieto: e' una bugia a schermo.
    const rows = minorFieldsRows(
      balance(), { sp16g: "ricavi", sp17g: "ricavi", sp16f: "ricavi" },
      false, ["altri_debiti"],
    );
    for (const field of ["sp16g_growth_pct", "sp17g_growth_pct"]) {
      const r = rows.find((x) => x.field === field);
      expect(r?.code).toBeNull();
      expect(r?.driver).toBeNull();
      expect(r?.agganciata).toBe(false);
      expect(r?.andamento).toBe("Governata dal piano di scadenziamento");
      expect(r?.off).toBe(true);
    }
    // Una voce che quel piano NON tocca resta agganciabile.
    const previdenza = rows.find((x) => x.field === "sp16f_growth_pct");
    expect(previdenza?.driver).toBe("ricavi");
    expect(previdenza?.code).toBe("sp16f");
  });

  it("l'interruttore previdenza/personale toglie sp16f e sp17f dagli agganciabili", () => {
    const rows = minorFieldsRows(balance(), { sp16f: "ricavi" }, true);
    const sp16f = rows.find((r) => r.field === "sp16f_growth_pct");
    expect(sp16f?.code).toBeNull();
    expect(sp16f?.andamento).toBe("Cresce con il costo del personale");
    expect(sp16f?.agganciata).toBe(true);
    expect(sp16f?.off).toBe(true);
  });

  it("i tre driver, e solo tre", () => {
    expect([...DRIVERS]).toEqual(["ricavi", "acquisti", "personale"]);
  });
});

describe("pianiPregressoOf", () => {
  it("legge i saldi con piano dalla riga del PRIMO anno, dove il motore lo pretende", () => {
    const a: AssumptionsMap = {
      2025: { pregresso: { altri_debiti: { opening: 100, amounts: [100] }, debiti_fornitori: null } },
      2026: {},
    } as unknown as AssumptionsMap;
    expect(pianiPregressoOf(a, [2025, 2026])).toEqual(["altri_debiti"]);
  });

  it("senza piano nessun saldo, e nessuna riga viene spenta per sbaglio", () => {
    expect(pianiPregressoOf({ 2025: {} }, [2025])).toEqual([]);
    expect(pianiPregressoOf({}, [2025])).toEqual([]);
  });
});

describe("spIndexingOf", () => {
  it("legge l'aggancio del primo anno previsto", () => {
    const a: AssumptionsMap = {
      2025: { sp_indexing: { sp16g: "ricavi" } },
      2026: { sp_indexing: { sp16g: "acquisti" } },
    };
    expect(spIndexingOf(a, [2025, 2026])).toEqual({ sp16g: "ricavi" });
  });

  it("assente o null ⇒ mappa vuota, cioe' tutto costante", () => {
    expect(spIndexingOf({ 2025: { sp_indexing: null } }, [2025])).toEqual({});
    expect(spIndexingOf({}, [2025])).toEqual({});
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
