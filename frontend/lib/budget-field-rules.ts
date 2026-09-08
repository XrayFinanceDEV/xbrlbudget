// Per-field validation rules for the budget assumptions form. One entry per
// scalar field written by ESSENTIAL_ROWS / ADVANCED_GROUPS in
// components/budget/assumption-rows.ts, so kind/min/max/step/nullable exist
// exactly once and both the form rows and the wizard steps read from here.
export interface FieldRule {
  kind: "pct" | "eur" | "years" | "days" | "bool";
  min?: number;
  max?: number;
  step?: string;
  nullable?: boolean;
}

const pct = (over: Partial<FieldRule> = {}): FieldRule =>
  ({ kind: "pct", step: "0.1", min: -100, max: 100, ...over });

const eur = (over: Partial<FieldRule> = {}): FieldRule =>
  ({ kind: "eur", min: 0, step: "1000", ...over });

const years = (over: Partial<FieldRule> = {}): FieldRule =>
  ({ kind: "years", nullable: true, min: 0, max: 30, ...over });

const days = (over: Partial<FieldRule> = {}): FieldRule =>
  ({ kind: "days", nullable: true, min: 0, max: 365, ...over });

const bool: FieldRule = { kind: "bool" };

export const FIELD_RULES: Record<string, FieldRule> = {
  // Ricavi e costi
  revenue_growth_pct: pct(),
  other_revenue_growth_pct: pct(),
  variable_materials_growth_pct: pct(),
  fixed_materials_growth_pct: pct(),
  variable_services_growth_pct: pct(),
  fixed_services_growth_pct: pct(),
  fixed_materials_percentage: pct({ min: 0, max: 100, step: "1" }),
  fixed_services_percentage: pct({ min: 0, max: 100, step: "1" }),
  personnel_growth_pct: pct(),
  rent_growth_pct: pct(),
  other_costs_growth_pct: pct(),

  // Capitale circolante
  dso_days: days(),
  dio_days: days(),
  dpo_days: days(),
  receivables_long_growth_pct: pct(),

  // Stato patrimoniale — voci minori (crescita, vuoto = costante)
  sp01_growth_pct: pct({ nullable: true }),
  sp04_growth_pct: pct({ nullable: true }),
  sp06e_growth_pct: pct({ nullable: true }),
  sp06f_growth_pct: pct({ nullable: true }),
  sp08_growth_pct: pct({ nullable: true }),
  sp10_growth_pct: pct({ nullable: true }),
  sp14_growth_pct: pct({ nullable: true }),
  sp16e_growth_pct: pct({ nullable: true }),
  sp16f_growth_pct: pct({ nullable: true }),
  sp16g_growth_pct: pct({ nullable: true }),
  sp17d_growth_pct: pct({ nullable: true }),
  sp17e_growth_pct: pct({ nullable: true }),
  sp17f_growth_pct: pct({ nullable: true }),
  sp17g_growth_pct: pct({ nullable: true }),
  sp18_growth_pct: pct({ nullable: true }),

  // Pregresso e nuovo: debiti, finanziamenti, investimenti
  existing_debt_repayment_years: years(),
  altri_finanz_repayment_years: years(),
  financing_amount: eur(),
  financing_duration_years: years(),
  financing_interest_rate: pct({ min: 0, max: 30 }),
  tangible_investments: eur(),
  intangible_investments: eur(),
  depreciation_rate: pct({ min: 0, max: 100, step: "1" }),
  depreciation_rate_intangible: pct({ min: 0, max: 100, step: "1" }),
  asset_disposal_nbv: eur({ nullable: true }),
  asset_disposal_proceeds: eur({ nullable: true }),
  cash_sweep_enabled: bool,
  cash_sweep_min_cash: eur({ nullable: true }),
  tfr_accrual_suspended: bool,
  previdenza_scales_with_personnel: bool,

  // Imposte
  tax_rate: pct({ min: 0, max: 100 }),
  tax_advances_paid: eur(),
};

/** "" -> null se il campo e' nullable, altrimenti 0; virgola accettata; clamp min/max. */
export function parseFieldValue(field: string, raw: string): number | null {
  const rule = FIELD_RULES[field] ?? { kind: "pct" };
  const t = raw.trim();
  if (t === "") return rule.nullable ? null : 0;
  const n = parseFloat(t.replace(",", "."));
  if (Number.isNaN(n)) return rule.nullable ? null : 0;
  const lo = rule.min ?? -Infinity, hi = rule.max ?? Infinity;
  return Math.min(hi, Math.max(lo, n));
}
