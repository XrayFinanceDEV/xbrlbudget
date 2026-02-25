// API Response Types

export interface Company {
  id: number;
  name: string;
  tax_id: string | null;
  sector: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FinancialYear {
  id: number;
  company_id: number;
  year: number;
  created_at: string;
  updated_at: string;
}

export interface BalanceSheet {
  id: number;
  financial_year_id: number;
  sp01_crediti_soci: string;
  sp02_immob_immateriali: string;
  sp03_immob_materiali: string;
  sp04_immob_finanziarie: string;

  // Detailed breakdown - Immobilizzazioni finanziarie
  sp04a_partecipazioni: string;
  sp04b_crediti_immob_breve: string;
  sp04c_crediti_immob_lungo: string;
  sp04d_altri_titoli: string;
  sp04e_strumenti_derivati_attivi: string;

  sp05_rimanenze: string;
  sp06_crediti_breve: string;
  sp07_crediti_lungo: string;
  sp08_attivita_finanziarie: string;
  sp09_disponibilita_liquide: string;
  sp10_ratei_risconti_attivi: string;
  sp11_capitale: string;
  sp12_riserve: string;

  // Detailed breakdown - Patrimonio Netto (Riserve)
  sp12a_riserva_sovrapprezzo: string;
  sp12b_riserve_rivalutazione: string;
  sp12c_riserva_legale: string;
  sp12d_riserve_statutarie: string;
  sp12e_altre_riserve: string;
  sp12f_riserva_copertura_flussi: string;
  sp12g_utili_perdite_portati: string;
  sp12h_riserva_neg_azioni_proprie: string;

  sp13_utile_perdita: string;
  sp14_fondi_rischi: string;
  sp15_tfr: string;
  sp16_debiti_breve: string;
  sp17_debiti_lungo: string;

  // Detailed breakdown - Financial debts
  sp16a_debiti_banche_breve: string;
  sp17a_debiti_banche_lungo: string;
  sp16b_debiti_altri_finanz_breve: string;
  sp17b_debiti_altri_finanz_lungo: string;
  sp16c_debiti_obbligazioni_breve: string;
  sp17c_debiti_obbligazioni_lungo: string;

  // Detailed breakdown - Operating debts
  sp16d_debiti_fornitori_breve: string;
  sp17d_debiti_fornitori_lungo: string;
  sp16e_debiti_tributari_breve: string;
  sp17e_debiti_tributari_lungo: string;
  sp16f_debiti_previdenza_breve: string;
  sp17f_debiti_previdenza_lungo: string;
  sp16g_altri_debiti_breve: string;
  sp17g_altri_debiti_lungo: string;

