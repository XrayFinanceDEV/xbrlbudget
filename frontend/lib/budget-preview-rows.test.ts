import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import type { HistoricalData } from "@/lib/budget-trend";
import { computeAutoDays } from "@/lib/budget-turnover";
import {
  rowsAltreVociCe, rowsAnnoBase, rowsCircolante, rowsCosti, rowsFatturato, rowsImposte, rowsPregressoNuovo,
  unfundedFromError,
} from "./budget-preview-rows";

const baseInc = {
  ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "50", ce05_materie_prime: "400",
  ce06_servizi: "200", ce07_godimento_beni: "30", ce08_costi_personale: "150",
  ce12_oneri_diversi: "20", ce09_ammortamenti: "40", ce15_oneri_finanziari: "10", ce20_imposte: "30",
} as unknown as IncomeStatement;

const year = (y: number, over: Partial<Record<string, number>> = {}): ForecastPreviewYear => ({
  year: y,
  income_statement: {
    ce01_ricavi_vendite: 1100, ce04_altri_ricavi: 50, ce05_materie_prime: 430, ce06_servizi: 210,
    ce07_godimento_beni: 30, ce08_costi_personale: 155, ce12_oneri_diversi: 20, ce09_ammortamenti: 40,
    ce15_oneri_finanziari: 10, ce20_imposte: 33, ...over,
  },
  balance_sheet: { sp16d_debiti_fornitori_breve: 140, sp09_disponibilita_liquide: 80,
    sp16a_debiti_banche_breve: 20, sp17a_debiti_banche_lungo: 100, sp17b_debiti_altri_finanz_lungo: 0,
    sp16b_debiti_altri_finanz_breve: 0, sp16c_debiti_obbligazioni_breve: 0, sp17c_debiti_obbligazioni_lungo: 0,
    sp16e_debiti_tributari_breve: 33 },
  details: { ce05_fixed: 130, ce05_variable: 300, ce06_fixed: 120, ce06_variable: 90,
    dso_applied: 60, dio_applied: 45, dpo_applied: 78 },
});

describe("rowsFatturato", () => {
  it("ricavi con variazione % sull'anno precedente e cumulata sul base", () => {
    const rows = rowsFatturato(baseInc, [year(2027), year(2028, { ce01_ricavi_vendite: 1210 })]);
    const ricavi = rows.find((r) => r.key === "ce01")!;
    expect(ricavi.base.value).toBe(1000);
    expect(ricavi.years[0]).toMatchObject({ value: 1100, pct: 10 });
    expect(ricavi.years[1]).toMatchObject({ value: 1210, pct: 10 });
    expect(rows.find((r) => r.key === "cumulata")!.years[1].pct).toBeCloseTo(21, 5);
  });
});

describe("rowsCosti", () => {
  it("totale = somma delle quattro voci, fissi + variabili = materie + servizi, % sui ricavi", () => {
    const rows = rowsCosti(baseInc, { materials: 32.5, services: 60 }, [year(2027)]);
    const tot = rows.find((r) => r.key === "principali")!;
    expect(tot.years[0].value).toBe(430 + 210 + 30 + 155);
    expect(tot.years[0].pct).toBeCloseTo((825 / 1100) * 100, 6);
    expect(rows.find((r) => r.key === "fissi")!.years[0].value).toBe(130 + 120 + 155 + 30);
    expect(rows.find((r) => r.key === "variabili")!.years[0].value).toBe(300 + 90);
    // base: quote dallo slider
    expect(rows.find((r) => r.key === "fissi")!.base.value).toBe(400 * 0.325 + 200 * 0.6 + 150 + 30);
    expect(rows.find((r) => r.key === "mol")!.years[0].value).toBe(1100 + 50 - 825 - 20);
  });
  it("con override i componenti sono null e la riga lo dice", () => {
    const y = year(2027); y.details.ce05_fixed = null; y.details.ce05_variable = null;
    const rows = rowsCosti(baseInc, { materials: 40, services: 40 }, [y]);
    expect(rows.find((r) => r.key === "fissi")!.years[0].value).toBeNull();
    expect(rows.find((r) => r.key === "fissi")!.years[0].note).toBe("forzato in CE Prev.");
  });
});

// Fixture con tre delle undici voci minori non nulle e di segno diverso, cosi' la
// formula canonica (usata da ceAggregates/rowsImposte/rowsAltreVociCe) e quella
// semplificata che c'era prima del fix danno numeri diversi:
//   canonica:     vp=1180 (1100+30+50), costs=900 (430+210+30+155+40+0+15+20), fin=-20 (-10-10)
//                 ebt = 1180 - 900 - 20 = 260
//   semplificata: vp0=1150 (1100+50), main=825, alt0=20 (solo ce12), mol=305, amm=40, ro=265,
//                 of=10 -> ebt = 265 - 10 = 255
// La differenza (5) e' esattamente ce02+ce03+ce03a-ce10-ce11+ce13+ce14+ce16+ce17+ce18-ce19
// = 30 - 15 - 10 = 5.
const minoriOver = { ce02_variazioni_rimanenze: 30, ce11_accantonamenti: 15, ce18_proventi_straordinari: -10 };
const EBT_CANONICO = 260;
const EBT_SEMPLIFICATO = 255;

