// Config-driven row definitions for the budget assumptions form.
// Spec: docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md
// A row with fields.length > 1 DUAL-WRITES the same value into every listed
// column (Materie/Servizi %: variable == fixed growth makes the fixed/variable
// split mathematically irrelevant — see forecast_engine.py:220-242).
import type { BalanceSheet, IncomeStatement } from "@/types/api";

export type AssumptionRowDef = {
  key: string;
  label: string;
  tooltip?: string;
  kind: "pct" | "eur" | "years" | "days" | "bool";
  /** columns written; >1 = dual-write the same value into each */
  fields: string[];
  /** CE/BS field rendered in the read-only historical columns */
  historicalField?: string;
  /** when set: show a "personalizzato in Avanzate" badge if
   *  assumptions[divergenceField] !== assumptions[fields[0]] */
  divergenceField?: string;
  /** empty input maps to null instead of 0 (auto/constant semantics) */
  nullable?: boolean;
  /** placeholder shows the auto-derived base-year value */
  autoPlaceholder?: "dso" | "dio" | "dpo";
  step?: string;
  min?: number;
  max?: number;
};

const pct = (over: Partial<AssumptionRowDef>): AssumptionRowDef =>
  ({ kind: "pct", step: "0.1", min: -100, max: 100, ...over } as AssumptionRowDef);

export const ESSENTIAL_ROWS: AssumptionRowDef[] = [
  pct({ key: "ricavi", label: "Ricavi %", historicalField: "ce01_ricavi_vendite",
        fields: ["revenue_growth_pct"],
        tooltip: "Variazione % dei ricavi rispetto all'anno precedente di piano" }),
  pct({ key: "materie", label: "Materie prime %", historicalField: "ce05_materie_prime",
        fields: ["variable_materials_growth_pct", "fixed_materials_growth_pct"],
        divergenceField: "fixed_materials_growth_pct",
        tooltip: "Variazione % dei costi per materie. Quote variabile/fissa distinte in Avanzate" }),
  pct({ key: "servizi", label: "Servizi %", historicalField: "ce06_servizi",
        fields: ["variable_services_growth_pct", "fixed_services_growth_pct"],
        divergenceField: "fixed_services_growth_pct",
        tooltip: "Variazione % dei costi per servizi. Quote variabile/fissa distinte in Avanzate" }),
  pct({ key: "personale", label: "Personale %", historicalField: "ce08_costi_personale",
        fields: ["personnel_growth_pct"] }),
  pct({ key: "altri-costi", label: "Altri costi (oneri diversi) %",
        historicalField: "ce12_oneri_diversi", fields: ["other_costs_growth_pct"] }),
  { key: "capex-mat", label: "Investimenti materiali €", kind: "eur",
    fields: ["tangible_investments"], min: 0, step: "1000" },
  { key: "capex-imm", label: "Investimenti immateriali €", kind: "eur",
    fields: ["intangible_investments"], min: 0, step: "1000" },
  { key: "rimborso-banche", label: "Rimborso debiti bancari (anni)", kind: "years",
    fields: ["existing_debt_repayment_years"], nullable: true, min: 0, max: 30,
    tooltip: "Anni di rimborso del debito bancario esistente. Vuoto = debito costante" },
  { key: "fin-importo", label: "Nuovo finanziamento €", kind: "eur",
    fields: ["financing_amount"], min: 0, step: "1000" },
  { key: "fin-durata", label: "Nuovo finanziamento: durata (anni)", kind: "years",
    fields: ["financing_duration_years"], min: 0, max: 30 },
  pct({ key: "fin-tasso", label: "Nuovo finanziamento: tasso %",
        fields: ["financing_interest_rate"], min: 0, max: 30 }),
];