  sp18_ratei_risconti_passivi: string;
  created_at: string;
  updated_at: string;
  total_assets: number;
  total_equity: number;
  total_liabilities: number;
  fixed_assets: number;
  current_assets: number;
  current_liabilities: number;
  total_debt: number;
  working_capital_net: number;
}

export interface IncomeStatement {
  id: number;
  financial_year_id: number;
  // A) Valore della Produzione
  ce01_ricavi_vendite: string;
  ce02_variazioni_rimanenze: string;
  ce03_lavori_interni: string;
  ce04_altri_ricavi: string;
  // B) Costi della Produzione
  ce05_materie_prime: string;
  ce06_servizi: string;
  ce07_godimento_beni: string;
  ce08_costi_personale: string;
  ce08a_tfr_accrual: string;  // TFR accrual detail
  ce09_ammortamenti: string;  // Total depreciation
  ce09a_ammort_immateriali: string;  // Intangible depreciation
  ce09b_ammort_materiali: string;  // Tangible depreciation
  ce09c_svalutazioni: string;  // Other fixed asset write-downs (c)
  ce09d_svalutazione_crediti: string;  // Receivables write-downs (d)
  ce10_var_rimanenze_mat_prime: string;
  ce11_accantonamenti: string;
  ce11b_altri_accantonamenti: string;  // Other provisions
  ce12_oneri_diversi: string;
  // C) Proventi e Oneri Finanziari
  ce13_proventi_partecipazioni: string;
  ce14_altri_proventi_finanziari: string;
  ce15_oneri_finanziari: string;
  ce16_utili_perdite_cambi: string;
  // D) Rettifiche Attività Finanziarie
  ce17_rettifiche_attivita_fin: string;
  // E) Proventi e Oneri Straordinari
  ce18_proventi_straordinari: string;
  ce19_oneri_straordinari: string;
  // Imposte
  ce20_imposte: string;
  created_at: string;
  updated_at: string;
  // Computed fields
  production_value: number;
  production_cost: number;
  ebitda: number;
  ebit: number;
  financial_result: number;
  extraordinary_result: number;
  profit_before_tax: number;
  net_profit: number;
  revenue: number;
}

// Calculation Response Types

export interface WorkingCapitalMetrics {
  ccln: number;
  ccn: number;
  ms: number;
  mt: number;
}

export interface LiquidityRatios {
  current_ratio: number;
  quick_ratio: number;
  acid_test: number;
}

export interface SolvencyRatios {
  autonomy_index: number;
  leverage_ratio: number;
  debt_to_equity: number;
  debt_to_production: number;
}

export interface ProfitabilityRatios {
  roe: number;
  roi: number;
  ros: number;
  rod: number;
  ebitda_margin: number;
  ebit_margin: number;
  net_margin: number;
}

export interface ActivityRatios {
  asset_turnover: number;
  inventory_turnover_days: number;
  receivables_turnover_days: number;
  payables_turnover_days: number;
  working_capital_days: number;
  cash_conversion_cycle: number;
}

export interface CoverageRatios {
  fixed_assets_coverage_with_equity_and_ltdebt: number;
  fixed_assets_coverage_with_equity: number;
  independence_from_third_parties: number;
}

export interface TurnoverRatios {
  inventory_turnover: number;
  receivables_turnover: number;
  payables_turnover: number;
  working_capital_turnover: number;
  total_assets_turnover: number;
}

export interface ExtendedProfitabilityRatios {
  spread: number;
  financial_leverage_effect: number;
  ebitda_on_sales: number;
  financial_charges_on_revenue: number;
}

export interface EfficiencyRatios {
  revenue_per_employee_cost: number;
  revenue_per_materials_cost: number;
}

export interface BreakEvenAnalysis {
  fixed_costs: number;
  variable_costs: number;
  contribution_margin: number;
  contribution_margin_percentage: number;
  break_even_revenue: number;
  safety_margin: number;
  operating_leverage: number;
  fixed_cost_multiplier: number;
}

export interface AllRatios {
  working_capital: WorkingCapitalMetrics;
  liquidity: LiquidityRatios;
  solvency: SolvencyRatios;
  profitability: ProfitabilityRatios;
  activity: ActivityRatios;
  coverage: CoverageRatios;
  turnover: TurnoverRatios;
  extended_profitability: ExtendedProfitabilityRatios;
  efficiency: EfficiencyRatios;
  break_even: BreakEvenAnalysis;
}

export interface MultiYearRatios {
  company_id: number;
  scenario_id: number;
  base_year: number;
  years: number[];
  ratios: AllRatios[];
}

export interface SummaryMetrics {
  revenue: number;
  ebitda: number;
  ebit: number;
  net_profit: number;
  total_assets: number;
  total_equity: number;
  total_debt: number;
  working_capital: number;
  current_ratio: number;
  roe: number;
  roi: number;
  debt_to_equity: number;
  ebitda_margin: number;
}

export interface AltmanComponents {
  A: number;
  B: number;
  C: number;
  D: number;
  E: number;
}

export interface AltmanResult {
  z_score: number;
  components: AltmanComponents;
  classification: "safe" | "gray_zone" | "distress";
  interpretation_it: string;
  sector: number;
  model_type: "manufacturing" | "services";
}

export interface IndicatorScore {
  code: string;
  name: string;
  value: number;
  points: number;
  max_points: number;
  percentage: number;
}

export interface FGPMIResult {
  total_score: number;
  max_score: number;
  rating_class: number;
  rating_code: string;
  rating_description: string;
  risk_level: string;
  sector_model: string;
  revenue_bonus: number;
  indicators: Record<string, IndicatorScore>;
}

export interface FinancialAnalysis {
  company_id: number;
  year: number;
  sector: number;
  ratios: AllRatios;
  altman: AltmanResult;
  fgpmi: FGPMIResult;
  summary: SummaryMetrics;
}

// Budget Scenarios

export interface BudgetScenario {
  id: number;
  company_id: number;
  name: string;
  base_year: number;
  scenario_type: "budget" | "infrannuale";
  period_months: number | null;
  description: string | null;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export interface BudgetScenarioCreate {
  company_id: number;
  name: string;
  base_year: number;
  scenario_type?: "budget" | "infrannuale";
  period_months?: number;
  description?: string;
  is_active?: number;
}

export interface BudgetScenarioUpdate {
  name?: string;
  base_year?: number;
  scenario_type?: string;
  period_months?: number;
  description?: string;
  is_active?: number;
}

// Intra-Year Comparison Types
export interface IntraYearComparisonItem {
  code: string;
  label: string;
  partial_value: number;
  reference_value: number;
  pct_of_reference: number;
  annualized_value: number;
}

export interface IntraYearComparison {
  partial_year: number;
  reference_year: number;
  period_months: number;
  income_items: IntraYearComparisonItem[];
  balance_items: IntraYearComparisonItem[];
}

export interface BudgetAssumptions {
  id: number;
  scenario_id: number;
  forecast_year: number;
  revenue_growth_pct: number;
  other_revenue_growth_pct: number;
  variable_materials_growth_pct: number;
  fixed_materials_growth_pct: number;
  variable_services_growth_pct: number;
  fixed_services_growth_pct: number;
  rent_growth_pct: number;
  personnel_growth_pct: number;
  other_costs_growth_pct: number;
  investments: number;
  receivables_short_growth_pct: number;
  receivables_long_growth_pct: number;
  payables_short_growth_pct: number;
  interest_rate_receivables: number;
  interest_rate_payables: number;
  tax_rate: number;
  fixed_materials_percentage: number;
  fixed_services_percentage: number;
  depreciation_rate: number;
  financing_amount: number;
  financing_duration_years: number;
  financing_interest_rate: number;
  created_at: string;
  updated_at: string;
}

export interface BudgetAssumptionsCreate {
  scenario_id: number;
  forecast_year: number;
  revenue_growth_pct?: number;
  other_revenue_growth_pct?: number;
  variable_materials_growth_pct?: number;
  fixed_materials_growth_pct?: number;
  variable_services_growth_pct?: number;
  fixed_services_growth_pct?: number;
  rent_growth_pct?: number;
  personnel_growth_pct?: number;
  other_costs_growth_pct?: number;
  investments?: number;
  receivables_short_growth_pct?: number;
  receivables_long_growth_pct?: number;
  payables_short_growth_pct?: number;
  interest_rate_receivables?: number;
  interest_rate_payables?: number;
  tax_rate?: number;
  fixed_materials_percentage?: number;
  fixed_services_percentage?: number;
  depreciation_rate?: number;
  financing_amount?: number;
  financing_duration_years?: number;
  financing_interest_rate?: number;
}

export interface ForecastBalanceSheet {
  id: number;
  forecast_year_id: number;
  sp01_crediti_soci: number;
  sp02_immob_immateriali: number;
  sp03_immob_materiali: number;
  sp04_immob_finanziarie: number;

