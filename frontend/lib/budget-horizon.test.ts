import { describe, it, expect } from "vitest";
import {
  forecastYearsFor,
  defaultAssumption,
  withDefaultsForYears,
  baseYearNote,
  hydrateAssumptions,
  horizonFromSavedRows,
} from "@/lib/budget-horizon";
import type { BudgetAssumptions } from "@/types/api";

/**
 * Riga `BudgetAssumptions` completa, con tutti i campi valorizzati a un
 * default neutro: serve solo a far compilare i test senza dover ribattere le
 * ~40 proprietà del tipo a ogni caso. `overrides` sostituisce i campi che al
 * test interessano davvero.
 */
function fixtureRow(overrides: Partial<BudgetAssumptions>): BudgetAssumptions {
  return {
    id: 1,
    scenario_id: 1,
    forecast_year: 2026,
    revenue_growth_pct: 0,
    other_revenue_growth_pct: 0,
    variable_materials_growth_pct: 0,
    fixed_materials_growth_pct: 0,
    variable_services_growth_pct: 0,
    fixed_services_growth_pct: 0,
    rent_growth_pct: 0,
    personnel_growth_pct: 0,
    other_costs_growth_pct: 0,
    investments: 0,
    intangible_investments: 0,
    tangible_investments: 0,
    asset_disposal_nbv: null,
    asset_disposal_proceeds: null,
    receivables_short_growth_pct: 0,
    receivables_long_growth_pct: 0,
    payables_short_growth_pct: 0,
    dso_days: null,
    dio_days: null,
    dpo_days: null,
    existing_debt_repayment_years: null,
    altri_finanz_repayment_years: null,
    cash_sweep_enabled: false,
    cash_sweep_min_cash: null,
    tfr_accrual_suspended: false,
    previdenza_scales_with_personnel: false,
    interest_rate_receivables: 0,
    interest_rate_payables: 0,
    tax_rate: 27.9,
    tax_advances_paid: 0,
    tax_temporary_differences: null,
    fixed_materials_percentage: 0,
    fixed_services_percentage: 0,
    depreciation_rate: 20,
    depreciation_rate_intangible: 20,
    financing_amount: 0,
    financing_duration_years: 5,
    financing_interest_rate: 3,
    financing_loans: null,
    sp01_growth_pct: null,
    sp04_growth_pct: null,
    sp06e_growth_pct: null,
    sp06f_growth_pct: null,
    sp08_growth_pct: null,
    sp10_growth_pct: null,
    sp14_growth_pct: null,
    sp16e_growth_pct: null,
    sp16f_growth_pct: null,
    sp16g_growth_pct: null,
    sp17d_growth_pct: null,
    sp17e_growth_pct: null,
    sp17f_growth_pct: null,
    sp17g_growth_pct: null,
    sp18_growth_pct: null,
    sp_overrides: null,
    ce01_override: null,
    ce02_override: null,
    ce03_override: null,
    ce03a_override: null,
    ce04_override: null,
    ce05_override: null,
    ce06_override: null,
    ce07_override: null,
    ce08_override: null,
    ce08a_override: null,
    ce08b_override: null,
    ce08c_override: null,
    ce08d_override: null,
    ce09_override: null,
    ce09a_override: null,
    ce09b_override: null,
    ce09c_override: null,
    ce09d_override: null,
    ce10_override: null,
    ce11_override: null,
    ce11b_override: null,
    ce12_override: null,
    ce13_override: null,
    ce14_override: null,
    ce15_override: null,
    ce16_override: null,
    ce17_override: null,
    ce17a_override: null,
    ce17b_override: null,
    ce18_override: null,
    ce19_override: null,
    ce20_override: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("forecastYearsFor", () => {
  it("elenca gli anni successivi all'anno base", () => {
    expect(forecastYearsFor(2024, 3)).toEqual([2025, 2026, 2027]);
    expect(forecastYearsFor(2024, 5)).toEqual([2025, 2026, 2027, 2028, 2029]);
  });

  it("non produce anni con un orizzonte non valido", () => {
    expect(forecastYearsFor(2024, 0)).toEqual([]);
    expect(forecastYearsFor(2024, -1)).toEqual([]);
    expect(forecastYearsFor(2024, 2.6)).toEqual([2025, 2026]);
  });
});

describe("defaultAssumption", () => {
  it("marca l'anno e l'aliquota reale (IRES + IRAP), non il 24 dello schema", () => {
    const a = defaultAssumption(2026, 17);
    expect(a.forecast_year).toBe(2026);
    expect(a.scenario_id).toBe(17);
    expect(a.tax_rate).toBe(27.9);
  });

  it("senza scenario non inventa un id", () => {
    expect(defaultAssumption(2026).scenario_id).toBeUndefined();
  });

  it("la quota fissa parte dal 40 del motore, non da uno zero che lo scavalca", () => {
    // Uno 0 esplicito BATTE il default della colonna e dello schema (40), e
    // apriva i Costi di uno scenario nuovo con lo slider a 0 % e le righe
    // «parte fissa» gia' spente. Se questi due tornano a zero, si vede qui.
    const a = defaultAssumption(2026, 17);
    expect(a.fixed_materials_percentage).toBe(40);
    expect(a.fixed_services_percentage).toBe(40);
  });
});

describe("withDefaultsForYears", () => {
  it("riempie di default una mappa vuota", () => {
    const out = withDefaultsForYears({}, [2025, 2026, 2027]);
    expect(Object.keys(out).map(Number).sort()).toEqual([2025, 2026, 2027]);
    expect(out[2026].forecast_year).toBe(2026);
  });

  it("allungando l'orizzonte aggiunge gli anni mancanti e NON tocca quelli salvati", () => {
    const salvate = {
      2025: { forecast_year: 2025, revenue_growth_pct: 12 },
      2026: { forecast_year: 2026, revenue_growth_pct: 8 },
      2027: { forecast_year: 2027, revenue_growth_pct: 4 },
    };
    const out = withDefaultsForYears(salvate, [2025, 2026, 2027, 2028, 2029], 17);

    expect(Object.keys(out).map(Number).sort()).toEqual([
      2025, 2026, 2027, 2028, 2029,
    ]);
    expect(out[2025]).toBe(salvate[2025]);
    expect(out[2026].revenue_growth_pct).toBe(8);
    expect(out[2028].revenue_growth_pct).toBe(0);
    expect(out[2029].scenario_id).toBe(17);
  });

  it("restituisce la STESSA mappa quando non manca nulla", () => {
    // È questa identità a fermare l'effetto che riempie i default: senza,
    // `setAssumptions` rende di nuovo e l'effetto riparte da solo.
    const gia = withDefaultsForYears({}, [2025, 2026]);
    expect(withDefaultsForYears(gia, [2025, 2026])).toBe(gia);
    expect(withDefaultsForYears(gia, [2025])).toBe(gia);
  });

  it("accorciando l'orizzonte conserva gli anni fuori range", () => {
    // L'utente che torna da 5 a 3 anni e poi ci ripensa non deve perdere ciò
    // che aveva scritto: a filtrare è il salvataggio, non questa mappa.
    const cinque = withDefaultsForYears({}, [2025, 2026, 2027, 2028, 2029]);
    const tre = withDefaultsForYears(cinque, [2025, 2026, 2027]);
    expect(tre[2029]).toBeDefined();
  });
});

describe("baseYearNote", () => {
  it("dice «ultimo anno disponibile» solo quando lo e' davvero", () => {
    expect(baseYearNote(2026, [2024, 2025, 2026])).toBe("ultimo anno disponibile");
  });

  it("con anni piu' recenti in database dichiara fin dove arriva l'archivio", () => {
    // Era una stringa fissa: uno scenario con base 2025 su un'azienda con il
    // 2026 importato affermava il contrario di cio' che si legge in database.
    // Parla di archivio e non di disponibilita' perche' `years` elenca anche i
    // periodi parziali, che come anno base non si possono usare.
    expect(baseYearNote(2025, [2024, 2025, 2026])).toBe("in archivio fino al 2026");
    expect(baseYearNote(2024, [2024, 2025, 2026])).toBe("in archivio fino al 2026");
  });

  it("tace quando non c'e' niente di vero da dire", () => {
    expect(baseYearNote(2026, [])).toBeNull();
    // Anno base oltre lo storico (startup, o anno cancellato dopo la creazione).
    expect(baseYearNote(2027, [2025, 2026])).toBeNull();
  });
});

describe("hydrateAssumptions", () => {
  // Generato dal codice reale — chiamando `hydrateAssumptions` su una riga
  // con tutti i campi valorizzati e stampando `Object.keys(...).sort()` — non
  // battuto a mano, sullo stesso modello di `ivcee-catalog-parity.test.ts`.
  // NON si aggiorna per far tornare verde la suite: se cambia, un campo e'
  // sparito dalla mappa idratata (o e' stato aggiunto senza aggiornare questo
  // elenco nello stesso commit), ed e' quello il difetto — un campo perso qui
  // cancella un dato dell'utente al primo «Salva e Calcola Previsionale», in
  // silenzio, perche' il bulk e' delete-all + reinsert.
  const CHIAVI_ATTESE = [
    "altri_finanz_repayment_years", "asset_disposal_nbv", "asset_disposal_proceeds",
    "cash_sweep_enabled", "cash_sweep_min_cash", "ce01_override", "ce02_override",
    "ce03_override", "ce03a_override", "ce04_override", "ce05_override", "ce06_override",
    "ce07_override", "ce08_override", "ce08a_override", "ce08b_override", "ce08c_override",
    "ce08d_override", "ce09_override", "ce09a_override", "ce09b_override", "ce09c_override",
    "ce09d_override", "ce10_override", "ce11_override", "ce11b_override", "ce12_override",
    "ce13_override", "ce14_override", "ce15_override", "ce16_override", "ce17_override",
    "ce17a_override", "ce17b_override", "ce18_override", "ce19_override", "ce20_override",
    "depreciation_rate", "depreciation_rate_intangible", "dio_days", "dpo_days", "dso_days",
    "existing_debt_repayment_years", "financing_amount", "financing_duration_years",
    "financing_interest_rate", "financing_loans", "fixed_materials_growth_pct",
    "fixed_materials_percentage", "fixed_services_growth_pct", "fixed_services_percentage",
    "forecast_year", "intangible_investments", "investments", "other_costs_growth_pct",
    "other_revenue_growth_pct", "payables_short_growth_pct", "personnel_growth_pct",
    "previdenza_scales_with_personnel", "receivables_long_growth_pct",
    "receivables_short_growth_pct", "rent_growth_pct", "revenue_growth_pct", "scenario_id",
    "sp01_growth_pct", "sp04_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct",
    "sp08_growth_pct", "sp10_growth_pct", "sp14_growth_pct", "sp16e_growth_pct",
    "sp16f_growth_pct", "sp16g_growth_pct", "sp17d_growth_pct", "sp17e_growth_pct",
    "sp17f_growth_pct", "sp17g_growth_pct", "sp18_growth_pct", "sp_overrides",
    "tangible_investments", "tax_advances_paid", "tax_rate", "tax_temporary_differences",
    "tfr_accrual_suspended", "variable_materials_growth_pct", "variable_services_growth_pct",
  ];

  it("scrive esattamente le 87 chiavi congelate, ordinate", () => {
    expect(CHIAVI_ATTESE.length).toBe(87);
    const out = hydrateAssumptions([fixtureRow({ forecast_year: 2026 })], 1);
    expect(Object.keys(out[2026]).sort()).toEqual([...CHIAVI_ATTESE].sort());
  });

  it("un override sopravvive al salvataggio: round-trip di ce09_override e sp_overrides", () => {
    // Riga in cui SOLO questi due campi sono valorizzati: verifica che il
    // round-trip non li perda ne' li confonda con un default.
    const row = fixtureRow({
      forecast_year: 2026,
      ce09_override: 12345,
      sp_overrides: { sp09_disponibilita_liquide: 999 },
    });
    const out = hydrateAssumptions([row], 1);
    expect(out[2026].ce09_override).toBe(12345);
    expect(out[2026].sp_overrides).toEqual({ sp09_disponibilita_liquide: 999 });
  });

  it("normalizza i tre campi il cui default non e' null", () => {
    // `cash_sweep_enabled` e `tax_advances_paid` sono tipati non-nullable ma
    // possono arrivare `null` dal server; `tax_temporary_differences` puo'
    // arrivare `undefined` se il campo manca nella risposta — da qui il cast.
    const row = {
      ...fixtureRow({ forecast_year: 2026 }),
      cash_sweep_enabled: null,
      tax_advances_paid: null,
      tax_temporary_differences: undefined,
    } as unknown as BudgetAssumptions;
    const out = hydrateAssumptions([row], 1);
    expect(out[2026].cash_sweep_enabled).toBe(false);
    expect(out[2026].tax_advances_paid).toBe(0);
    expect(out[2026].tax_temporary_differences).toBeNull();
  });
});

describe("horizonFromSavedRows", () => {
  it("senza righe salvate resta il default di prodotto, tre anni", () => {
    expect(horizonFromSavedRows([], 2025)).toBe(3);
  });

  it("guarda la DISTANZA dall'ultimo anno salvato, non il numero di righe", () => {
    // Due righe, su base+3 e base+4: contare le righe darebbe 2 e
    // butterebbe via l'anno base+4 al salvataggio successivo — la
    // disallineatura da finestra spostata che questo lotto ha chiuso.
    const rows = [
      fixtureRow({ forecast_year: 2028 }),
      fixtureRow({ forecast_year: 2029 }),
    ];
    expect(horizonFromSavedRows(rows, 2025)).toBe(4);
  });

  it("una riga sola su base+1 da' un orizzonte di 1", () => {
    expect(horizonFromSavedRows([fixtureRow({ forecast_year: 2026 })], 2025)).toBe(1);
  });

  it("una riga degenere sull'anno base da' comunque 1, non 0", () => {
    expect(horizonFromSavedRows([fixtureRow({ forecast_year: 2025 })], 2025)).toBe(1);
  });
});