export const ADVANCED_GROUPS: { title: string; rows: AssumptionRowDef[] }[] = [
  {
    title: "Ricavi e costi — dettaglio",
    rows: [
      pct({ key: "altri-ricavi", label: "Altri ricavi %",
            historicalField: "ce04_altri_ricavi", fields: ["other_revenue_growth_pct"] }),
      pct({ key: "affitti", label: "Godimento beni di terzi %",
            historicalField: "ce07_godimento_beni", fields: ["rent_growth_pct"] }),
      pct({ key: "quota-fissa-mat", label: "% quota fissa materie",
            fields: ["fixed_materials_percentage"], min: 0, max: 100, step: "1",
            tooltip: "Quota di costi materie che NON scala col variabile. Rilevante solo se le due crescite divergono" }),
      pct({ key: "quota-fissa-serv", label: "% quota fissa servizi",
            fields: ["fixed_services_percentage"], min: 0, max: 100, step: "1" }),
      pct({ key: "var-materie", label: "Var. % costi variabili materie",
            fields: ["variable_materials_growth_pct"] }),
      pct({ key: "fix-materie", label: "Var. % costi fissi materie",
            fields: ["fixed_materials_growth_pct"] }),
      pct({ key: "var-servizi", label: "Var. % costi variabili servizi",
            fields: ["variable_services_growth_pct"] }),
      pct({ key: "fix-servizi", label: "Var. % costi fissi servizi",
            fields: ["fixed_services_growth_pct"] }),
    ],
  },
  {
    title: "Capitale circolante",
    rows: [
      { key: "dso", label: "Giorni incasso clienti (DSO)", kind: "days",
        fields: ["dso_days"], nullable: true, autoPlaceholder: "dso", min: 0, max: 365 },
      { key: "dio", label: "Giorni rotazione magazzino (DIO)", kind: "days",
        fields: ["dio_days"], nullable: true, autoPlaceholder: "dio", min: 0, max: 365 },
      { key: "dpo", label: "Giorni pagamento fornitori (DPO)", kind: "days",
        fields: ["dpo_days"], nullable: true, autoPlaceholder: "dpo", min: 0, max: 365 },
      pct({ key: "crediti-oltre", label: "Crediti oltre 12 mesi %",
            fields: ["receivables_long_growth_pct"] }),
    ],
  },
  {
    title: "Stato patrimoniale",
    rows: [
      pct({ key: "sp01", label: "Crediti verso soci %", fields: ["sp01_growth_pct"], nullable: true }),
      pct({ key: "sp04", label: "Immobilizzazioni finanziarie %", fields: ["sp04_growth_pct"], nullable: true }),
      pct({ key: "sp08", label: "Attività finanziarie %", fields: ["sp08_growth_pct"], nullable: true }),
      pct({ key: "sp10", label: "Ratei e risconti attivi %", fields: ["sp10_growth_pct"], nullable: true }),
      pct({ key: "sp14", label: "Fondi per rischi e oneri %", fields: ["sp14_growth_pct"], nullable: true }),
      pct({ key: "sp16e", label: "Debiti tributari entro %", fields: ["sp16e_growth_pct"], nullable: true }),
      pct({ key: "sp16f", label: "Debiti previdenziali entro %", fields: ["sp16f_growth_pct"], nullable: true }),
      pct({ key: "sp16g", label: "Altri debiti entro %", fields: ["sp16g_growth_pct"], nullable: true }),
      pct({ key: "sp17d", label: "Debiti tributari oltre %", fields: ["sp17d_growth_pct"], nullable: true }),
      pct({ key: "sp17e", label: "Debiti previdenziali oltre %", fields: ["sp17e_growth_pct"], nullable: true }),
      pct({ key: "sp17f", label: "Altri debiti oltre %", fields: ["sp17f_growth_pct"], nullable: true }),
      pct({ key: "sp17g", label: "Altri debiti oltre (residuali) %", fields: ["sp17g_growth_pct"], nullable: true }),
      pct({ key: "sp18", label: "Ratei e risconti passivi %", fields: ["sp18_growth_pct"], nullable: true }),
      { key: "cessioni-nbv", label: "Cessioni: valore contabile netto €", kind: "eur",
        fields: ["asset_disposal_nbv"], nullable: true, min: 0, step: "1000" },
      { key: "cessioni-prezzo", label: "Cessioni: corrispettivo €", kind: "eur",
        fields: ["asset_disposal_proceeds"], nullable: true, min: 0, step: "1000" },
      { key: "altri-finanz", label: "Rimborso altri finanziatori (anni)", kind: "years",
        fields: ["altri_finanz_repayment_years"], nullable: true, min: 0, max: 30 },
      pct({ key: "amm-mat", label: "Ammortamento nuovi investimenti materiali %",
            fields: ["depreciation_rate"], min: 0, max: 100, step: "1" }),
      pct({ key: "amm-imm", label: "Ammortamento nuovi investimenti immateriali %",
            fields: ["depreciation_rate_intangible"], min: 0, max: 100, step: "1" }),
      { key: "tfr-inps", label: "TFR versato a INPS/fondi (accantonamento sospeso)",
        kind: "bool", fields: ["tfr_accrual_suspended"] },
      { key: "cash-sweep", label: "Cash sweep (usa cassa in eccesso per rimborsare debito)",
        kind: "bool", fields: ["cash_sweep_enabled"] },
      { key: "cash-sweep-min", label: "Cash sweep: cassa minima €", kind: "eur",
        fields: ["cash_sweep_min_cash"], nullable: true, min: 0, step: "1000" },
    ],
  },
  {
    title: "Fiscale",
    rows: [
      pct({ key: "tax", label: "Aliquota fiscale % (override)",
            fields: ["tax_rate"], min: 0, max: 100,
            tooltip: "Il motore usa l'aliquota EFFETTIVA dell'anno base quando plausibile; questo valore è il fallback" }),
    ],
  },
];