  // Detailed breakdown - Immobilizzazioni finanziarie
  sp04a_partecipazioni: number;
  sp04b_crediti_immob_breve: number;
  sp04c_crediti_immob_lungo: number;
  sp04d_altri_titoli: number;
  sp04e_strumenti_derivati_attivi: number;

  sp05_rimanenze: number;
  sp06_crediti_breve: number;
  sp07_crediti_lungo: number;
  sp08_attivita_finanziarie: number;
  sp09_disponibilita_liquide: number;
  sp10_ratei_risconti_attivi: number;
  sp11_capitale: number;
  sp12_riserve: number;

  // Detailed breakdown - Patrimonio Netto (Riserve)
  sp12a_riserva_sovrapprezzo: number;
  sp12b_riserve_rivalutazione: number;
  sp12c_riserva_legale: number;
  sp12d_riserve_statutarie: number;
  sp12e_altre_riserve: number;
  sp12f_riserva_copertura_flussi: number;
  sp12g_utili_perdite_portati: number;
  sp12h_riserva_neg_azioni_proprie: number;

  sp13_utile_perdita: number;
  sp14_fondi_rischi: number;
  sp15_tfr: number;
  sp16_debiti_breve: number;
  sp17_debiti_lungo: number;

  // Detailed breakdown - Financial debts
  sp16a_debiti_banche_breve: number;
  sp17a_debiti_banche_lungo: number;
  sp16b_debiti_altri_finanz_breve: number;
  sp17b_debiti_altri_finanz_lungo: number;
  sp16c_debiti_obbligazioni_breve: number;
  sp17c_debiti_obbligazioni_lungo: number;

