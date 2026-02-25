import axios from 'axios';
import type {
  Company,
  FinancialYear,
  BalanceSheet,
  IncomeStatement,
  AllRatios,
  SummaryMetrics,
  AltmanResult,
  FGPMIResult,
  FinancialAnalysis,
} from '@/types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || (typeof window !== 'undefined' ? '/api/v1' : 'http://localhost:8000/api/v1');

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Auth token management
let _authToken: string | null = null;

export function setAuthToken(token: string | null) {
  _authToken = token;
}

// Request interceptor: add Bearer token
api.interceptors.request.use((config) => {
  if (_authToken) {
    config.headers.Authorization = `Bearer ${_authToken}`;
  }
  return config;
});

// Response interceptor: request new token on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined' && window.parent !== window) {
      window.parent.postMessage({ type: 'REQUEST_AUTH_TOKEN' }, '*');
    }
    return Promise.reject(error);
  }
);

// Companies
export const getCompanies = async (): Promise<Company[]> => {
  const { data } = await api.get<Company[]>('/companies');
  return data;
};

export const getCompany = async (id: number): Promise<Company> => {
  const { data } = await api.get<Company>(`/companies/${id}`);
  return data;
};

export const createCompany = async (company: {
  name: string;
  tax_id?: string;
  sector: number;
  notes?: string;
}): Promise<Company> => {
  const { data } = await api.post<Company>('/companies', company);
  return data;
};

export const updateCompany = async (
  id: number,
  data: { name?: string; tax_id?: string; sector?: number; notes?: string }
): Promise<Company> => {
  const { data: result } = await api.put<Company>(`/companies/${id}`, data);
  return result;
};

export const deleteCompany = async (id: number): Promise<void> => {
  await api.delete(`/companies/${id}`);
};

// Financial Years
export const getCompanyYears = async (companyId: number): Promise<number[]> => {
  const { data } = await api.get<number[]>(`/companies/${companyId}/years`);
  return data;
};

export const getFinancialYear = async (
  companyId: number,
  year: number
): Promise<FinancialYear> => {
  const { data } = await api.get<FinancialYear>(
    `/companies/${companyId}/years/${year}`
  );
  return data;
};

// Financial Statements
export const getBalanceSheet = async (
  companyId: number,
  year: number
): Promise<BalanceSheet> => {
  const { data} = await api.get<BalanceSheet>(
    `/companies/${companyId}/years/${year}/balance-sheet`
  );
  return data;
};

export const getIncomeStatement = async (
  companyId: number,
  year: number
): Promise<IncomeStatement> => {
  const { data } = await api.get<IncomeStatement>(
    `/companies/${companyId}/years/${year}/income-statement`
  );
  return data;
};

// Calculations
export const getSummaryMetrics = async (
  companyId: number,
  year: number
): Promise<SummaryMetrics> => {
  const { data } = await api.get<SummaryMetrics>(
    `/companies/${companyId}/years/${year}/calculations/summary`
  );
  return data;
};

export const getAllRatios = async (
  companyId: number,
  year: number
): Promise<AllRatios> => {
  const { data } = await api.get<AllRatios>(
    `/companies/${companyId}/years/${year}/calculations/ratios`
  );
  return data;
};

export const getAltmanZScore = async (
  companyId: number,
  year: number
): Promise<AltmanResult> => {
  const { data } = await api.get<AltmanResult>(
    `/companies/${companyId}/years/${year}/calculations/altman`
  );
  return data;
};

export const getFGPMIRating = async (
  companyId: number,
  year: number
): Promise<FGPMIResult> => {
  const { data } = await api.get<FGPMIResult>(
    `/companies/${companyId}/years/${year}/calculations/fgpmi`
  );
  return data;
};

export const getCompleteAnalysis = async (
  companyId: number,
  year: number
): Promise<FinancialAnalysis> => {
  const { data } = await api.get<FinancialAnalysis>(
    `/companies/${companyId}/years/${year}/calculations/complete`
  );
  return data;
};

export const getMultiYearRatios = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').MultiYearRatios> => {
  const { data } = await api.get<import('@/types/api').MultiYearRatios>(
    `/companies/${companyId}/scenarios/${scenarioId}/ratios`
  );
  return data;
};

// Import APIs
export interface ReconciliationAdjustment {
  xbrl_total: number;
  imported_sum: number;
  adjustment: number;
  applied_to: string;
}

export interface ReconciliationInfo {
  aggregate_totals?: Record<string, number>;
  reconciliation_adjustments?: Record<string, ReconciliationAdjustment>;
  unmapped_tags?: Array<{ tag: string; value: number }>;
}

export interface XBRLImportResult {
  success: boolean;
  taxonomy_version: string;
  years: number[];
  company_id: number;
  company_name: string;
  tax_id: string;
  financial_year_ids: number[];
  contexts_found: number;
  years_imported: number;
  company_created: boolean;
  reconciliation_info?: Record<number, ReconciliationInfo>;
}

