/** I sette passi del percorso ipotesi (spec 2026-09-08 §4). Modulo puro. */
export type WizardStepKey =
  | "scenario" | "fatturato" | "costi" | "altre-voci-ce"
  | "circolante" | "pregresso-nuovo" | "imposte";

export interface WizardStep {
  n: number; key: WizardStepKey; title: string; subtitle: string;
  group: "Impostazione" | "Conto economico" | "Stato patrimoniale";
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { n: 1, key: "scenario", title: "Scenario", subtitle: "nome, anno base, orizzonte", group: "Impostazione" },
  { n: 2, key: "fatturato", title: "Fatturato", subtitle: "ricavi e altri ricavi", group: "Conto economico" },
  { n: 3, key: "costi", title: "Costi principali", subtitle: "quota fissa e variabile", group: "Conto economico" },
  { n: 4, key: "altre-voci-ce", title: "Altre voci CE", subtitle: "voci minori e automatiche", group: "Conto economico" },
  { n: 5, key: "circolante", title: "Capitale circolante", subtitle: "giorni medi", group: "Stato patrimoniale" },
  { n: 6, key: "pregresso-nuovo", title: "Pregresso e nuovo", subtitle: "debiti, finanziamenti, investimenti", group: "Stato patrimoniale" },
  { n: 7, key: "imposte", title: "Imposte", subtitle: "aliquota e pagamento", group: "Stato patrimoniale" },
];

export const STEP_FIELDS: Record<WizardStepKey, readonly string[]> = {
  scenario: [],
  fatturato: ["revenue_growth_pct", "other_revenue_growth_pct"],
  costi: [
    "fixed_materials_percentage", "fixed_services_percentage",
    "variable_materials_growth_pct", "variable_services_growth_pct",
    "fixed_materials_growth_pct", "fixed_services_growth_pct",
    "personnel_growth_pct", "rent_growth_pct",
  ],
  "altre-voci-ce": ["other_costs_growth_pct"],
  circolante: [
    "dso_days", "dio_days", "dpo_days", "receivables_long_growth_pct",
    "sp01_growth_pct", "sp04_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct",
    "sp08_growth_pct", "sp10_growth_pct", "sp14_growth_pct", "sp16f_growth_pct",
    "sp16g_growth_pct", "sp17d_growth_pct", "sp17f_growth_pct", "sp17g_growth_pct",
    "sp18_growth_pct", "previdenza_scales_with_personnel", "tfr_accrual_suspended",
  ],
  "pregresso-nuovo": [
    "existing_debt_repayment_years", "altri_finanz_repayment_years", "financing_loans",
    "financing_amount", "financing_duration_years", "financing_interest_rate",
    "tangible_investments", "intangible_investments",
    "depreciation_rate", "depreciation_rate_intangible",
    "asset_disposal_nbv", "asset_disposal_proceeds", "cash_sweep_enabled", "cash_sweep_min_cash",
  ],
  imposte: ["tax_rate", "tax_advances_paid", "tax_temporary_differences", "sp16e_growth_pct", "sp17e_growth_pct"],
};

/** Colonne che il motore non legge: idratate e rispedite, mai mostrate. */
export const DEAD_FIELDS = [
  "investments", "receivables_short_growth_pct", "payables_short_growth_pct",
  "interest_rate_receivables", "interest_rate_payables",
] as const;

export interface WizardStepGroup { group: WizardStep["group"]; steps: WizardStep[] }

/** Raggruppa per identita' di `group`, non per vicinanza nell'elenco: due
 *  passi con lo stesso `group` finiscono nello stesso gruppo anche se un
 *  passo di un altro gruppo li separa. L'ordine dei gruppi e' quello della
 *  prima comparsa. */
export function groupWizardSteps(steps: readonly WizardStep[]): WizardStepGroup[] {
  const byGroup = new Map<WizardStep["group"], WizardStep[]>();
  for (const step of steps) {
    const existing = byGroup.get(step.group);
    if (existing) existing.push(step);
    else byGroup.set(step.group, [step]);
  }
  return Array.from(byGroup, ([group, groupSteps]) => ({ group, steps: groupSteps }));
}

export function primaryLabel(step: WizardStepKey): string {
  return step === "imposte" ? "Salva e calcola previsionale" : "Avanti";
}

export function stepForErrorMessage(message: string): WizardStepKey {
  return /unfunded financing requirement/i.test(message) ? "pregresso-nuovo" : "imposte";
}

export function stepStorageKey(scenarioId: number): string {
  return `budget-wizard-step:${scenarioId}`;
}

const ORDER = WIZARD_STEPS.map((s) => s.key);

export function nextStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i >= 0 && i < ORDER.length - 1 ? ORDER[i + 1] : null;
}

export function prevStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i > 0 ? ORDER[i - 1] : null;
}
