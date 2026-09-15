import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear } from "@/types/api";
import {
  annoLibero, avvisiFidi, nuoviFinanziamenti, nuovoPrestito, regimeEsplicito, regoleVociMinori, riepilogoNuovo,
  rowsAltriCreditiDebiti, rowsDebitoCassaPfn, tfrRighe, withNuovoCampo,
} from "./budget-piano-step";

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap => m as unknown as AssumptionsMap;
const anni = [2027, 2028, 2029];
const y = (year: number, over: Record<string, unknown> = {}): ForecastPreviewYear => ({
  year,
  income_statement: { ce01_ricavi_vendite: 2500000, ce04_altri_ricavi: 35000, ce05_materie_prime: 1000000, ce06_servizi: 430000, ce07_godimento_beni: 86000, ce08_costi_personale: 620000, ce12_oneri_diversi: 41000 },
  balance_sheet: { sp16a_debiti_banche_breve: 262500, sp17a_debiti_banche_lungo: 565000, sp16b_debiti_altri_finanz_breve: 50000, sp17b_debiti_altri_finanz_lungo: 100000, sp02_immob_immateriali: 20000, sp03_immob_materiali: 1200000, sp09_disponibilita_liquide: 130000, sp06g_crediti_altri_breve: 48000, sp10_ratei_risconti_attivi: 12000, sp06e_crediti_tributari_breve: 18000, sp16f_debiti_previdenza_breve: 28000, sp16g_altri_debiti_breve: 45000, sp14_fondi_rischi: 20000, sp18_ratei_risconti_passivi: 10000 },
  details: {
    tfr: { apertura: 160000, accantonamento: 32148.15, liquidazioni: year === 2028 ? 50000 : 0, chiusura: 192148.15, sospeso: false },
    debito_bancario: { fidi: { apertura: 90000, variazione_ricavi: 0, rimborso_sweep: 0, residuo: 90000, regola: "costante" }, pregresso_senza_piano: null, pregresso_piano_anni: null,
      contratti: [
        { indice: 0, anno: 2027, nome: "Mutuo Intesa 2022", tasso: 3.8, erogato: 0, residuo_iniziale: 330000, rimborso: 82500, interessi: 12540, breve: 82500, lungo: 165000 },
        { indice: 1, anno: 2027, nome: "Nuovo finanziamento BPM", tasso: 4.5, erogato: 500000, residuo_iniziale: 0, rimborso: 0, interessi: 0, breve: 100000, lungo: 400000 },
      ] },
    altri_finanziatori: { apertura: 150000, rimborso: 0, interessi: 0, breve: 50000, lungo: 100000, mode: "contratti", contratti: [] },
    scoperto_residuo: 0,
    ...over,
  } as never,
} as unknown as ForecastPreviewYear);
const bs = { sp16a_debiti_banche_breve: "172500", sp17a_debiti_banche_lungo: "467500", sp16b_debiti_altri_finanz_breve: "0", sp17b_debiti_altri_finanz_lungo: "150000", sp02_immob_immateriali: "30000", sp03_immob_materiali: "1150000", sp09_disponibilita_liquide: "118000", sp15_tfr: "160000", sp06g_crediti_altri_breve: "48000", sp10_ratei_risconti_attivi: "12000", sp06e_crediti_tributari_breve: "18000", sp16f_debiti_previdenza_breve: "28000", sp16g_altri_debiti_breve: "45000", sp14_fondi_rischi: "20000", sp18_ratei_risconti_passivi: "10000" } as unknown as BalanceSheet;
const resp = (years: ForecastPreviewYear[], error: ForecastPreviewResponse["error"] = null): ForecastPreviewResponse => ({ scenario_id: 1, base_year: 2026, forecast_years: years, error });