  // Detailed breakdown - Operating debts
  sp16d_debiti_fornitori_breve: number;
  sp17d_debiti_fornitori_lungo: number;
  sp16e_debiti_tributari_breve: number;
  sp17e_debiti_tributari_lungo: number;
  sp16f_debiti_previdenza_breve: number;
  sp17f_debiti_previdenza_lungo: number;
  sp16g_altri_debiti_breve: number;
  sp17g_altri_debiti_lungo: number;

  sp18_ratei_risconti_passivi: number;
  created_at: string;
  updated_at: string;
  total_assets: number;
  total_equity: number;
  total_liabilities: number;
  fixed_assets: number;
  current_assets: number;
  current_liabilities: number;
  total_debt: number;
  working_capital_net: number;
}

export interface ForecastIncomeStatement {
  id: number;
  forecast_year_id: number;
  ce01_ricavi_vendite: number;
  ce02_variazioni_rimanenze: number;
  ce03_lavori_interni: number;
  ce04_altri_ricavi: number;
  ce05_materie_prime: number;
  ce06_servizi: number;
  ce07_godimento_beni: number;
  ce08_costi_personale: number;
  ce08a_tfr_accrual: number;
  ce09_ammortamenti: number;
  ce09a_ammort_immateriali: number;
  ce09b_ammort_materiali: number;
  ce09c_svalutazioni: number;
  ce09d_svalutazione_crediti: number;
  ce10_var_rimanenze_mat_prime: number;
  ce11_accantonamenti: number;
  ce11b_altri_accantonamenti: number;
  ce12_oneri_diversi: number;
  ce13_proventi_partecipazioni: number;
  ce14_altri_proventi_finanziari: number;
  ce15_oneri_finanziari: number;
  ce16_utili_perdite_cambi: number;
  ce17_rettifiche_attivita_fin: number;
  ce18_proventi_straordinari: number;
  ce19_oneri_straordinari: number;
  ce20_imposte: number;
  created_at: string;
  updated_at: string;
  production_value: number;
  production_cost: number;
  ebitda: number;
  ebit: number;
  financial_result: number;
  extraordinary_result: number;
  profit_before_tax: number;
  net_profit: number;
  revenue: number;
}

export interface ForecastGenerationResult {
  scenario_id: number;
  scenario_name: string;
  base_year: number;
  forecast_years: number[];
  summary: Record<string, {
    total_assets: number;
    total_equity: number;
    total_debt: number;
    working_capital_net: number;
    revenue: number;
    ebitda: number;
    ebit: number;
    net_profit: number;
  }>;
  generated_at: string;
}

// Cash Flow Statement

export interface CashFlowComponents {
  net_profit: number;
  depreciation: number;
  delta_receivables: number;
  delta_inventory: number;
  delta_payables: number;
  operating_cf: number;
  capex: number;
  investing_cf: number;
  delta_debt: number;
  delta_equity: number;
  financing_cf: number;
  total_cf: number;
  actual_cash_change: number;
  cash_beginning: number;
  cash_ending: number;
}

export interface CashFlowRatios {
  ocf_margin: number;
  free_cash_flow: number;
  cash_conversion: number;
  capex_to_operating_cf: number;
}

export interface CashFlowResult {
  year: number;
  components: CashFlowComponents;
  ratios: CashFlowRatios;
}

// ===== Detailed Cash Flow (Italian GAAP - Indirect Method) =====

export interface OperatingActivitiesStart {
  net_profit: number;
  income_taxes: number;
  interest_expense_income: number;
  dividends: number;
  capital_gains_losses: number;
  profit_before_adjustments: number;
}

export interface NonCashAdjustments {
  provisions: number;
  depreciation_amortization: number;
  write_downs: number;
  total: number;
}

export interface WorkingCapitalChanges {
  delta_inventory: number;
  delta_receivables: number;
  delta_payables: number;
  delta_accruals_deferrals_active: number;
  delta_accruals_deferrals_passive: number;
  other_wc_changes: number;
  total: number;
}

export interface CashAdjustments {
  interest_paid_received: number;
  taxes_paid: number;
  dividends_received: number;
  use_of_provisions: number;
  other_cash_changes: number;
  total: number;
}

export interface OperatingActivities {
  start: OperatingActivitiesStart;
  non_cash_adjustments: NonCashAdjustments;
  cashflow_before_wc: number;
  working_capital_changes: WorkingCapitalChanges;
  cashflow_after_wc: number;
  cash_adjustments: CashAdjustments;
  total_operating_cashflow: number;
}

export interface AssetInvestments {
  investments: number;
  disinvestments: number;
  net: number;
}

export interface InvestingActivities {
  tangible_assets: AssetInvestments;
  intangible_assets: AssetInvestments;
  financial_assets: AssetInvestments;
  total_investing_cashflow: number;
}

export interface FinancingSource {
  increases: number;
  decreases: number;
  net: number;
}

export interface FinancingActivities {
  third_party_funds: FinancingSource;
  own_funds: FinancingSource;
  total_financing_cashflow: number;
}

export interface CashReconciliation {
  total_cashflow: number;
  cash_beginning: number;
  cash_ending: number;
  difference: number;
  verification_ok: boolean;
}

export interface DetailedCashFlowStatement {
  year: number;
  operating_activities: OperatingActivities;
  investing_activities: InvestingActivities;
  financing_activities: FinancingActivities;
  cash_reconciliation: CashReconciliation;
}

export interface MultiYearDetailedCashFlow {
  company_id: number;
  scenario_id: number | null;
  base_year: number;
  cashflows: DetailedCashFlowStatement[];
}

// ===== EM-Score =====

export interface EMScoreResult {
  rating: string;
  z_score_used: number;
  description: string;
}

// ===== Scenario Analysis (comprehensive single-call response) =====

export interface ScenarioAnalysisYearData {
  year: number;
  type: "historical" | "forecast";
  balance_sheet: Record<string, number>;
  income_statement: Record<string, number>;
  assumptions?: BudgetAssumptions | null;
}

export interface ScenarioAnalysisYearCalculations {
  altman: AltmanResult;
  fgpmi: FGPMIResult;
  em_score?: EMScoreResult;
  ratios: AllRatios;
}

export interface ScenarioAnalysisCashflowYear {
  year: number;
  base_year: number;
  operating: OperatingActivities;
  investing: InvestingActivities;
  financing: FinancingActivities;
  cash_reconciliation: CashReconciliation;
}

export interface ScenarioAnalysis {
  scenario: {
    id: number;
    name: string;
    base_year: number;
    projection_years: number;
    is_active: boolean;
    company: {
      id: number;
      name: string;
      tax_id: string;
      sector: number;
    };
  };
  historical_years: ScenarioAnalysisYearData[];
  forecast_years: ScenarioAnalysisYearData[];
  calculations: {
    by_year: Record<string, ScenarioAnalysisYearCalculations>;
    cashflow: {
      years: ScenarioAnalysisCashflowYear[];
    };
  };
}