export interface CSVImportResult {
  success: boolean;
  balance_sheet_type: string;
  years: number[];
  rows_processed: number;
  balance_sheet_fields_imported: number;
  income_statement_fields_imported: number;
  financial_year_ids: number[];
}

export const importXBRL = async (
  file: File,
  companyId?: number | null,
  createCompany: boolean = true,
  sector?: number,
  periodMonths?: number
): Promise<XBRLImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  if (companyId !== null && companyId !== undefined) {
    params.append('company_id', companyId.toString());
  }
  params.append('create_company', createCompany.toString());
  if (sector) {
    params.append('sector', sector.toString());
  }
  if (periodMonths) {
    params.append('period_months', periodMonths.toString());
  }

  const { data } = await api.post<XBRLImportResult>(
    `/import/xbrl?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return data;
};

export const importCSV = async (
  file: File,
  companyId: number,
  year1?: number,
  year2?: number
): Promise<CSVImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  params.append('company_id', companyId.toString());
  if (year1) params.append('year1', year1.toString());
  if (year2) params.append('year2', year2.toString());

  const { data } = await api.post<CSVImportResult>(
    `/import/csv?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return data;
};

export interface PDFImportResult {
  success: boolean;
  company_id: number;
  company_name: string;
  fiscal_year: number;
  balance_sheet_id: number;
  income_statement_id: number;
  format: string;
  confidence_score: number;
  extraction_time_seconds: number;
  message: string;
  warnings: string[];
  prior_year_imported?: boolean;
  prior_fiscal_year?: number | null;
}

