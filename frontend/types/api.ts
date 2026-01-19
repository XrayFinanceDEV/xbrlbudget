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
  sp05_rimanenze: string;
  sp06_crediti_breve: string;
  sp07_crediti_lungo: string;
  sp08_attivita_finanziarie: string;
  sp09_disponibilita_liquide: string;
  sp10_ratei_risconti_attivi: string;
  sp11_capitale: string;
  sp12_riserve: string;
  sp13_utile_perdita: string;
  sp14_fondi_rischi: string;
  sp15_tfr: string;
  sp16_debiti_breve: string;
  sp17_debiti_lungo: string;
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
  ce01_ricavi_vendite: string;
  ce02_variazioni_rimanenze: string;
  ce03_lavori_interni: string;
  ce04_altri_ricavi: string;
  ce05_materie_prime: string;
  ce06_servizi: string;
  ce07_godimento_beni: string;
  ce08_costi_personale: string;
  ce09_ammortamenti: string;
  ce10_var_rimanenze_mat_prime: string;
  ce11_accantonamenti: string;
  ce12_oneri_diversi: string;
  ce13_proventi_partecipazioni: string;
  ce14_altri_proventi_finanziari: string;
  ce15_oneri_finanziari: string;
  ce16_utili_perdite_cambi: string;
  ce17_rettifiche_attivita_fin: string;
  ce18_proventi_straordinari: string;
  ce19_oneri_straordinari: string;
  ce20_imposte: string;
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

export interface AllRatios {
  working_capital: WorkingCapitalMetrics;
  liquidity: LiquidityRatios;
  solvency: SolvencyRatios;
  profitability: ProfitabilityRatios;
  activity: ActivityRatios;
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
  description: string | null;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export interface BudgetScenarioCreate {
  company_id: number;
  name: string;
  base_year: number;
  description?: string;
  is_active?: number;
}

export interface BudgetScenarioUpdate {
  name?: string;
  base_year?: number;
  description?: string;
  is_active?: number;
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
  sp05_rimanenze: number;
  sp06_crediti_breve: number;
  sp07_crediti_lungo: number;
  sp08_attivita_finanziarie: number;
  sp09_disponibilita_liquide: number;
  sp10_ratei_risconti_attivi: number;
  sp11_capitale: number;
  sp12_riserve: number;
  sp13_utile_perdita: number;
  sp14_fondi_rischi: number;
  sp15_tfr: number;
  sp16_debiti_breve: number;
  sp17_debiti_lungo: number;
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
  ce09_ammortamenti: number;
  ce10_var_rimanenze_mat_prime: number;
  ce11_accantonamenti: number;
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