const num = (v: string | number | null | undefined): number =>
  typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0;

/** Effective base-year tax rate (ce20 / PBT), or null when not derivable.
 *  Mirrors the engine's preference (forecast_engine.py:374-390). */
export function computeEffectiveTaxRate(income: IncomeStatement): number | null {
  const vp = num(income.ce01_ricavi_vendite) + num(income.ce02_variazioni_rimanenze)
    + num(income.ce03_lavori_interni) + num(income.ce03a_incrementi_immobilizzazioni)
    + num(income.ce04_altri_ricavi);
  const costs = num(income.ce05_materie_prime) + num(income.ce06_servizi)
    + num(income.ce07_godimento_beni) + num(income.ce08_costi_personale)
    + num(income.ce09_ammortamenti) + num(income.ce10_var_rimanenze_mat_prime)
    + num(income.ce11_accantonamenti) + num(income.ce12_oneri_diversi);
  const fin = num(income.ce13_proventi_partecipazioni) + num(income.ce14_altri_proventi_finanziari)
    - num(income.ce15_oneri_finanziari) + num(income.ce16_utili_perdite_cambi)
    + num(income.ce17_rettifiche_attivita_fin)
    + num(income.ce18_proventi_straordinari) - num(income.ce19_oneri_straordinari);
  const pbt = vp - costs + fin;
  const tax = num(income.ce20_imposte);
  if (pbt <= 0 || tax <= 0) return null;
  const rate = (tax / pbt) * 100;
  return rate > 0 && rate <= 60 ? Math.round(rate * 10) / 10 : null;
}

/** Auto-derived turnover days from the base year — same formulas the engine
 *  applies when the field is NULL (forecast_engine.py:487-505). */
export function computeAutoDays(
  kind: "dso" | "dio" | "dpo",
  income: IncomeStatement | undefined,
  balance: BalanceSheet | undefined,
): number | null {
  if (!income || !balance) return null;
  const revenue = num(income.ce01_ricavi_vendite);
  const purchases = num(income.ce05_materie_prime) + num(income.ce06_servizi);
  let numerator = 0;
  let denominator = 0;
  if (kind === "dso") { numerator = num(balance.sp06_crediti_breve); denominator = revenue; }
  if (kind === "dio") { numerator = num(balance.sp05_rimanenze); denominator = revenue; }
  if (kind === "dpo") { numerator = num(balance.sp16d_debiti_fornitori_breve); denominator = purchases; }
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 360);
}
