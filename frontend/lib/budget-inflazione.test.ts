import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { applicaInflazioneAlleAuto, inflazioneOf, trendRicaviNota, withInflazione } from "./budget-inflazione";

const anni = [2027, 2028];
const m = (over: Record<number, Record<string, unknown>>): AssumptionsMap => over as unknown as AssumptionsMap;

describe("budget-inflazione", () => {
  it("legge l'inflazione dal primo anno, 2 quando manca", () => {
    expect(inflazioneOf(m({ 2027: { inflation_pct: 3 }, 2028: { inflation_pct: 3 } }), anni)).toBe(3);
    expect(inflazioneOf(m({ 2027: { inflation_pct: null } }), anni)).toBe(2);
    expect(inflazioneOf({}, anni)).toBe(2);
  });
  it("withInflazione scrive ogni anno e riallinea solo le caselle automatiche", () => {
    const out = withInflazione(m({
      2027: { fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 1, fixed_services_growth_auto: false },
      2028: { fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 2, fixed_services_growth_auto: true },
    }), anni, 3.5);
    expect(out[2027]).toMatchObject({ inflation_pct: 3.5, fixed_materials_growth_pct: 3.5, fixed_services_growth_pct: 1 });
    expect(out[2028]).toMatchObject({ inflation_pct: 3.5, fixed_materials_growth_pct: 3.5, fixed_services_growth_pct: 3.5 });
  });
  it("applicaInflazioneAlleAuto restituisce la mappa ricevuta quando nulla cambia", () => {
    const map = m({ 2027: { inflation_pct: 2, fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 2, fixed_services_growth_auto: true } });
    expect(applicaInflazioneAlleAuto(map, [2027])).toBe(map);
  });
  it("la nota sulla tendenza dei ricavi c'e' solo con due anni storici", () => {
    const hist = { 2025: { income: { ce01_ricavi_vendite: "2000" } }, 2026: { income: { ce01_ricavi_vendite: "2120" } } } as never;
    expect(trendRicaviNota([2025, 2026], hist)).toBe("Per riferimento: tendenza storica 2025-2026 dei ricavi +6,0% annuo. Non viene applicata.");
    expect(trendRicaviNota([2026], hist)).toBeNull();
  });
});