export const importPDF = async (
  file: File,
  fiscalYear: number,
  companyName?: string,
  companyId?: number | null,
  createCompany: boolean = true,
  sector?: number,
  periodMonths?: number
): Promise<PDFImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  params.append('fiscal_year', fiscalYear.toString());
  params.append('create_company', createCompany.toString());

  if (companyId !== null && companyId !== undefined) {
    params.append('company_id', companyId.toString());
  }

  if (companyName) {
    params.append('company_name', companyName);
  }

  if (sector) {
    params.append('sector', sector.toString());
  }

  if (periodMonths) {
    params.append('period_months', periodMonths.toString());
  }

  const { data } = await api.post<PDFImportResult>(
    `/import/pdf?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300000, // 5 minutes for PDF processing (Docling model loading + extraction)
    }
  );
  return data;
};

// Budget Scenarios
export const getBudgetScenarios = async (companyId: number): Promise<import('@/types/api').BudgetScenario[]> => {
  const { data } = await api.get<import('@/types/api').BudgetScenario[]>(
    `/companies/${companyId}/scenarios`
  );
  return data;
};

export const getBudgetScenario = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').BudgetScenario> => {
  const { data } = await api.get<import('@/types/api').BudgetScenario>(
    `/companies/${companyId}/scenarios/${scenarioId}`
  );
  return data;
};

export const createBudgetScenario = async (
  companyId: number,
  scenario: import('@/types/api').BudgetScenarioCreate
): Promise<import('@/types/api').BudgetScenario> => {
  const { data } = await api.post<import('@/types/api').BudgetScenario>(
    `/companies/${companyId}/scenarios`,
    scenario
  );
  return data;
};

export const updateBudgetScenario = async (
  companyId: number,
  scenarioId: number,
  updates: import('@/types/api').BudgetScenarioUpdate
): Promise<import('@/types/api').BudgetScenario> => {
  const { data } = await api.put<import('@/types/api').BudgetScenario>(
    `/companies/${companyId}/scenarios/${scenarioId}`,
    updates
  );
  return data;
};

export const deleteBudgetScenario = async (
  companyId: number,
  scenarioId: number
): Promise<void> => {
  await api.delete(`/companies/${companyId}/scenarios/${scenarioId}`);
};

// Budget Assumptions
export const getBudgetAssumptions = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').BudgetAssumptions[]> => {
  const { data } = await api.get<import('@/types/api').BudgetAssumptions[]>(
    `/companies/${companyId}/scenarios/${scenarioId}/assumptions`
  );
  return data;
};

export const createBudgetAssumptions = async (
  companyId: number,
  scenarioId: number,
  assumptions: import('@/types/api').BudgetAssumptionsCreate
): Promise<import('@/types/api').BudgetAssumptions> => {
  const { data } = await api.post<import('@/types/api').BudgetAssumptions>(
    `/companies/${companyId}/scenarios/${scenarioId}/assumptions`,
    assumptions
  );
  return data;
};

export const updateBudgetAssumptions = async (
  companyId: number,
  scenarioId: number,
  year: number,
  updates: Partial<import('@/types/api').BudgetAssumptionsCreate>
): Promise<import('@/types/api').BudgetAssumptions> => {
  const { data } = await api.put<import('@/types/api').BudgetAssumptions>(
    `/companies/${companyId}/scenarios/${scenarioId}/assumptions/${year}`,
    updates
  );
  return data;
};

export const deleteBudgetAssumptions = async (
  companyId: number,
  scenarioId: number,
  year: number
): Promise<void> => {
  await api.delete(`/companies/${companyId}/scenarios/${scenarioId}/assumptions/${year}`);
};

// Forecast Generation
export const generateForecast = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').ForecastGenerationResult> => {
  const { data } = await api.post<import('@/types/api').ForecastGenerationResult>(
    `/companies/${companyId}/scenarios/${scenarioId}/generate`
  );
  return data;
};

// Forecast Data
export const getForecastBalanceSheet = async (
  companyId: number,
  scenarioId: number,
  year: number
): Promise<import('@/types/api').ForecastBalanceSheet> => {
  const { data } = await api.get<import('@/types/api').ForecastBalanceSheet>(
    `/companies/${companyId}/scenarios/${scenarioId}/forecasts/${year}/balance-sheet`
  );
  return data;
};

export const getForecastIncomeStatement = async (
  companyId: number,
  scenarioId: number,
  year: number
): Promise<import('@/types/api').ForecastIncomeStatement> => {
  const { data } = await api.get<import('@/types/api').ForecastIncomeStatement>(
    `/companies/${companyId}/scenarios/${scenarioId}/forecasts/${year}/income-statement`
  );
  return data;
};

export const getForecastReclassifiedData = async (
  companyId: number,
  scenarioId: number
): Promise<any> => {
  const { data } = await api.get<any>(
    `/companies/${companyId}/scenarios/${scenarioId}/reclassified`
  );
  return data;
};

// Cash Flow
export const getCashFlow = async (
  companyId: number,
  year: number
): Promise<import('@/types/api').CashFlowResult> => {
  const { data } = await api.get<import('@/types/api').CashFlowResult>(
    `/companies/${companyId}/years/${year}/calculations/cashflow`
  );
  return data;
};

export const getCashFlowMultiYear = async (
  companyId: number
): Promise<import('@/types/api').CashFlowResult[]> => {
  const { data } = await api.get<import('@/types/api').CashFlowResult[]>(
    `/companies/${companyId}/calculations/cashflow`
  );
  return data;
};

// Detailed Cash Flow (Italian GAAP)
export const getDetailedCashFlow = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').MultiYearDetailedCashFlow> => {
  const { data } = await api.get<import('@/types/api').MultiYearDetailedCashFlow>(
    `/companies/${companyId}/scenarios/${scenarioId}/detailed-cashflow`
  );
  return data;
};

export const getDetailedCashFlowHistorical = async (
  companyId: number,
  startYear: number,
  endYear: number
): Promise<import('@/types/api').MultiYearDetailedCashFlow> => {
  const { data } = await api.get<import('@/types/api').MultiYearDetailedCashFlow>(
    `/companies/${companyId}/detailed-cashflow?start_year=${startYear}&end_year=${endYear}`
  );
  return data;
};

// Intra-Year Comparison
export const getIntraYearComparison = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').IntraYearComparison> => {
  const { data } = await api.get<import('@/types/api').IntraYearComparison>(
    `/companies/${companyId}/scenarios/${scenarioId}/comparison`
  );
  return data;
};

// Bulk Assumptions (used by both budget and infrannuale)
export const bulkUpsertAssumptions = async (
  companyId: number,
  scenarioId: number,
  payload: { assumptions: Record<string, unknown>[]; auto_generate: boolean }
): Promise<{ success: boolean; forecast_generated: boolean; forecast_years: number[] }> => {
  const { data } = await api.put(
    `/companies/${companyId}/scenarios/${scenarioId}/assumptions`,
    payload
  );
  return data;
};

// Promote Infrannuale Projection
export interface PromoteResult {
  success: boolean;
  financial_year_id: number;
  year: number;
  company_id: number;
  message: string;
}

export const promoteProjection = async (
  companyId: number,
  scenarioId: number
): Promise<PromoteResult> => {
  const { data } = await api.post<PromoteResult>(
    `/companies/${companyId}/scenarios/${scenarioId}/promote`
  );
  return data;
};

// Scenario Analysis (comprehensive single-call)
export const getScenarioAnalysis = async (
  companyId: number,
  scenarioId: number
): Promise<import('@/types/api').ScenarioAnalysis> => {
  const { data } = await api.get<import('@/types/api').ScenarioAnalysis>(
    `/companies/${companyId}/scenarios/${scenarioId}/analysis`
  );
  return data;
};

// PDF Report Download
export const downloadReportPDF = async (
  companyId: number,
  scenarioId: number,
  companyName?: string
): Promise<void> => {
  const response = await api.get(
    `/companies/${companyId}/scenarios/${scenarioId}/report/pdf`,
    { responseType: 'blob' }
  );

  // Create download link
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;

  // Extract filename from Content-Disposition header or build one
  const contentDisposition = response.headers['content-disposition'];
  let filename = 'report.pdf';
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="?([^"]+)"?/);
    if (match) filename = match[1];
  } else if (companyName) {
    filename = `${companyName.replace(/\s+/g, '_')}_Analisi.pdf`;
  }

  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export default api;