describe("rowsImposte — formula canonica, non quella semplificata", () => {
  it("imposte e utile netto", () => {
    const rows = rowsImposte(baseInc, [year(2027)]);
    expect(rows.find((r) => r.key === "ce20")!.years[0].value).toBe(-33);
  });
  it("ebt/net con le voci minori non nulle usano la formula canonica", () => {
    const rows = rowsImposte(baseInc, [year(2027, minoriOver)]);
    const ebt = rows.find((r) => r.key === "ebt")!.years[0].value;
    const net = rows.find((r) => r.key === "net")!.years[0].value;
    expect(ebt).toBe(EBT_CANONICO);
    expect(ebt).not.toBe(EBT_SEMPLIFICATO);
    expect(net).toBe(EBT_CANONICO - 33);
  });
  it("years: [] non lancia e non produce righe d'anno", () => {
    const rows = rowsImposte(baseInc, []);
    expect(rows.every((r) => r.years.length === 0)).toBe(true);
  });
});

describe("rowsAltreVociCe", () => {
  it("ebt e' quello canonico, diverso dal semplificato, con le voci minori non nulle", () => {
    const rows = rowsAltreVociCe(baseInc, [year(2027, minoriOver)]);
    expect(rows.find((r) => r.key === "ebt")!.years[0].value).toBe(EBT_CANONICO);
    expect(rows.find((r) => r.key === "ebt")!.years[0].value).not.toBe(EBT_SEMPLIFICATO);
  });
  it("la cascata vp + main + alt + amm + fin somma esattamente a ebt (segni delle righe)", () => {
    const rows = rowsAltreVociCe(baseInc, [year(2027, minoriOver)]);
    const val = (key: string) => rows.find((r) => r.key === key)!.years[0].value!;
    expect(val("vp") + val("main") + val("alt") + val("amm") + val("fin")).toBeCloseTo(val("ebt"), 6);
    // e vale anche sulla colonna base
    const valBase = (key: string) => rows.find((r) => r.key === key)!.base.value!;
    expect(valBase("vp") + valBase("main") + valBase("alt") + valBase("amm") + valBase("fin"))
      .toBeCloseTo(valBase("ebt"), 6);
  });
  it("years: [] non lancia e non produce righe d'anno", () => {
    const rows = rowsAltreVociCe(baseInc, []);
    expect(rows.every((r) => r.years.length === 0)).toBe(true);
  });
});

describe("rowsCircolante", () => {
  it("CCN, quota sui ricavi, assorbimento di cassa — letterali verificabili a mano", () => {
    const baseBs = {
      sp06_crediti_breve: "300", sp06e_crediti_tributari_breve: "50",
      sp06f_imposte_anticipate_breve: "10", sp05_rimanenze: "120", sp16d_debiti_fornitori_breve: "180",
    } as unknown as BalanceSheet;
    // bCred = 300-50-10=240, bMag=120, bForn=180 -> bCcn = 240+120-180 = 180
    const y = year(2027, { ce01_ricavi_vendite: 1200 });
    Object.assign(y.balance_sheet, {
      sp06_crediti_breve: 330, sp06e_crediti_tributari_breve: 40,
      sp06f_imposte_anticipate_breve: 20, sp05_rimanenze: 150, sp16d_debiti_fornitori_breve: 200,
    });
    // cred = 330-40-20=270, mag=150, forn=200 -> ccn = 270+150-200 = 220
    const rows = rowsCircolante(baseBs, baseInc, [y]);
    expect(rows.find((r) => r.key === "crediti")!.base.value).toBe(240);
    expect(rows.find((r) => r.key === "crediti")!.years[0].value).toBe(270);
    expect(rows.find((r) => r.key === "rimanenze")!.years[0].value).toBe(150);
    expect(rows.find((r) => r.key === "fornitori")!.years[0].value).toBe(-200);
    expect(rows.find((r) => r.key === "ccn")!.base.value).toBe(180);
    expect(rows.find((r) => r.key === "ccn")!.years[0].value).toBe(220);
    expect(rows.find((r) => r.key === "ccn-pct")!.years[0].pct).toBeCloseTo((220 / 1200) * 100, 6);
    // assorbimento di cassa = -(ccn - ccn_precedente) = -(220 - 180) = -40
    expect(rows.find((r) => r.key === "cassa")!.years[0].value).toBe(-40);
  });
});