describe("budget-piano-step", () => {
  it("tfrRighe legge i details e marca oltre il fondo", () => {
    const map = asMap({ 2027: { tfr_payments: 0 }, 2028: { tfr_payments: 50000 }, 2029: { tfr_payments: 300000 } });
    const errore = { year: 2029, message: "Liquidazioni TFR 2029: 300.000,00 superano il fondo disponibile (224.296,30); correggi al passo «Patrimoniale piano»" };
    const righe = tfrRighe(map, anni, resp([y(2027), y(2028)], errore));
    expect(righe[0]).toEqual({ year: 2027, accantonamento: 32148.15, liquidazione: 0, chiusura: 192148.15, oltre: false, sospeso: false });
    expect(righe[1].liquidazione).toBe(50000);
    expect(righe[2]).toMatchObject({ year: 2029, accantonamento: null, chiusura: null, liquidazione: 300000, oltre: true });
  });
  it("nuovi finanziamenti: per anno, con anno libero e riepilogo", () => {
    const map = asMap({ 2027: { financing_loans: [{ name: "Nuovo finanziamento BPM", amount: 500000, opening_residual: 0, duration_years: 6, grace_years: 1, interest_rate: 4.5, balloon_pct: 0 }, { name: "Mutuo", amount: 0, opening_residual: 330000, interest_rate: 3.8, repayments: [] }] }, 2028: {}, 2029: {} });
    const nf = nuoviFinanziamenti(map, anni);
    expect(nf.map((n) => [n.year, n.index, n.loan.name])).toEqual([[2027, 0, "Nuovo finanziamento BPM"]]);
    expect(riepilogoNuovo(nf[0].loan, 2027)).toBe("500.000 € · 2027 · rata 100.000 €/anno dal 2029");
    expect(annoLibero(anni, nf)).toBe(2028);
    expect(nuovoPrestito(2028)).toEqual({ name: "Nuovo finanziamento", amount: 200000, opening_residual: 0, duration_years: 5, grace_years: 0, interest_rate: 4.5, balloon_pct: 0 });
  });
  it("rowsDebitoCassaPfn: una riga per componente, una per nuovo finanziamento col nome", () => {
    const rows = rowsDebitoCassaPfn(bs, 90000, [y(2027)]);
    expect(rows.map((r) => r.key)).toEqual(["fidi", "contratti", "nuovo-1", "scoperto", "altri", "tfr-liq", "immob", "cassa", "pfn", "pfn-mol"]);
    expect(rows.find((r) => r.key === "nuovo-1")?.label).toBe("Nuovo finanziamento BPM");
    expect(rows.find((r) => r.key === "nuovo-1")?.years[0].value).toBe(500000);
    expect(rows.find((r) => r.key === "contratti")?.years[0].value).toBe(247500);
    expect(rows.find((r) => r.key === "pfn")?.years[0].value).toBe(262500 + 565000 + 50000 + 100000 - 130000);
    expect(rows.find((r) => r.key === "fidi")?.base.value).toBe(90000);
  });
  it("regole delle voci minori e tabella altri crediti e debiti", () => {
    // sp_indexing usa il codice corto della voce (spIndexingOf/MINOR_FIELDS,
    // lib/budget-circolante-step.ts), mai il nome pieno del campo SP: e' cosi'
    // che il motore lo legge davvero (calculations/forecast_engine.py,
    // `_sp_scale('sp16g', ...)`). Il piano scriveva qui la chiave sbagliata
    // (`sp16g_altri_debiti_breve`), che con la convenzione vera non avrebbe
    // mai fatto scattare "segue i ricavi": corretto nell'oracolo, dichiarato
    // nel commit e nel rapporto del task.
    const map = asMap({ 2027: { sp16f_growth_pct: 2, sp_indexing: { sp16g: "ricavi" }, previdenza_scales_with_personnel: false }, 2028: {} });
    const regole = regoleVociMinori(map, [2027, 2028]);
    expect(regole.sp16f_debiti_previdenza_breve).toBe("variazione +2,0%");
    expect(regole.sp16g_altri_debiti_breve).toBe("segue i ricavi");
    expect(regole.sp14_fondi_rischi).toBe("costante");
    const rows = rowsAltriCreditiDebiti(bs, [y(2027)], regole);
    expect(rows.map((r) => r.key)).toEqual(["h-attivo", "sp06g", "sp10", "sp06e", "tot-attivo", "h-passivo", "sp16f", "sp16g", "sp14", "sp18", "tot-passivo", "cassa"]);
    expect(rows.find((r) => r.key === "cassa")?.years[0].value).toBe((28000 + 45000 + 20000 + 10000 - 103000) - (48000 + 12000 + 18000 - 78000));
  });
  it("withNuovoCampo aggiorna solo l'indice indicato", () => {
    const loans = [nuovoPrestito(2027), { ...nuovoPrestito(2028), name: "Secondo" }];
    const next = withNuovoCampo(loans, 1, "amount", 300000);
    expect(next[0]).toEqual(loans[0]);
    expect(next[1].amount).toBe(300000);
    expect(next[1].name).toBe("Secondo");
  });
  it("regimeEsplicito: bank_lines_amount non nullo sulla riga del primo anno", () => {
    expect(regimeEsplicito(asMap({ 2027: { bank_lines_amount: 0 } }), 2027)).toBe(true);
    expect(regimeEsplicito(asMap({ 2027: { bank_lines_amount: 90000 } }), 2027)).toBe(true);
    expect(regimeEsplicito(asMap({ 2027: { bank_lines_amount: null } }), 2027)).toBe(false);
    expect(regimeEsplicito(asMap({ 2027: {} }), 2027)).toBe(false);
  });
  it("avvisiFidi: raccoglie il solo avviso dichiarato dal motore, anno per anno", () => {
    const anno2027 = y(2027, { avviso_fidi: "Nel 2027 il piano usa 120.000 € di fidi e anticipi, 30.000 € oltre i 90.000 € del bilancio di partenza: servono affidamenti in più." });
    const anno2028 = y(2028, { avviso_fidi: null });
    expect(avvisiFidi([anno2027, anno2028])).toEqual([anno2027.details.avviso_fidi]);
    expect(avvisiFidi([anno2028])).toEqual([]);
  });
});