describe("rowsPregressoNuovo / unfundedFromError", () => {
  it("PFN = debiti finanziari - cassa", () => {
    const rows = rowsPregressoNuovo({ sp09_disponibilita_liquide: "50", sp16a_debiti_banche_breve: "30",
      sp17a_debiti_banche_lungo: "120" } as unknown as BalanceSheet, [year(2027)]);
    expect(rows.find((r) => r.key === "pfn")!.years[0].value).toBe(20 + 100 - 80);
  });
  it("estrae anno e importo dal messaggio del motore", () => {
    expect(unfundedFromError({ year: 2028, message: "Unfunded financing requirement 84,120.50: add ..." }))
      .toEqual({ year: 2028, amount: 84120.5 });
    expect(unfundedFromError({ year: null, message: "altro" })).toBeNull();
  });
  it("year non nullo ma messaggio senza importo riconoscibile -> null, non lancia", () => {
    expect(unfundedFromError({ year: 2028, message: "Errore generico senza importo" })).toBeNull();
  });
});

describe("rowsAnnoBase", () => {
  const inc2023 = {
    ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "50", ce05_materie_prime: "400",
    ce06_servizi: "200", ce07_godimento_beni: "30", ce08_costi_personale: "150", ce12_oneri_diversi: "20",
  } as unknown as IncomeStatement;
  const bal2023 = {
    sp05_rimanenze: "120", sp06_crediti_breve: "300", sp06e_crediti_tributari_breve: "50",
    sp06f_imposte_anticipate_breve: "10", sp16d_debiti_fornitori_breve: "180",
  } as unknown as BalanceSheet;
  const inc2024 = {
    ...inc2023, ce01_ricavi_vendite: "1100", ce05_materie_prime: "430",
  } as unknown as IncomeStatement;
  const bal2024 = { ...bal2023, sp06_crediti_breve: "330" } as unknown as BalanceSheet;
  const historical: HistoricalData = {
    2023: { income: inc2023, balance: bal2023 },
    2024: { income: inc2024, balance: bal2024 },
  };

  it("[] senza anni storici, e non lancia", () => {
    expect(rowsAnnoBase([], historical)).toEqual([]);
  });

  it("il primo anno storico fa da colonna base, il resto (anno base incluso) da colonne years", () => {
    const rows = rowsAnnoBase([2023, 2024], historical);
    const ricavi = rows.find((r) => r.key === "ricavi")!;
    expect(ricavi.base.value).toBe(1000);
    expect(ricavi.years).toEqual([{ value: 1100 }]);
  });

  it("incidenza % di ce05/ce06/ce08 sui ricavi dello stesso anno", () => {
    const rows = rowsAnnoBase([2023, 2024], historical);
    const ce05 = rows.find((r) => r.key === "ce05")!;
    expect(ce05.base).toMatchObject({ value: 400, pct: 40 });
    expect(ce05.years[0].value).toBe(430);
    expect(ce05.years[0].pct).toBeCloseTo((430 / 1100) * 100, 6);
  });

  it("MOL = ce01+ce04-ce05-ce06-ce07-ce08-ce12", () => {
    const rows = rowsAnnoBase([2023, 2024], historical);
    const mol = rows.find((r) => r.key === "mol")!;
    expect(mol.base.value).toBe(1000 + 50 - 400 - 200 - 30 - 150 - 20);
    expect(mol.years[0].value).toBe(1100 + 50 - 430 - 200 - 30 - 150 - 20);
  });

  it("giorni DSO/DIO/DPO sono quelli di computeAutoDays, valore assente", () => {
    const rows = rowsAnnoBase([2023, 2024], historical);
    const dso = rows.find((r) => r.key === "dso")!;
    expect(dso.base.value).toBeNull();
    expect(dso.base.days).toBe(computeAutoDays("dso", inc2023, bal2023));
    expect(dso.years[0].days).toBe(computeAutoDays("dso", inc2024, bal2024));
    const dio = rows.find((r) => r.key === "dio")!;
    expect(dio.base.days).toBe(computeAutoDays("dio", inc2023, bal2023));
    const dpo = rows.find((r) => r.key === "dpo")!;
    expect(dpo.base.days).toBe(computeAutoDays("dpo", inc2023, bal2023));
  });

  it("un solo anno storico: base valorizzata, years vuote su ogni riga", () => {
    const rows = rowsAnnoBase([2023], historical);
    expect(rows.every((r) => r.years.length === 0)).toBe(true);
    expect(rows.find((r) => r.key === "ricavi")!.base.value).toBe(1000);
  });

  it("anno storico senza dati in `historical` -> celle nulle, non lancia", () => {
    const rows = rowsAnnoBase([2023, 2099], historical);
    const ricavi = rows.find((r) => r.key === "ricavi")!;
    expect(ricavi.years[0].value).toBeNull();
    const dso = rows.find((r) => r.key === "dso")!;
    expect(dso.years[0]).toEqual({ value: null, days: null });
  });
});
