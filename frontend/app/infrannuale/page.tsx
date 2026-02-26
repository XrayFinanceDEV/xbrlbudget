"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import {
  importXBRL,
  importPDF,
  getCompanies,
  getCompanyYears,
  createBudgetScenario,
  bulkUpsertAssumptions,
  getIntraYearComparison,
  getScenarioAnalysis,
  getBudgetScenarios,
  promoteProjection,
  deleteCompany,
} from "@/lib/api";
import axios from "axios";
import type {
  Company,
  BudgetScenario,
  IntraYearComparison,
  IntraYearComparisonItem,
  ScenarioAnalysis,
} from "@/types/api";
import { toast } from "sonner";
import {
  Upload,
  ArrowRight,
  ArrowLeft,
  BarChart3,
  Building2,
  FileText,
  Loader2,
  Check,
  Printer,
  Trash2,
  TrendingUp,
  TrendingDown,
  GitCompareArrows,
  LineChart,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const MONTH_LABELS: Record<number, string> = {
  1: "1 mese (31/01)",
  2: "2 mesi (28/02)",
  3: "3 mesi (31/03)",
  4: "4 mesi (30/04)",
  5: "5 mesi (31/05)",
  6: "6 mesi (30/06)",
  7: "7 mesi (31/07)",
  8: "8 mesi (31/08)",
  9: "9 mesi (30/09)",
  10: "10 mesi (31/10)",
  11: "11 mesi (30/11)",
  12: "12 mesi (31/12)",
};

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria",
  2: "Commercio",
  3: "Servizi",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

// Key P&L items the user can override
const EDITABLE_CE_CODES = [
  "ce01_ricavi_vendite",
  "ce04_altri_ricavi",
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce09_ammortamenti",
  "ce12_oneri_diversi",
];

// Key BS items the user can override (informational, not directly editable in v1)
const KEY_BS_CODES = [
  "sp05_rimanenze",
  "sp06_crediti_breve",
  "sp09_disponibilita_liquide",
  "sp16_debiti_breve",
  "sp17_debiti_lungo",
];

function formatEuro(value: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

// Format number with Italian thousand separators (4.246.479) for input display
function formatInputNumber(value: string): string {
  const raw = value.replace(/[^\d-]/g, "");
  if (!raw || raw === "-") return raw;
  const num = parseInt(raw, 10);
  if (isNaN(num)) return raw;
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(num);
}

// Parse Italian-formatted number back to plain digits
function parseInputNumber(formatted: string): string {
  return formatted.replace(/\./g, "");
}

// Codes that make up EBITDA: VP items are positive, cost items are negative
const VP_CODES = ["ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi"];
const EBITDA_COST_CODES = [
  "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale", "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi",
];

// Always show these rows even when both values are zero
const ALWAYS_SHOW_CODES = new Set([
  "ce20_imposte", "_ebitda", "_ebitda_pct", "_net_profit",
  "_totale_attivo", "_totale_passivo",
  // CE section headers and subtotals
  "_hdr_a", "_hdr_b", "_hdr_c", "_hdr_d", "_hdr_e",
  "_totale_vp", "_totale_cp", "_ebit",
  "_totale_fin", "_totale_straord", "_profit_before_tax",
  // BS section headers and subtotals
  "_hdr_attivo", "_hdr_immob", "_hdr_circ", "_hdr_passivo", "_hdr_pn", "_hdr_debiti",
  "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza",
]);

// BS codes: sp01-sp10 = Attivo, sp11-sp18 = Passivo
const ATTIVO_CODES = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
];
const PASSIVO_CODES = [
  "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
  "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve",
  "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
];

// ===== INDICATOR COMPUTATION =====

function safeDivide(a: number, b: number): number {
  return b !== 0 ? a / b : 0;
}

interface IndicatorSet {
  dscr: number;
  ebitda_margin: number;
  mt: number;
  ccn: number;
  current_ratio: number;
  ms: number;
  copertura_immob: number;
  indipendenza: number;
  pfn: number;
  pfn_ebitda: number;
  roi: number;
  roe: number;
  ros: number;
  of_mol: number;
  // Internal fields for scoring
  _ebitda_raw: number;
  _quick_ratio: number;
  _equity_over_fixed: number;
}

// Linear interpolation score: 0 at `low`, 1 at `high`, clamped [0,1]
function linearScore(value: number, low: number, high: number): number {
  if (value <= low) return 0;
  if (value >= high) return 1;
  return (value - low) / (high - low);
}

// Score where lower values are better (inverted)
function invertedScore(value: number, goodBelow: number, badAbove: number): number {
  return 1 - linearScore(value, goodBelow, badAbove);
}

function computeIndicators(
  bs: Record<string, number>,
  is_: Record<string, number>,
): IndicatorSet {
  const v = (obj: Record<string, number>, key: string) => obj[key] || 0;

  // P&L aggregates
  const revenue = v(is_, "ce01_ricavi_vendite");
  const vp =
    revenue +
    v(is_, "ce02_variazioni_rimanenze") +
    v(is_, "ce03_lavori_interni") +
    v(is_, "ce04_altri_ricavi");
  const opCosts =
    v(is_, "ce05_materie_prime") +
    v(is_, "ce06_servizi") +
    v(is_, "ce07_godimento_beni") +
    v(is_, "ce08_costi_personale") +
    v(is_, "ce10_var_rimanenze_mat_prime") +
    v(is_, "ce11_accantonamenti") +
    v(is_, "ce11b_altri_accantonamenti") +
    v(is_, "ce12_oneri_diversi");
  const ebitda = vp - opCosts;
  const depreciation = v(is_, "ce09_ammortamenti");
  const ebit = ebitda - depreciation;
  const oneriFinanziari = v(is_, "ce15_oneri_finanziari");
  const imposte = v(is_, "ce20_imposte");

  // Net profit
  const financialIncome =
    v(is_, "ce13_proventi_partecipazioni") +
    v(is_, "ce14_altri_proventi_finanziari") +
    v(is_, "ce16_utili_perdite_cambi");
  const extraResult =
    v(is_, "ce18_proventi_straordinari") -
    v(is_, "ce19_oneri_straordinari");
  const netProfit =
    ebit -
    oneriFinanziari +
    financialIncome +
    extraResult +
    v(is_, "ce17_rettifiche_attivita_fin") -
    imposte;

  // BS aggregates
  const fixedAssets =
    v(bs, "sp02_immob_immateriali") +
    v(bs, "sp03_immob_materiali") +
    v(bs, "sp04_immob_finanziarie");
  const inventory = v(bs, "sp05_rimanenze");
  const cash = v(bs, "sp09_disponibilita_liquide");
  const financialAssets = v(bs, "sp08_attivita_finanziarie");
  const currentAssets =
    inventory +
    v(bs, "sp06_crediti_breve") +
    financialAssets +
    cash +
    v(bs, "sp10_ratei_risconti_attivi");
  const totalAssets = v(bs, "sp01_crediti_soci") + fixedAssets + currentAssets;
  const equity =
    v(bs, "sp11_capitale") +
    v(bs, "sp12_riserve") +
    v(bs, "sp13_utile_perdita");
  const currentLiabilities = v(bs, "sp16_debiti_breve");
  const longTermDebt = v(bs, "sp17_debiti_lungo");

  // PFN: use detailed financial debt if available, else total debts
  const financialDebtShort =
    v(bs, "sp16a_debiti_banche_breve") +
    v(bs, "sp16b_debiti_altri_finanz_breve") +
    v(bs, "sp16c_debiti_obbligazioni_breve");
  const financialDebtLong =
    v(bs, "sp17a_debiti_banche_lungo") +
    v(bs, "sp17b_debiti_altri_finanz_lungo") +
    v(bs, "sp17c_debiti_obbligazioni_lungo");
  const hasDetailedDebt = financialDebtShort > 0 || financialDebtLong > 0;
  const totalFinancialDebt = hasDetailedDebt
    ? financialDebtShort + financialDebtLong
    : currentLiabilities + longTermDebt;
  const pfn = totalFinancialDebt - cash - financialAssets;

  // DSCR = (EBITDA - Imposte) / Oneri finanziari
  const dscr = safeDivide(ebitda - imposte, oneriFinanziari);

  return {
    dscr,
    ebitda_margin: safeDivide(ebitda, revenue) * 100,
    mt: currentAssets - inventory - currentLiabilities,
    ccn: currentAssets - currentLiabilities,
    current_ratio: safeDivide(currentAssets, currentLiabilities),
    ms: equity - fixedAssets,
    copertura_immob: safeDivide(equity + longTermDebt, fixedAssets) * 100,
    indipendenza: safeDivide(equity, totalAssets) * 100,
    pfn,
    pfn_ebitda: safeDivide(pfn, ebitda),
    roi: safeDivide(ebit, totalAssets) * 100,
    roe: safeDivide(netProfit, equity) * 100,
    ros: safeDivide(ebit, revenue) * 100,
    of_mol: safeDivide(oneriFinanziari, ebitda) * 100,
    _ebitda_raw: ebitda,
    _quick_ratio: safeDivide(currentAssets - inventory, currentLiabilities),
    _equity_over_fixed: safeDivide(equity, fixedAssets) * 100,
  };
}

// Score each indicator 0-1 based on Italian banking/CNDCEC practice
function scoreIndicator(
  key: keyof IndicatorSet,
  ind: IndicatorSet,
): number {
  switch (key) {
    // DSCR: <1 crisis (CNDCEC), 1-1.2 grey zone, >1.2 good, >1.5 solid
    case "dscr":
      return linearScore(ind.dscr, 1.0, 1.5);
    // EBITDA margin: <5% concerning, >20% excellent
    case "ebitda_margin":
      return linearScore(ind.ebitda_margin, 5, 20);
    // MT: scored via quick ratio - <0.8 critical, >1.3 solid
    case "mt":
      return linearScore(ind._quick_ratio, 0.8, 1.3);
    // CCN: scored via current ratio
    case "ccn":
      return linearScore(ind.current_ratio, 0.8, 1.5);
    // Current ratio: <0.8 critical, >1.5 solid
    case "current_ratio":
      return linearScore(ind.current_ratio, 0.8, 1.5);
    // MS: scored via equity/fixed assets - 50% weak, 120% strong
    case "ms":
      return linearScore(ind._equity_over_fixed, 50, 120);
    // Copertura: <80% critical, >150% solid
    case "copertura_immob":
      return linearScore(ind.copertura_immob, 80, 150);
    // Indipendenza: <15% fragile, >50% optimal
    case "indipendenza":
      return linearScore(ind.indipendenza, 15, 50);
    // PFN: scored via PFN/EBITDA (lower is better)
    case "pfn":
      if (ind._ebitda_raw <= 0 && ind.pfn > 0) return 0;
      return invertedScore(ind.pfn_ebitda, 0, 6);
    // PFN/EBITDA: <=0 great (no net debt), >6 critical (BCE threshold)
    case "pfn_ebitda":
      if (ind._ebitda_raw <= 0 && ind.pfn > 0) return 0;
      return invertedScore(ind.pfn_ebitda, 0, 6);
    // ROI: <0 loss, >12% good
    case "roi":
      return linearScore(ind.roi, 0, 12);
    // ROE: <0 loss, >12% good
    case "roe":
      return linearScore(ind.roe, 0, 12);
    // ROS: <0 loss, >10% good
    case "ros":
      return linearScore(ind.ros, 0, 10);
    // OF/MOL: <5% excellent, >30% critical (inverted)
    case "of_mol":
      if (ind._ebitda_raw <= 0) return ind.of_mol > 0 ? 0 : 0.5;
      return invertedScore(ind.of_mol, 5, 30);
    default:
      return 0.5;
  }
}

const INDICATOR_DEFS: Array<{
  key: keyof IndicatorSet;
  label: string;
  format: "euro" | "pct" | "ratio";
}> = [
  { key: "dscr", label: "DSCR", format: "ratio" },
  { key: "ebitda_margin", label: "EBITDA %", format: "pct" },
  { key: "mt", label: "Margine di Tesoreria", format: "euro" },
  { key: "ccn", label: "CCN", format: "euro" },
  { key: "current_ratio", label: "Liquidità Corrente", format: "ratio" },
  { key: "ms", label: "Margine di Struttura", format: "euro" },
  { key: "copertura_immob", label: "Copertura Immobilizzazioni", format: "pct" },
  { key: "indipendenza", label: "Indipendenza Finanziaria", format: "pct" },
  { key: "pfn", label: "PFN", format: "euro" },
  { key: "pfn_ebitda", label: "PFN / EBITDA", format: "ratio" },
  { key: "roi", label: "ROI", format: "pct" },
  { key: "roe", label: "ROE", format: "pct" },
  { key: "ros", label: "ROS", format: "pct" },
  { key: "of_mol", label: "Oneri Finanziari / MOL", format: "pct" },
];

// Dot color and overall rating from score
function scoreDotColor(score: number): string {
  if (score >= 0.67) return "bg-green-500";
  if (score >= 0.33) return "bg-yellow-500";
  return "bg-red-500";
}


// Crisis rating: combines indicators "oltre soglia" (score < 0.33) with extra-accounting alerts
// An indicator is "oltre soglia" when its score falls in the red zone
function computeCrisisRating(
  scores: number[],
  alertCount: number,
): { code: string; label: string; color: string } {
  const oltreCount = scores.filter((s) => s < 0.33).length;

  // From best to worst:
  // A3: 0 oltre + 0 segnali
  if (oltreCount === 0 && alertCount === 0)
    return { code: "A3", label: "Nessun rischio", color: "text-green-600 dark:text-green-400" };
  // A2: 1-2 oltre + 0 segnali
  if (oltreCount <= 2 && alertCount === 0)
    return { code: "A2", label: "Rischio minimo", color: "text-green-600 dark:text-green-400" };
  // A1: 3 oltre + 0 segnali
  if (oltreCount === 3 && alertCount === 0)
    return { code: "A1", label: "Rischio basso", color: "text-green-600 dark:text-green-400" };
  // B3: 4-5 oltre + 0 segnali
  if (oltreCount <= 5 && alertCount === 0)
    return { code: "B3", label: "Rischio moderato", color: "text-yellow-600 dark:text-yellow-400" };
  // B2: 1 segnale e/o >4 oltre
  if (alertCount <= 1 && oltreCount <= 5)
    return { code: "B2", label: "Rischio significativo", color: "text-yellow-600 dark:text-yellow-400" };
  // B1: 2 segnali e/o >4 oltre
  if (alertCount <= 2 && oltreCount <= 5)
    return { code: "B1", label: "Rischio elevato", color: "text-orange-600 dark:text-orange-400" };
  // C3: 3 segnali e/o >5 oltre
  if (alertCount <= 3 && oltreCount <= 6)
    return { code: "C3", label: "Rischio alto", color: "text-orange-600 dark:text-orange-400" };
  // C2: 3 segnali e/o >6 oltre
  if (alertCount <= 3 && oltreCount <= 7)
    return { code: "C2", label: "Rischio grave", color: "text-red-600 dark:text-red-400" };
  // C1: 3+ segnali e >5 oltre
  if (alertCount >= 3 && oltreCount > 5)
    return { code: "C1", label: "Pre-crisi", color: "text-red-600 dark:text-red-400" };
  // D: 4+ segnali + 5+ oltre
  return { code: "D", label: "Crisi", color: "text-red-600 dark:text-red-400" };
}

function buildBalanceItemsWithTotals(
  items: IntraYearComparisonItem[],
): IntraYearComparisonItem[] {
  const byCode = new Map(items.map((i) => [i.code, i]));
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);

  const v = (code: string, key: "partial_value" | "reference_value" | "annualized_value") =>
    byCode.get(code)?.[key] ?? 0;

  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0);

  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Relabel
  const relabel: Record<string, string> = {
    sp01_crediti_soci: "A) Crediti verso soci per versamenti ancora dovuti",
    sp02_immob_immateriali: "I - Immobilizzazioni immateriali",
    sp03_immob_materiali: "II - Immobilizzazioni materiali",
    sp04_immob_finanziarie: "III - Immobilizzazioni finanziarie",
    sp05_rimanenze: "I - Rimanenze",
    sp06_crediti_breve: "II - Crediti (entro esercizio successivo)",
    sp07_crediti_lungo: "II - Crediti (oltre esercizio successivo)",
    sp08_attivita_finanziarie: "III - Attivit\u00e0 finanziarie che non costituiscono immobilizzazioni",
    sp09_disponibilita_liquide: "IV - Disponibilit\u00e0 liquide",
    sp10_ratei_risconti_attivi: "D) Ratei e risconti attivi",
    sp11_capitale: "I - Capitale",
    sp12_riserve: "II-VIII - Riserve",
    sp13_utile_perdita: "IX - Utile (perdita) dell'esercizio",
    sp14_fondi_rischi: "B) Fondi per rischi e oneri",
    sp15_tfr: "C) Trattamento di fine rapporto di lavoro subordinato",
    sp16_debiti_breve: "Debiti (entro esercizio successivo)",
    sp17_debiti_lungo: "Debiti (oltre esercizio successivo)",
    sp18_ratei_risconti_passivi: "E) Ratei e risconti passivi",
  };

  const labeled = (code: string): IntraYearComparisonItem => {
    const orig = item(code);
    return { ...orig, label: relabel[code] ?? orig.label };
  };

  // Subtotals
  const IMMOB_CODES = ["sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie"];
  const CIRC_CODES = ["sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide"];
  const PN_CODES = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita"];
  const DEBT_CODES = ["sp16_debiti_breve", "sp17_debiti_lungo"];

  const sumCodes = (codes: string[], key: "partial_value" | "reference_value" | "annualized_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);

  const totImmobP = sumCodes(IMMOB_CODES, "partial_value");
  const totImmobR = sumCodes(IMMOB_CODES, "reference_value");
  const totImmobA = sumCodes(IMMOB_CODES, "annualized_value");

  const totCircP = sumCodes(CIRC_CODES, "partial_value");
  const totCircR = sumCodes(CIRC_CODES, "reference_value");
  const totCircA = sumCodes(CIRC_CODES, "annualized_value");

  const totAttivoP = sumCodes(ATTIVO_CODES, "partial_value");
  const totAttivoR = sumCodes(ATTIVO_CODES, "reference_value");
  const totAttivoA = sumCodes(ATTIVO_CODES, "annualized_value");

  const totPNP = sumCodes(PN_CODES, "partial_value");
  const totPNR = sumCodes(PN_CODES, "reference_value");
  const totPNA = sumCodes(PN_CODES, "annualized_value");

  const totDebtP = sumCodes(DEBT_CODES, "partial_value");
  const totDebtR = sumCodes(DEBT_CODES, "reference_value");
  const totDebtA = sumCodes(DEBT_CODES, "annualized_value");

  const totPassivoP = sumCodes(PASSIVO_CODES, "partial_value");
  const totPassivoR = sumCodes(PASSIVO_CODES, "reference_value");
  const totPassivoA = sumCodes(PASSIVO_CODES, "annualized_value");

  return [
    // ATTIVO
    hdr("_hdr_attivo", "ATTIVO"),
    labeled("sp01_crediti_soci"),
    // B) IMMOBILIZZAZIONI
    hdr("_hdr_immob", "B) IMMOBILIZZAZIONI"),
    labeled("sp02_immob_immateriali"),
    labeled("sp03_immob_materiali"),
    labeled("sp04_immob_finanziarie"),
    makeRow("_totale_immob", "Totale Immobilizzazioni", totImmobP, totImmobR, totImmobA),
    // C) ATTIVO CIRCOLANTE
    hdr("_hdr_circ", "C) ATTIVO CIRCOLANTE"),
    labeled("sp05_rimanenze"),
    labeled("sp06_crediti_breve"),
    labeled("sp07_crediti_lungo"),
    labeled("sp08_attivita_finanziarie"),
    labeled("sp09_disponibilita_liquide"),
    makeRow("_totale_circ", "Totale Attivo Circolante", totCircP, totCircR, totCircA),
    // D) Ratei
    labeled("sp10_ratei_risconti_attivi"),
    makeRow("_totale_attivo", "TOTALE ATTIVO", totAttivoP, totAttivoR, totAttivoA),
    // PASSIVO E PATRIMONIO NETTO
    hdr("_hdr_passivo", "PASSIVO E PATRIMONIO NETTO"),
    // A) PATRIMONIO NETTO
    hdr("_hdr_pn", "A) PATRIMONIO NETTO"),
    labeled("sp11_capitale"),
    labeled("sp12_riserve"),
    labeled("sp13_utile_perdita"),
    makeRow("_totale_pn", "Totale Patrimonio Netto", totPNP, totPNR, totPNA),
    // B) Fondi
    labeled("sp14_fondi_rischi"),
    // C) TFR
    labeled("sp15_tfr"),
    // D) DEBITI
    hdr("_hdr_debiti", "D) DEBITI"),
    labeled("sp16_debiti_breve"),
    labeled("sp17_debiti_lungo"),
    makeRow("_totale_debiti", "Totale Debiti", totDebtP, totDebtR, totDebtA),
    // E) Ratei passivi
    labeled("sp18_ratei_risconti_passivi"),
    makeRow("_totale_passivo", "TOTALE PASSIVO E PATRIMONIO NETTO", totPassivoP, totPassivoR, totPassivoA),
    // Differenza
    makeRow("_differenza", "DIFFERENZA (Attivo - Passivo)",
      totAttivoP - totPassivoP, totAttivoR - totPassivoR, totAttivoA - totPassivoA),
  ];
}

function buildIncomeItemsWithEbitda(
  items: IntraYearComparisonItem[],
  periodMonths: number,
): IntraYearComparisonItem[] {
  const byCode = new Map(items.map((i) => [i.code, i]));
  const factor = 12 / periodMonths;
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);

  const v = (code: string, key: "partial_value" | "reference_value") =>
    byCode.get(code)?.[key] ?? 0;
  const ann = (code: string) => byCode.get(code)?.annualized_value ?? 0;
  const sum = (codes: string[], key: "partial_value" | "reference_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);
  const sumAnn = (codes: string[]) =>
    codes.reduce((acc, c) => acc + ann(c), 0);

  // Lookup or zero-item helper
  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Helper: create a synthetic row
  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  // Header row (no values)
  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0);

  // Subtotals
  const partialVP = sum(VP_CODES, "partial_value");
  const refVP = sum(VP_CODES, "reference_value");
  const annVP = sumAnn(VP_CODES);

  const COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce12_oneri_diversi"];
  const partialCP = sum(COST_CODES_ALL, "partial_value");
  const refCP = sum(COST_CODES_ALL, "reference_value");
  const annCP = sumAnn(COST_CODES_ALL);

  const partialEbitda = partialVP - (partialCP - v("ce09_ammortamenti", "partial_value"));
  const refEbitda = refVP - (refCP - v("ce09_ammortamenti", "reference_value"));
  const annEbitda = annVP - (annCP - ann("ce09_ammortamenti"));

  const partialEbit = partialVP - partialCP;
  const refEbit = refVP - refCP;
  const annEbit = annVP - annCP;

  const FIN_INCOME = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"];
  const FIN_COST = ["ce15_oneri_finanziari"];
  const partialFin = sum(FIN_INCOME, "partial_value") - sum(FIN_COST, "partial_value");
  const refFin = sum(FIN_INCOME, "reference_value") - sum(FIN_COST, "reference_value");
  const annFin = sumAnn(FIN_INCOME) - sumAnn(FIN_COST);

  const partialStraord = v("ce18_proventi_straordinari", "partial_value") - v("ce19_oneri_straordinari", "partial_value");
  const refStraord = v("ce18_proventi_straordinari", "reference_value") - v("ce19_oneri_straordinari", "reference_value");
  const annStraord = ann("ce18_proventi_straordinari") - ann("ce19_oneri_straordinari");

  const partialRettifiche = v("ce17_rettifiche_attivita_fin", "partial_value");
  const refRettifiche = v("ce17_rettifiche_attivita_fin", "reference_value");
  const annRettifiche = ann("ce17_rettifiche_attivita_fin");

  const partialPBT = partialEbit + partialFin + partialRettifiche + partialStraord;
  const refPBT = refEbit + refFin + refRettifiche + refStraord;
  const annPBT = annEbit + annFin + annRettifiche + annStraord;

  const partialNetProfit = partialPBT - v("ce20_imposte", "partial_value");
  const refNetProfit = refPBT - v("ce20_imposte", "reference_value");
  const annNetProfit = annPBT - ann("ce20_imposte");

  const partialRevenue = v("ce01_ricavi_vendite", "partial_value");
  const refRevenue = v("ce01_ricavi_vendite", "reference_value");

  // Relabel items to match IV CEE format
  const relabel: Record<string, string> = {
    ce01_ricavi_vendite: "1) Ricavi delle vendite e delle prestazioni",
    ce02_variazioni_rimanenze: "2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti",
    ce03_lavori_interni: "3) Variazioni dei lavori in corso su ordinazione",
    ce04_altri_ricavi: "5) Altri ricavi e proventi",
    ce05_materie_prime: "6) Materie prime, sussidiarie, di consumo e di merci",
    ce06_servizi: "7) Servizi",
    ce07_godimento_beni: "8) Godimento di beni di terzi",
    ce08_costi_personale: "9) Personale",
    ce09_ammortamenti: "10) Ammortamenti e svalutazioni",
    ce10_var_rimanenze_mat_prime: "11) Variazioni delle rim. di materie prime, sussidiarie, di cons. e merci",
    ce11_accantonamenti: "12) Accantonamenti per rischi",
    ce12_oneri_diversi: "14) Oneri diversi di gestione",
    ce13_proventi_partecipazioni: "15) Proventi da partecipazioni",
    ce14_altri_proventi_finanziari: "16) Altri proventi finanziari",
    ce15_oneri_finanziari: "17) Interessi e altri oneri finanziari",
    ce16_utili_perdite_cambi: "17-bis) Utili e perdite su cambi",
    ce17_rettifiche_attivita_fin: "18-19) Rettifiche di valore",
    ce18_proventi_straordinari: "20) Proventi straordinari",
    ce19_oneri_straordinari: "21) Oneri straordinari",
    ce20_imposte: "22) Imposte sul reddito",
  };

  const labeled = (code: string): IntraYearComparisonItem => {
    const orig = item(code);
    return { ...orig, label: relabel[code] ?? orig.label };
  };

  return [
    // A) VALORE DELLA PRODUZIONE
    hdr("_hdr_a", "A) VALORE DELLA PRODUZIONE"),
    labeled("ce01_ricavi_vendite"),
    labeled("ce02_variazioni_rimanenze"),
    labeled("ce03_lavori_interni"),
    labeled("ce04_altri_ricavi"),
    makeRow("_totale_vp", "Totale Valore della Produzione", partialVP, refVP, annVP),
    // B) COSTI DELLA PRODUZIONE
    hdr("_hdr_b", "B) COSTI DELLA PRODUZIONE"),
    labeled("ce05_materie_prime"),
    labeled("ce06_servizi"),
    labeled("ce07_godimento_beni"),
    labeled("ce08_costi_personale"),
    labeled("ce09_ammortamenti"),
    labeled("ce10_var_rimanenze_mat_prime"),
    labeled("ce11_accantonamenti"),
    labeled("ce12_oneri_diversi"),
    makeRow("_totale_cp", "Totale Costi della Produzione", partialCP, refCP, annCP),
    makeRow("_ebitda", "EBITDA (MOL)", partialEbitda, refEbitda, annEbitda),
    makeRow("_ebit", "EBIT (Risultato Operativo)", partialEbit, refEbit, annEbit),
    // C) PROVENTI E ONERI FINANZIARI
    hdr("_hdr_c", "C) PROVENTI E ONERI FINANZIARI"),
    labeled("ce13_proventi_partecipazioni"),
    labeled("ce14_altri_proventi_finanziari"),
    labeled("ce15_oneri_finanziari"),
    labeled("ce16_utili_perdite_cambi"),
    makeRow("_totale_fin", "Totale Proventi/Oneri Finanziari", partialFin, refFin, annFin),
    // D) RETTIFICHE DI VALORE
    hdr("_hdr_d", "D) RETTIFICHE DI VALORE ATTIVIT\u00c0 FINANZIARIE"),
    labeled("ce17_rettifiche_attivita_fin"),
    // E) PROVENTI E ONERI STRAORDINARI
    hdr("_hdr_e", "E) PROVENTI E ONERI STRAORDINARI"),
    labeled("ce18_proventi_straordinari"),
    labeled("ce19_oneri_straordinari"),
    makeRow("_totale_straord", "Totale Proventi/Oneri Straordinari", partialStraord, refStraord, annStraord),
    // Risultato prima delle imposte
    makeRow("_profit_before_tax", "Risultato prima delle imposte", partialPBT, refPBT, annPBT),
    labeled("ce20_imposte"),
    makeRow("_net_profit", "23) UTILE (PERDITA) DELL'ESERCIZIO", partialNetProfit, refNetProfit, annNetProfit),
  ];
}

export default function InfraannualePage() {
  const router = useRouter();
  const { companies, refreshCompanies, setSelectedCompanyId } = useApp();

  // Wizard state
  const [activeTab, setActiveTab] = useState("aziende");

  // Step 1: Import
  const [importType, setImportType] = useState<"pdf" | "xbrl">("pdf");
  const [file, setFile] = useState<File | null>(null);
  const [fiscalYear, setFiscalYear] = useState(new Date().getFullYear());
  const [periodMonths, setPeriodMonths] = useState(9);
  const [companyMode, setCompanyMode] = useState<"new" | "existing">("new");
  const [selectedCompany, setSelectedCompany] = useState<number | null>(null);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [sector, setSector] = useState(1);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{
    companyId: number;
    companyName: string;
  } | null>(null);
  const [missingRefYear, setMissingRefYear] = useState<number | null>(null);

  // Second import (historical year when infra-year PDF has only 1 column)
  const [refFile, setRefFile] = useState<File | null>(null);
  const [importingRef, setImportingRef] = useState(false);

  // Step 2: Comparison
  const [scenario, setScenario] = useState<BudgetScenario | null>(null);
  const [comparison, setComparison] = useState<IntraYearComparison | null>(null);
  const [loadingComparison, setLoadingComparison] = useState(false);

  // Step 3: Projection overrides
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [projectedBS, setProjectedBS] = useState<IntraYearComparisonItem[] | null>(null);

  // Step 4: Results
  const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [extraAlerts, setExtraAlerts] = useState<Record<string, boolean>>({});
  const [ratingVisible, setRatingVisible] = useState(false);
  const [showNoAlertsConfirm, setShowNoAlertsConfirm] = useState(false);

  // Refresh companies list on mount and when page regains focus
  useEffect(() => {
    refreshCompanies();

    const handleFocus = () => refreshCompanies();
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshCompanies]);

  // Auto-select first company if needed
  useEffect(() => {
    if (companies.length > 0 && !selectedCompany) {
      setSelectedCompany(companies[0].id);
    }
  }, [companies, selectedCompany]);

  // Helper: create scenario and advance to comparison step
  const createScenarioAndAdvance = async (companyId: number, companyName: string) => {
    const refYear = fiscalYear - 1;
    const scenarioData = await createBudgetScenario(companyId, {
      company_id: companyId,
      name: `Infrannuale ${periodMonths}M ${fiscalYear}`,
      base_year: refYear,
      scenario_type: "infrannuale",
      period_months: periodMonths,
    });
    setScenario(scenarioData);
    setImportResult({ companyId, companyName });
    toast.success(`Importazione completata: ${companyName}`);
    setActiveTab("comparison");
  };

  // STEP 1: Import Handler (infra-year PDF/XBRL)
  const handleImport = async () => {
    if (!file) {
      toast.error("Seleziona un file da importare");
      return;
    }

    setImporting(true);
    try {
      let companyId: number;
      let companyName: string;

      if (importType === "pdf") {
        const result = await importPDF(
          file,
          fiscalYear,
          companyMode === "new" ? newCompanyName : undefined,
          companyMode === "existing" ? selectedCompany : undefined,
          companyMode === "new",
          companyMode === "new" ? sector : undefined,
          periodMonths
        );
        companyId = result.company_id;
        companyName = result.company_name;
      } else {
        const result = await importXBRL(
          file,
          companyMode === "existing" ? selectedCompany : undefined,
          companyMode === "new",
          companyMode === "new" ? sector : undefined,
          periodMonths
        );
        companyId = result.company_id;
        companyName = result.company_name;
      }

      await refreshCompanies();
      setSelectedCompanyId(companyId);
      setMissingRefYear(null);

      // Check if reference year exists (may have been imported from dual-column PDF)
      const years = await getCompanyYears(companyId);
      const refYear = fiscalYear - 1;
      if (!years.includes(refYear)) {
        setImportResult({ companyId, companyName });
        setMissingRefYear(refYear);
        toast.warning(
          `Dati ${fiscalYear} importati. Serve il bilancio storico ${refYear} per procedere.`
        );
        return;
      }

      await createScenarioAndAdvance(companyId, companyName);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore durante l'importazione";
      toast.error(msg);
    } finally {
      setImporting(false);
    }
  };

  // STEP 1b: Import reference year (historical full-year balance sheet)
  const handleImportRefYear = async () => {
    if (!refFile || !importResult || !missingRefYear) return;

    setImportingRef(true);
    try {
      await importPDF(
        refFile,
        missingRefYear,
        undefined,                  // no company name (existing company)
        importResult.companyId,     // attach to same company
        false,                      // don't create company
        undefined,                  // sector already set
        undefined                   // no period_months = full 12-month year
      );

      // Verify it worked
      const years = await getCompanyYears(importResult.companyId);
      if (!years.includes(missingRefYear)) {
        toast.error(`Importazione riuscita ma anno ${missingRefYear} non trovato`);
        return;
      }

      setMissingRefYear(null);
      await createScenarioAndAdvance(importResult.companyId, importResult.companyName);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nell'importazione del bilancio storico";
      toast.error(msg);
    } finally {
      setImportingRef(false);
    }
  };

  // STEP 2: Load Comparison
  const loadComparison = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingComparison(true);
    try {
      const data = await getIntraYearComparison(importResult.companyId, scenario.id);
      setComparison(data);

      // Try to restore saved projections from existing forecast data
      let restored = false;
      try {
        const existingAnalysis = await getScenarioAnalysis(importResult.companyId, scenario.id);
        const forecastIS = existingAnalysis.forecast_years?.[0]?.income_statement;
        const forecastBS = existingAnalysis.forecast_years?.[0]?.balance_sheet;
        if (forecastIS && Object.keys(forecastIS).length > 0) {
          // Restore CE overrides from saved forecast income statement
          const saved: Record<string, string> = {};
          for (const code of EDITABLE_CE_CODES) {
            if (code in forecastIS) {
              saved[code] = Math.round(forecastIS[code]).toString();
            }
          }
          if (Object.keys(saved).length > 0) {
            setOverrides(saved);
            restored = true;
          }

          // Restore BS projection from saved forecast balance sheet
          if (forecastBS && Object.keys(forecastBS).length > 0) {
            const projItems: IntraYearComparisonItem[] = data.balance_items.map((item) => ({
              ...item,
              annualized_value: Math.round(forecastBS[item.code] ?? item.partial_value),
            }));
            setProjectedBS(buildBalanceItemsWithTotals(projItems));
          }

          setAnalysis(existingAnalysis);
        }
      } catch {
        // No existing forecast — that's fine, use defaults
      }

      if (!restored) {
        // Pre-populate overrides with annualized values (fresh scenario)
        const defaults: Record<string, string> = {};
        for (const item of data.income_items) {
          if (EDITABLE_CE_CODES.includes(item.code)) {
            defaults[item.code] = Math.round(item.annualized_value).toString();
          }
        }
        setOverrides(defaults);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento confronto";
      toast.error(msg);
    } finally {
      setLoadingComparison(false);
    }
  }, [importResult, scenario]);

  useEffect(() => {
    if (activeTab === "comparison" && !comparison && scenario) {
      loadComparison();
    }
  }, [activeTab, comparison, scenario, loadComparison]);

  // STEP 3: Generate Projection

  // Calculate projected BS from CE overrides + historical turnover ratios,
  // then save assumptions to backend to generate forecast
  const calculateProjectedBS = async () => {
    if (!comparison || !importResult || !scenario) return;

    const refBS = new Map(comparison.balance_items.map((i) => [i.code, i]));
    const refCE = new Map(comparison.income_items.map((i) => [i.code, i]));

    const refVal = (code: string) => refBS.get(code)?.reference_value ?? 0;
    const partialVal = (code: string) => refBS.get(code)?.partial_value ?? 0;
    const refCEVal = (code: string) => refCE.get(code)?.reference_value ?? 0;
    const projCEVal = (code: string) => parseFloat(overrides[code] || "0");

    // Projected P&L values for turnover computation
    const projRevenue = projCEVal("ce01_ricavi_vendite");
    const projMaterials = projCEVal("ce05_materie_prime");
    const projServices = projCEVal("ce06_servizi");
    const projPurchases = projMaterials + projServices;

    // Compute projected net profit from overrides (same logic as ProjectionTable)
    const allCostCodes = [
      ...EBITDA_COST_CODES, "ce09_ammortamenti",
      "ce15_oneri_finanziari", "ce19_oneri_straordinari", "ce20_imposte",
    ];
    const allIncomeCodes = [
      ...VP_CODES,
      "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
      "ce16_utili_perdite_cambi", "ce17_rettifiche_attivita_fin", "ce18_proventi_straordinari",
    ];
    const projIncome = allIncomeCodes.reduce(
      (acc, c) => acc + (EDITABLE_CE_CODES.includes(c) ? projCEVal(c) : (refCE.get(c)?.annualized_value ?? 0)), 0
    );
    const projCosts = allCostCodes.reduce(
      (acc, c) => acc + (EDITABLE_CE_CODES.includes(c) ? projCEVal(c) : (refCE.get(c)?.annualized_value ?? 0)), 0
    );
    const projNetProfit = projIncome - projCosts;

    // Turnover days from historical (reference year = full 12 months)
    const refRevenue = refCEVal("ce01_ricavi_vendite");
    const refPurchases = refCEVal("ce05_materie_prime") + refCEVal("ce06_servizi");

    const receivableDays = refRevenue !== 0 ? (refVal("sp06_crediti_breve") / refRevenue) * 365 : 0;
    const inventoryDays = refCEVal("ce05_materie_prime") !== 0
      ? (refVal("sp05_rimanenze") / refCEVal("ce05_materie_prime")) * 365 : 0;
    const payableDays = refPurchases !== 0 ? (refVal("sp16_debiti_breve") / refPurchases) * 365 : 0;

    // Projected working capital items
    const sp05 = projMaterials !== 0 ? projMaterials * inventoryDays / 365 : partialVal("sp05_rimanenze");
    const sp06 = projRevenue !== 0 ? projRevenue * receivableDays / 365 : partialVal("sp06_crediti_breve");
    let sp16 = projPurchases !== 0 ? projPurchases * payableDays / 365 : partialVal("sp16_debiti_breve");

    // Other items from infrannuale (partial year)
    const sp01 = partialVal("sp01_crediti_soci");
    const sp02 = partialVal("sp02_immob_immateriali");
    const sp03 = partialVal("sp03_immob_materiali");
    const sp04 = partialVal("sp04_immob_finanziarie");
    const sp07 = partialVal("sp07_crediti_lungo");
    const sp08 = partialVal("sp08_attivita_finanziarie");
    const sp10 = partialVal("sp10_ratei_risconti_attivi");
    const sp11 = partialVal("sp11_capitale");
    const sp12 = partialVal("sp12_riserve");
    const sp14 = partialVal("sp14_fondi_rischi");
    const sp15 = partialVal("sp15_tfr");
    const sp17 = partialVal("sp17_debiti_lungo");
    const sp18 = partialVal("sp18_ratei_risconti_passivi");

    // sp13 = projected net profit
    const sp13 = projNetProfit;

    // Cash plug: Passivo - Attivo (without cash)
    const totalAssetNoCash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10;
    const totalLiabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18;
    let sp09 = totalLiabilities - totalAssetNoCash;

    if (sp09 < 0) {
      // Negative cash → increase short-term debt
      sp16 = sp16 + Math.abs(sp09);
      sp09 = 0;
    }

    // Build projected items with same structure as comparison
    const projValues: Record<string, number> = {
      sp01_crediti_soci: sp01, sp02_immob_immateriali: sp02,
      sp03_immob_materiali: sp03, sp04_immob_finanziarie: sp04,
      sp05_rimanenze: sp05, sp06_crediti_breve: sp06,
      sp07_crediti_lungo: sp07, sp08_attivita_finanziarie: sp08,
      sp09_disponibilita_liquide: sp09, sp10_ratei_risconti_attivi: sp10,
      sp11_capitale: sp11, sp12_riserve: sp12, sp13_utile_perdita: sp13,
      sp14_fondi_rischi: sp14, sp15_tfr: sp15, sp16_debiti_breve: sp16,
      sp17_debiti_lungo: sp17, sp18_ratei_risconti_passivi: sp18,
    };

    const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);
    const projItems: IntraYearComparisonItem[] = comparison.balance_items.map((item) => ({
      ...item,
      annualized_value: Math.round(projValues[item.code] ?? partialVal(item.code)),
    }));

    setProjectedBS(buildBalanceItemsWithTotals(projItems));

    // Save assumptions to backend and generate forecast
    try {
      const refItems = comparison.income_items.reduce(
        (acc, item) => ({ ...acc, [item.code]: item.reference_value }),
        {} as Record<string, number>
      );
      const calcGrowth = (code: string): number => {
        const overrideVal = parseFloat(overrides[code] || "0");
        const refV = refItems[code] || 0;
        if (refV === 0) return 0;
        return ((overrideVal / refV) - 1) * 100;
      };

      await bulkUpsertAssumptions(importResult.companyId, scenario.id, {
        assumptions: [{
          forecast_year: fiscalYear,
          revenue_growth_pct: calcGrowth("ce01_ricavi_vendite"),
          other_revenue_growth_pct: calcGrowth("ce04_altri_ricavi"),
          variable_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          fixed_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          variable_services_growth_pct: calcGrowth("ce06_servizi"),
          fixed_services_growth_pct: calcGrowth("ce06_servizi"),
          rent_growth_pct: calcGrowth("ce07_godimento_beni"),
          personnel_growth_pct: calcGrowth("ce08_costi_personale"),
          other_costs_growth_pct: calcGrowth("ce12_oneri_diversi"),
          tax_rate: 27.9,
          fixed_materials_percentage: 40,
          fixed_services_percentage: 40,
          depreciation_rate: 20,
          investments: 0,
          receivables_short_growth_pct: 0,
          receivables_long_growth_pct: 0,
          payables_short_growth_pct: 0,
          interest_rate_receivables: 0,
          interest_rate_payables: 0,
          financing_amount: 0,
          financing_duration_years: 0,
          financing_interest_rate: 0,
        }],
        auto_generate: true,
      });
      setAnalysis(null); // Clear stale analysis so Indicatori tab reloads
      toast.success("Proiezione calcolata e salvata");
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel salvataggio proiezione";
      toast.error(msg);
    }
  };

  // Auto-save projection with 0% growth for 12M infrannuale (no annualization needed)
  const saveProjection12M = async () => {
    if (!comparison || !importResult || !scenario) return;

    // Pre-fill overrides from comparison partial values (= full year when 12M)
    const defaults: Record<string, string> = {};
    for (const item of comparison.income_items) {
      if (EDITABLE_CE_CODES.includes(item.code)) {
        defaults[item.code] = Math.round(item.partial_value).toString();
      }
    }
    setOverrides(defaults);

    // Set projectedBS from comparison balance items (already full-year values)
    const projItems: IntraYearComparisonItem[] = comparison.balance_items.map((item) => ({
      ...item,
      annualized_value: item.partial_value,
    }));
    setProjectedBS(buildBalanceItemsWithTotals(projItems));

    // Calculate growth rates from imported 12M values vs reference year
    try {
      const refItems = comparison.income_items.reduce(
        (acc, item) => ({ ...acc, [item.code]: item.reference_value }),
        {} as Record<string, number>
      );
      const calcGrowth = (code: string): number => {
        const importedVal = comparison.income_items.find(i => i.code === code)?.partial_value ?? 0;
        const refV = refItems[code] || 0;
        if (refV === 0) return 0;
        return ((importedVal / refV) - 1) * 100;
      };

      await bulkUpsertAssumptions(importResult.companyId, scenario.id, {
        assumptions: [{
          forecast_year: fiscalYear,
          revenue_growth_pct: calcGrowth("ce01_ricavi_vendite"),
          other_revenue_growth_pct: calcGrowth("ce04_altri_ricavi"),
          variable_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          fixed_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          variable_services_growth_pct: calcGrowth("ce06_servizi"),
          fixed_services_growth_pct: calcGrowth("ce06_servizi"),
          rent_growth_pct: calcGrowth("ce07_godimento_beni"),
          personnel_growth_pct: calcGrowth("ce08_costi_personale"),
          other_costs_growth_pct: calcGrowth("ce12_oneri_diversi"),
          tax_rate: 27.9,
          fixed_materials_percentage: 40,
          fixed_services_percentage: 40,
          depreciation_rate: 20,
          investments: 0,
          receivables_short_growth_pct: 0,
          receivables_long_growth_pct: 0,
          payables_short_growth_pct: 0,
          interest_rate_receivables: 0,
          interest_rate_payables: 0,
          financing_amount: 0,
          financing_duration_years: 0,
          financing_interest_rate: 0,
        }],
        auto_generate: true,
      });
      setAnalysis(null); // Clear stale analysis so Indicatori tab reloads
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel salvataggio proiezione";
      toast.error(msg);
    }
  };

  // STEP 4: Load Analysis
  const loadAnalysis = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingAnalysis(true);
    try {
      const data = await getScenarioAnalysis(importResult.companyId, scenario.id);
      setAnalysis(data);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento analisi";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [importResult, scenario]);

  useEffect(() => {
    if ((activeTab === "results" || activeTab === "stampa") && !analysis && scenario) {
      loadAnalysis();
    }
  }, [activeTab, analysis, scenario, loadAnalysis]);

  // Also handle resuming an existing infrannuale scenario
  const handleResumeScenario = async (s: BudgetScenario, comp: Company) => {
    setImportResult({ companyId: comp.id, companyName: comp.name });
    setScenario(s);
    setFiscalYear(s.base_year + 1);
    setPeriodMonths(s.period_months || 9);
    setSelectedCompanyId(comp.id);
    setActiveTab("comparison");
  };

  const handleDeleteCompany = async (id: number, name: string) => {
    try {
      await deleteCompany(id);
      await refreshCompanies();
      if (selectedCompany === id) setSelectedCompany(null);
      if (importResult?.companyId === id) setImportResult(null);
      toast.success(`"${name}" eliminata`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Errore durante l'eliminazione";
      toast.error(msg);
    }
  };

  // Load existing infrannuale scenarios on mount
  const [existingScenarios, setExistingScenarios] = useState<
    Array<{ scenario: BudgetScenario; company: Company }>
  >([]);

  useEffect(() => {
    const loadExisting = async () => {
      const results = await Promise.allSettled(
        companies.map(async (company) => {
          const scenarios = await getBudgetScenarios(company.id);
          return scenarios
            .filter((s) => s.scenario_type === "infrannuale")
            .map((scenario) => ({ scenario, company }));
        })
      );
      const allScenarios = results
        .filter((r): r is PromiseFulfilledResult<Array<{ scenario: BudgetScenario; company: Company }>> => r.status === "fulfilled")
        .flatMap((r) => r.value);
      setExistingScenarios(allScenarios);
    };
    if (companies.length > 0) {
      loadExisting();
    }
  }, [companies]);

  const STEPS = [
    { id: "aziende", label: "Aziende", icon: Building2, enabled: true },
    { id: "import", label: "Importazione", icon: Upload, enabled: true },
    { id: "comparison", label: "Confronto", icon: GitCompareArrows, enabled: !!scenario },
    ...(periodMonths !== 12 ? [{ id: "projection", label: "Proiezione", icon: LineChart, enabled: !!comparison }] : []),
    { id: "results", label: "Indicatori", icon: BarChart3, enabled: !!scenario },
    { id: "stampa", label: "Stampa", icon: Printer, enabled: !!(projectedBS || (periodMonths === 12 && comparison)) },
  ];

  return (
    <>
      {/* Infrannuale Navigation Bar */}
      <div className="border-b border-border bg-background print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Infrannuale steps">
            {STEPS.map((step) => {
              const isActive = activeTab === step.id;
              const Icon = step.icon;
              return (
                <button
                  key={step.id}
                  onClick={() => step.enabled && setActiveTab(step.id)}
                  disabled={!step.enabled}
                  className={cn(
                    "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                    isActive
                      ? "border-primary text-foreground"
                      : step.enabled
                      ? "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                      : "border-transparent text-muted-foreground/40 cursor-not-allowed"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {step.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* STEP 0: AZIENDE */}
        {activeTab === "aziende" && <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Analisi Infrannuali</CardTitle>
              <CardDescription>
                Seleziona un&apos;analisi esistente per riprenderla, oppure importa un nuovo bilancio infrannuale.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {existingScenarios.length > 0 ? (
                <div className="space-y-2">
                  {existingScenarios.map(({ scenario: s, company: c }) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-muted/50 cursor-pointer"
                      onClick={() => handleResumeScenario(s, c)}
                    >
                      <div>
                        <p className="font-medium">{c.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {s.name} - Base: {s.base_year}
                        </p>
                      </div>
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        <Button variant="outline" size="sm" onClick={() => handleResumeScenario(s, c)}>
                          Riprendi
                          <ArrowRight className="h-4 w-4 ml-1" />
                        </Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="ghost">
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Elimina azienda</AlertDialogTitle>
                              <AlertDialogDescription>
                                Eliminare &quot;{c.name}&quot; e tutti i dati associati
                                (bilanci, scenari, previsioni)? Questa azione non può
                                essere annullata.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Annulla</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => handleDeleteCompany(c.id, c.name)}
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                              >
                                Elimina
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Nessuna analisi infrannuale presente. Importa un bilancio per iniziare.
                </p>
              )}
            </CardContent>
          </Card>
          <div className="flex justify-end">
            <Button onClick={() => setActiveTab("import")}>
              Nuova Importazione
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        </div>}

        {/* STEP 1: IMPORT */}
        {activeTab === "import" && <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Importa Bilancio Infrannuale</CardTitle>
              <CardDescription>
                Carica il bilancio parziale (es. situazione al 30/09/2025)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Import Type */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipo di file</Label>
                  <Select
                    value={importType}
                    onValueChange={(v) => setImportType(v as "pdf" | "xbrl")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pdf">PDF</SelectItem>
                      <SelectItem value="xbrl">XBRL</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>File</Label>
                  <Input
                    type="file"
                    accept={importType === "pdf" ? ".pdf" : ".xbrl,.xml"}
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </div>
              </div>

              {/* Period */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Anno fiscale</Label>
                  <Input
                    type="number"
                    value={fiscalYear}
                    onChange={(e) => setFiscalYear(parseInt(e.target.value) || 2025)}
                    min={2000}
                    max={2100}
                  />
                </div>
                <div>
                  <Label>Periodo (mesi coperti)</Label>
                  <Select
                    value={periodMonths.toString()}
                    onValueChange={(v) => setPeriodMonths(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(MONTH_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Company */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Azienda</Label>
                  <Select
                    value={companyMode}
                    onValueChange={(v) => setCompanyMode(v as "new" | "existing")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="existing">Azienda esistente</SelectItem>
                      <SelectItem value="new">Nuova azienda</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {companyMode === "existing" ? (
                  <div>
                    <Label>Seleziona azienda</Label>
                    <Select
                      value={selectedCompany?.toString() || ""}
                      onValueChange={(v) => setSelectedCompany(parseInt(v))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Seleziona..." />
                      </SelectTrigger>
                      <SelectContent>
                        {companies.map((c) => (
                          <SelectItem key={c.id} value={c.id.toString()}>
                            {c.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : (
                  <div>
                    <Label>Nome azienda</Label>
                    <Input
                      value={newCompanyName}
                      onChange={(e) => setNewCompanyName(e.target.value)}
                      placeholder="Ragione sociale"
                    />
                  </div>
                )}
              </div>

              {companyMode === "new" && (
                <div className="w-1/2">
                  <Label>Settore</Label>
                  <Select
                    value={sector.toString()}
                    onValueChange={(v) => setSector(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {value}. {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {importResult && missingRefYear ? (
                <div className="space-y-4">
                  <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
                    <div className="flex items-center gap-2">
                      <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
                      <p className="font-medium text-green-800 dark:text-green-300">
                        Dati infrannuali {fiscalYear} importati per {importResult.companyName}
                      </p>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800">
                    <div className="flex items-center gap-2">
                      <Upload className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                      <p className="font-medium text-yellow-800 dark:text-yellow-300">
                        Serve il bilancio storico {missingRefYear}
                      </p>
                    </div>
                    <p className="text-sm text-yellow-700 dark:text-yellow-400 mt-2">
                      Il PDF infrannuale non conteneva i dati dell&apos;anno precedente.
                      Carica il bilancio completo {missingRefYear} per procedere con l&apos;analisi.
                    </p>
                    <div className="flex items-center gap-3 mt-4">
                      <Input
                        type="file"
                        accept=".pdf"
                        className="flex-1"
                        onChange={(e) => setRefFile(e.target.files?.[0] || null)}
                      />
                      <Button
                        onClick={handleImportRefYear}
                        disabled={importingRef || !refFile}
                      >
                        {importingRef ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Importazione...
                          </>
                        ) : (
                          <>
                            <Upload className="h-4 w-4 mr-2" />
                            Importa {missingRefYear}
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              ) : importResult && scenario ? (
                <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
                  <div className="flex items-center gap-2">
                    <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <p className="font-medium text-green-800 dark:text-green-300">
                      Importazione completata: {importResult.companyName}
                    </p>
                  </div>
                  <Button
                    className="mt-3"
                    onClick={() => setActiveTab("comparison")}
                  >
                    Vai al Confronto
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
                </div>
              ) : (
                <Button
                  onClick={handleImport}
                  disabled={importing || !file}
                  className="w-full"
                >
                  {importing ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Importazione in corso...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Importa e Continua
                    </>
                  )}
                </Button>
              )}
            </CardContent>
          </Card>
        </div>}

        {/* STEP 2: COMPARISON */}
        {activeTab === "comparison" && <div className="space-y-6">
          {loadingComparison ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento confronto...</p>
              </CardContent>
            </Card>
          ) : comparison ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {["ce01_ricavi_vendite", "ce08_costi_personale", "ce05_materie_prime", "ce06_servizi"].map(
                  (code) => {
                    const item = comparison.income_items.find((i) => i.code === code);
                    if (!item) return null;
                    const expectedPct = (comparison.period_months / 12) * 100;
                    const isAbove = item.pct_of_reference > expectedPct;
                    return (
                      <Card key={code}>
                        <CardContent className="pt-4">
                          <p className="text-xs text-muted-foreground truncate">
                            {item.label}
                          </p>
                          <p className="text-lg font-bold">
                            {formatEuro(item.partial_value)}
                          </p>
                          <div className="flex items-center gap-1 mt-1">
                            {isAbove ? (
                              <TrendingUp className="h-3 w-3 text-green-600 dark:text-green-400" />
                            ) : (
                              <TrendingDown className="h-3 w-3 text-red-600 dark:text-red-400" />
                            )}
                            <span
                              className={`text-xs ${
                                isAbove
                                  ? "text-green-600 dark:text-green-400"
                                  : "text-red-600 dark:text-red-400"
                              }`}
                            >
                              {formatPct(item.pct_of_reference)} vs storico
                            </span>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  }
                )}
              </div>

              {/* P&L Comparison Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Conto Economico - Confronto {comparison.period_months}M{" "}
                    {comparison.partial_year} vs 12M {comparison.reference_year}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ComparisonTable
                    items={buildIncomeItemsWithEbitda(comparison.income_items, comparison.period_months)}
                    periodMonths={comparison.period_months}
                    referenceYear={comparison.reference_year}
                    partialYear={comparison.partial_year}
                    showAnnualized={periodMonths !== 12}
                    showRevenuePct
                  />
                </CardContent>
              </Card>

              {/* BS Comparison Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Stato Patrimoniale - Confronto
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ComparisonTable
                    items={buildBalanceItemsWithTotals(comparison.balance_items)}
                    periodMonths={comparison.period_months}
                    referenceYear={comparison.reference_year}
                    partialYear={comparison.partial_year}
                    showAnnualized={false}
                  />
                </CardContent>
              </Card>

              <div className="flex justify-end">
                <Button onClick={async () => {
                  if (periodMonths === 12) {
                    await saveProjection12M();
                    setActiveTab("results");
                  } else {
                    setActiveTab("projection");
                  }
                }}>
                  {periodMonths === 12 ? "Vai agli Indicatori" : "Vai alla Proiezione"}
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </div>
            </>
          ) : null}
        </div>}

        {/* STEP 3: PROJECTION */}
        {activeTab === "projection" && comparison && <div className="space-y-6">
          {/* P&L Projection */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Conto Economico - Proiezione {fiscalYear}
              </CardTitle>
              <CardDescription>
                I valori Proiezione sono modificabili. Pre-compilati con
                annualizzazione ({periodMonths}M → 12M).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ProjectionTable
                items={buildIncomeItemsWithEbitda(comparison.income_items, comparison.period_months)}
                periodMonths={comparison.period_months}
                referenceYear={comparison.reference_year}
                partialYear={comparison.partial_year}
                showRevenuePct
                overrides={overrides}
                onOverrideChange={(code, value) => {
                  setOverrides((prev) => ({ ...prev, [code]: value }));
                  setProjectedBS(null); // Recalculate needed
                }}
              />
            </CardContent>
          </Card>

          {/* BS Projection */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle className="text-base">
                  Stato Patrimoniale - Proiezione {fiscalYear}
                </CardTitle>
                <CardDescription>
                  Crediti, debiti e rimanenze calcolati con stessi giorni di rotazione dello storico.
                  Liquidità come differenza.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={calculateProjectedBS}>
                <BarChart3 className="h-4 w-4 mr-2" />
                Calcola Proiezione SP
              </Button>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                items={projectedBS ?? buildBalanceItemsWithTotals(
                  comparison.balance_items.map((i) => ({ ...i, annualized_value: NaN }))
                )}
                periodMonths={comparison.period_months}
                referenceYear={comparison.reference_year}
                partialYear={comparison.partial_year}
                showAnnualized
              />
            </CardContent>
          </Card>

          <div className="flex justify-between">
            <Button
              variant="outline"
              onClick={() => setActiveTab("comparison")}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Torna al Confronto
            </Button>
            <Button
              onClick={() => setActiveTab("results")}
              disabled={!projectedBS}
            >
              Indicatori
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        </div>}

        {/* STEP 4: INDICATORI */}
        {activeTab === "results" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento indicatori...</p>
              </CardContent>
            </Card>
          ) : analysis && comparison ? (
            <>
              <ExtraAccountingAlerts alerts={extraAlerts} onChange={(a) => { setExtraAlerts(a); setRatingVisible(false); }} />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Indicatori Finanziari</CardTitle>
                  <CardDescription>
                    {periodMonths === 12
                      ? `Confronto: storico ${comparison.reference_year}, infrannuale 12M ${comparison.partial_year}`
                      : `Confronto: storico ${comparison.reference_year}, infrannuale ${comparison.period_months}M ${comparison.partial_year} (annualizzato), proiezione 12M ${comparison.partial_year}`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <IndicatoriTable
                    comparison={comparison}
                    forecastBs={analysis.forecast_years?.[0]?.balance_sheet || {}}
                    forecastIs={analysis.forecast_years?.[0]?.income_statement || {}}
                    extraAlerts={extraAlerts}
                    showRating={ratingVisible}
                    hideProiezione={periodMonths === 12}
                  />
                </CardContent>
              </Card>

              {!ratingVisible && (
                <div className="flex justify-center">
                  <AlertDialog open={showNoAlertsConfirm} onOpenChange={setShowNoAlertsConfirm}>
                    <AlertDialogTrigger asChild>
                      <Button onClick={() => {
                        const hasAlerts = Object.values(extraAlerts).some(Boolean);
                        if (hasAlerts) {
                          setRatingVisible(true);
                        } else {
                          setShowNoAlertsConfirm(true);
                        }
                      }}>
                        <BarChart3 className="h-4 w-4 mr-2" />
                        Calcola Rating
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Segnali Extracontabili</AlertDialogTitle>
                        <AlertDialogDescription>
                          Conferma che non ci sono segnali extra contabili della crisi
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Annulla</AlertDialogCancel>
                        <AlertDialogAction onClick={() => { setShowNoAlertsConfirm(false); setRatingVisible(true); }}>
                          Conferma
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Genera prima la proiezione nel passaggio 3.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}

        {/* STEP 5: STAMPA */}
        {activeTab === "stampa" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento dati...</p>
              </CardContent>
            </Card>
          ) : analysis && comparison && (projectedBS || periodMonths === 12) ? (
            <StampaContent
              comparison={comparison}
              overrides={overrides}
              projectedBS={projectedBS ?? buildBalanceItemsWithTotals(
                comparison.balance_items.map((i) => ({ ...i, annualized_value: i.partial_value }))
              )}
              forecastBs={analysis.forecast_years?.[0]?.balance_sheet || {}}
              forecastIs={analysis.forecast_years?.[0]?.income_statement || {}}
              extraAlerts={extraAlerts}
              companyName={importResult?.companyName || ""}
              fiscalYear={fiscalYear}
              periodMonths={periodMonths}
              companyId={importResult?.companyId}
              scenarioId={scenario?.id}
              onBeforePromote={periodMonths === 12 ? saveProjection12M : undefined}
            />
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Completa prima i passaggi precedenti.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}

      </div>
    </>
  );
}

// Comparison Table Component
function ComparisonTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  showAnnualized,
  showRevenuePct = false,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  showAnnualized: boolean;
  showRevenuePct?: boolean;
}) {
  const expectedPct = (periodMonths / 12) * 100;

  // Revenue values for % computation
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Column date labels
  const refDate = `31/12/${referenceYear}`;
  const partialDate = `${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue for annualized % computation
  const annualizedRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.annualized_value ?? 0)
    : 0;

  // Column spans for group headers
  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          {showAnnualized && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
              Proiezione
            </TableHead>
          )}
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            {showAnnualized ? "Proiezione / Storico" : "Infrannuale / Storico"}
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          {showAnnualized && (
            <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          )}
          {showAnnualized && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit",
              "_totale_attivo", "_totale_passivo",
              "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";

            // Section headers: bold label spanning all columns
            if (isHeader) {
              // Count total columns: 1 (label) + colSpan (ref) + colSpan (partial) + [colSpan (ann)] + 1 (delta)
              const totalCols = 1 + colSpan + colSpan + (showAnnualized ? colSpan : 0) + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>
                  {item.label}
                </TableCell>
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {showAnnualized && (
                  <TableCell className="text-right text-sm font-medium">
                    {isNaN(item.annualized_value) ? (
                      <span className="text-muted-foreground">-</span>
                    ) : isPctRow ? "-" : formatEuro(item.annualized_value)}
                  </TableCell>
                )}
                {showAnnualized && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && !isNaN(item.annualized_value) && formatPct(pctOnRevenue(item.annualized_value, annualizedRevenue))}
                  </TableCell>
                )}
                {(() => {
                  const compareValue = showAnnualized ? item.annualized_value : item.partial_value;
                  if (isNaN(compareValue)) {
                    return <TableCell className="text-right text-sm text-muted-foreground">-</TableCell>;
                  }
                  const delta = item.reference_value !== 0
                    ? ((compareValue - item.reference_value) / Math.abs(item.reference_value)) * 100
                    : 0;
                  const isPositive = delta > 1;
                  const isNegative = delta < -1;
                  return (
                    <TableCell className="text-right text-sm">
                      {isPctRow ? (
                        <span className="text-muted-foreground">-</span>
                      ) : (
                        <span
                          className={
                            isPositive
                              ? "text-green-600 dark:text-green-400"
                              : isNegative
                              ? "text-red-600 dark:text-red-400"
                              : "text-muted-foreground"
                          }
                        >
                          {delta > 0 ? "+" : ""}{formatPct(delta)}
                        </span>
                      )}
                    </TableCell>
                  );
                })()}
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

// Projection Table Component (same layout as ComparisonTable but with editable Proiezione)
function ProjectionTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  showRevenuePct = false,
  overrides,
  onOverrideChange,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  showRevenuePct?: boolean;
  overrides: Record<string, string>;
  onOverrideChange: (code: string, value: string) => void;
}) {
  const refDate = `31/12/${referenceYear}`;
  const partialDate = `${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue values for % computation
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Get projected value: override if editable, annualized otherwise
  const getProjectedValue = (item: IntraYearComparisonItem): number => {
    if (EDITABLE_CE_CODES.includes(item.code)) {
      return parseFloat(overrides[item.code] || "0");
    }
    return item.annualized_value;
  };

  // Compute projected revenue for % column
  const projRevenue = showRevenuePct
    ? parseFloat(overrides["ce01_ricavi_vendite"] || "0")
    : 0;

  // Helper: get projected value for a CE code (override if editable, annualized otherwise)
  const pv = (code: string): number =>
    EDITABLE_CE_CODES.includes(code)
      ? parseFloat(overrides[code] || "0")
      : (items.find((i) => i.code === code)?.annualized_value ?? 0);

  // Compute projected subtotals from overrides
  const projVP = VP_CODES.reduce((acc, c) => acc + pv(c), 0);
  const PROJ_COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce12_oneri_diversi"];
  const projCP = PROJ_COST_CODES_ALL.reduce((acc, c) => acc + pv(c), 0);
  const projEbitda = projVP - (projCP - pv("ce09_ammortamenti"));
  const projEbit = projVP - projCP;

  const projFin = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"].reduce((acc, c) => acc + pv(c), 0)
    - pv("ce15_oneri_finanziari");
  const projRettifiche = pv("ce17_rettifiche_attivita_fin");
  const projStraord = pv("ce18_proventi_straordinari") - pv("ce19_oneri_straordinari");
  const projPBT = projEbit + projFin + projRettifiche + projStraord;
  const projNetProfit = projPBT - pv("ce20_imposte");

  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Proiezione
          </TableHead>
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Proiezione / Storico
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isEditable = EDITABLE_CE_CODES.includes(item.code);

            // Section headers
            if (isHeader) {
              const totalCols = 1 + colSpan + colSpan + colSpan + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            // Projected value: from overrides for editable, computed for synthetic rows
            let projValue: number;
            if (item.code === "_totale_vp") projValue = projVP;
            else if (item.code === "_totale_cp") projValue = projCP;
            else if (item.code === "_ebitda") projValue = projEbitda;
            else if (item.code === "_ebit") projValue = projEbit;
            else if (item.code === "_totale_fin") projValue = projFin;
            else if (item.code === "_totale_straord") projValue = projStraord;
            else if (item.code === "_profit_before_tax") projValue = projPBT;
            else if (item.code === "_net_profit") projValue = projNetProfit;
            else projValue = getProjectedValue(item);

            const delta = item.reference_value !== 0
              ? ((projValue - item.reference_value) / Math.abs(item.reference_value)) * 100
              : 0;
            const isPositive = delta > 1;
            const isNegative = delta < -1;

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>
                  {item.label}
                </TableCell>
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {/* Projection (editable for CE items, computed for totals) */}
                <TableCell className="text-right text-sm">
                  {isEditable ? (
                    <Input
                      type="text"
                      inputMode="numeric"
                      className="w-32 ml-auto text-right h-8 text-sm"
                      value={formatInputNumber(overrides[item.code] || "")}
                      onChange={(e) => onOverrideChange(item.code, parseInputNumber(e.target.value))}
                    />
                  ) : isPctRow ? (
                    formatPct(projValue)
                  ) : (
                    <span className="font-medium">{formatEuro(projValue)}</span>
                  )}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(projValue, projRevenue))}
                  </TableCell>
                )}
                {/* Delta % */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? (
                    <span className="text-muted-foreground">-</span>
                  ) : (
                    <span
                      className={
                        isPositive
                          ? "text-green-600 dark:text-green-400"
                          : isNegative
                          ? "text-red-600 dark:text-red-400"
                          : "text-muted-foreground"
                      }
                    >
                      {delta > 0 ? "+" : ""}{formatPct(delta)}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

// Extra-Accounting Alerts (Segnali Extracontabili)
const EXTRA_ALERT_DEFS: Array<{ key: string; label: string }> = [
  {
    key: "retribuzioni",
    label:
      "Debiti per retribuzione scaduti da almeno 30 giorni pari a oltre il 50% dell'ammontare complessivo mensile delle retribuzioni",
  },
  {
    key: "fornitori",
    label:
      "Debiti verso fornitori scaduti da almeno 90 giorni di ammontare superiore ai debiti non ancora scaduti",
  },
  {
    key: "banche",
    label:
      "Esposizioni nei confronti delle banche e altri intermediari finanziari scadute da più di 60 giorni o che abbiano superato il limite degli affidamenti da più di 60 giorni, purché rappresentino almeno il 5% del totale delle esposizioni",
  },
  {
    key: "inps",
    label:
      "INPS: ritardo di oltre 90 giorni nel versamento di contributi previdenziali di ammontare superiore al 30% di quelli dovuti nell'anno precedente e all'importo di €15.000 (con lavoratori subordinati) o €5.000 (senza lavoratori subordinati)",
  },
  {
    key: "inail",
    label:
      "INAIL: ritardo di oltre 90 giorni nel versamento di premi assicurativi di ammontare superiore a €5.000",
  },
  {
    key: "riscossione",
    label:
      "Agente della Riscossione: crediti affidati per la riscossione, auto dichiarati o definitivamente accertati e scaduti da oltre 90 giorni, superiori a €100.000 (imprese individuali), €200.000 (società di persone), €500.000 (società di capitali)",
  },
  {
    key: "iva",
    label:
      "Agenzia delle Entrate: debiti IVA scaduti e non versati superiori a €20.000, o superiori a €5.000 se di entità pari ad oltre il 10% del volume d'affari dell'anno precedente",
  },
];

function ExtraAccountingAlerts({
  alerts,
  onChange,
}: {
  alerts: Record<string, boolean>;
  onChange: (alerts: Record<string, boolean>) => void;
}) {
  const activeCount = Object.values(alerts).filter(Boolean).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Segnali Extracontabili</CardTitle>
        <CardDescription>
          Indicatori di allerta ai sensi del D.Lgs. 14/2019 (Codice della Crisi).
          Selezionare le condizioni riscontrate.
          {activeCount > 0 && (
            <span className="ml-2 text-red-600 dark:text-red-400 font-medium">
              {activeCount} segnale{activeCount > 1 ? "i" : ""} attivo{activeCount > 1 ? "i" : ""}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {EXTRA_ALERT_DEFS.map((def, idx) => (
            <div key={def.key} className="flex items-start gap-3">
              <Checkbox
                id={`alert-${def.key}`}
                checked={!!alerts[def.key]}
                onCheckedChange={(checked) =>
                  onChange({ ...alerts, [def.key]: !!checked })
                }
                className="mt-0.5"
              />
              <label
                htmlFor={`alert-${def.key}`}
                className="text-sm leading-relaxed cursor-pointer"
              >
                <span className="font-medium text-muted-foreground">{idx + 1}.</span>{" "}
                {def.label}
              </label>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// Indicatori Table Component
function IndicatoriTable({
  comparison,
  forecastBs,
  forecastIs,
  extraAlerts,
  showRating = true,
  hideProiezione = false,
}: {
  comparison: IntraYearComparison;
  forecastBs: Record<string, number>;
  forecastIs: Record<string, number>;
  extraAlerts: Record<string, boolean>;
  showRating?: boolean;
  hideProiezione?: boolean;
}) {
  // Build data maps from comparison
  const storicoBs: Record<string, number> = {};
  const storicoIs: Record<string, number> = {};
  for (const item of comparison.balance_items) {
    storicoBs[item.code] = item.reference_value;
  }
  for (const item of comparison.income_items) {
    storicoIs[item.code] = item.reference_value;
  }

  // Infrannuale: BS point-in-time, IS annualized
  const infraBs: Record<string, number> = {};
  const infraIs: Record<string, number> = {};
  const annFactor = 12 / comparison.period_months;
  for (const item of comparison.balance_items) {
    infraBs[item.code] = item.partial_value;
  }
  for (const item of comparison.income_items) {
    infraIs[item.code] = item.partial_value * annFactor;
  }

  const storicoInd = computeIndicators(storicoBs, storicoIs);
  const infraInd = computeIndicators(infraBs, infraIs);

  // Check if projection data exists (forecastBs/Is are {} when forecast_years is empty)
  const hasProiezione = Object.keys(forecastBs).length > 0 && Object.keys(forecastIs).length > 0;
  const proiezioneInd = hasProiezione ? computeIndicators(forecastBs, forecastIs) : null;

  const formatIndicatorValue = (value: number, format: "euro" | "pct" | "ratio") => {
    if (format === "euro") return formatEuro(value);
    if (format === "pct") return formatPct(value);
    return `${value.toFixed(2)}x`;
  };

  // Compute scores for each column
  const storicoScores = INDICATOR_DEFS.map((d) => scoreIndicator(d.key, storicoInd));
  const infraScores = INDICATOR_DEFS.map((d) => scoreIndicator(d.key, infraInd));
  const proiezioneScores = proiezioneInd
    ? INDICATOR_DEFS.map((d) => scoreIndicator(d.key, proiezioneInd))
    : null;

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;

  // Crisis ratings: storico uses 0 alerts (historical), infra+proiezione include current alerts
  const storicoRating = computeCrisisRating(storicoScores, 0);
  const infraRating = computeCrisisRating(infraScores, alertCount);
  const proiezioneRating = proiezioneScores
    ? computeCrisisRating(proiezioneScores, alertCount)
    : null;

  const oltreCount = (scores: number[]) => scores.filter((s) => s < 0.33).length;

  return (
    <div className="space-y-4">
      {/* Overall Rating Cards - only shown after "Calcola Rating" */}
      {showRating && (
        <div className={cn("grid gap-4", hideProiezione ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${comparison.reference_year}`, rating: storicoRating, oltre: oltreCount(storicoScores), alerts: 0 },
            { label: `Infrann. ${comparison.period_months}M ${comparison.partial_year}`, rating: infraRating, oltre: oltreCount(infraScores), alerts: alertCount },
            ...(!hideProiezione ? [{
              label: `Proiezione ${comparison.partial_year}`,
              rating: proiezioneRating,
              oltre: proiezioneScores ? oltreCount(proiezioneScores) : null,
              alerts: alertCount,
            }] : []),
          ].map((col) => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                {col.rating ? (
                  <p className={cn("text-2xl font-bold", col.rating.color)}>
                    {col.rating.code}
                  </p>
                ) : (
                  <p className="text-2xl font-bold text-muted-foreground">—</p>
                )}
              </div>
              <div className="text-right">
                {col.rating ? (
                  <>
                    <p className={cn("text-sm font-medium", col.rating.color)}>
                      {col.rating.label}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {col.oltre}/14 oltre{col.alerts > 0 ? ` + ${col.alerts} segn.` : ""}
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Genera proiezione
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Indicator Detail Table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Indicatore</TableHead>
            <TableHead className="text-right">
              Storico {comparison.reference_year}
            </TableHead>
            <TableHead className="text-right">
              Infrann. {comparison.period_months}M {comparison.partial_year}
            </TableHead>
            {!hideProiezione && (
              <TableHead className="text-right">
                Proiezione {comparison.partial_year}
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {INDICATOR_DEFS.map((def, idx) => {
            const sv = storicoInd[def.key];
            const iv = infraInd[def.key];
            const ss = storicoScores[idx];
            const is_ = infraScores[idx];

            return (
              <TableRow key={def.key}>
                <TableCell className="font-medium">{def.label}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-muted-foreground">
                      {formatIndicatorValue(sv, def.format)}
                    </span>
                    {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(ss))} />}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span>{formatIndicatorValue(iv, def.format)}</span>
                    {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(is_))} />}
                  </span>
                </TableCell>
                {!hideProiezione && (
                  <TableCell className="text-right">
                    {proiezioneInd && proiezioneScores ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="font-medium">
                          {formatIndicatorValue(proiezioneInd[def.key], def.format)}
                        </span>
                        {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(proiezioneScores[idx]))} />}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// Print-ready view for PDF generation via Playwright
function StampaContent({
  comparison,
  overrides,
  projectedBS,
  forecastBs,
  forecastIs,
  extraAlerts,
  companyName,
  fiscalYear,
  periodMonths,
  companyId,
  scenarioId,
  onBeforePromote,
}: {
  comparison: IntraYearComparison;
  overrides: Record<string, string>;
  projectedBS: IntraYearComparisonItem[];
  forecastBs: Record<string, number>;
  forecastIs: Record<string, number>;
  extraAlerts: Record<string, boolean>;
  companyName: string;
  fiscalYear: number;
  periodMonths: number;
  companyId?: number;
  scenarioId?: number;
  onBeforePromote?: () => Promise<void>;
}) {
  const router = useRouter();
  const { refreshCompanies, refreshYears } = useApp();
  const [promoting, setPromoting] = useState(false);
  const refYear = comparison.reference_year;
  const partialYear = comparison.partial_year;
  const annFactor = 12 / periodMonths;

  // --- P&L data ---
  const incomeItems = buildIncomeItemsWithEbitda(comparison.income_items, periodMonths);
  const projCEVal = (code: string) => parseFloat(overrides[code] || "0");

  // Helper: get projected value for a CE code
  const spv = (code: string): number =>
    EDITABLE_CE_CODES.includes(code)
      ? projCEVal(code)
      : (comparison.income_items.find(i => i.code === code)?.annualized_value ?? 0);

  const projVP = VP_CODES.reduce((acc, c) => acc + spv(c), 0);
  const STAMPA_COST_CODES = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce12_oneri_diversi"];
  const projCP = STAMPA_COST_CODES.reduce((acc, c) => acc + spv(c), 0);
  const projEbitda = projVP - (projCP - spv("ce09_ammortamenti"));
  const projEbit = projVP - projCP;
  const projRevenue = projCEVal("ce01_ricavi_vendite");

  const projFin = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"].reduce((acc, c) => acc + spv(c), 0)
    - spv("ce15_oneri_finanziari");
  const projRettifiche = spv("ce17_rettifiche_attivita_fin");
  const projStraord = spv("ce18_proventi_straordinari") - spv("ce19_oneri_straordinari");
  const projPBT = projEbit + projFin + projRettifiche + projStraord;
  const projNetProfit = projPBT - spv("ce20_imposte");

  const getProjectedCE = (item: IntraYearComparisonItem): number => {
    if (item.code === "_totale_vp") return projVP;
    if (item.code === "_totale_cp") return projCP;
    if (item.code === "_ebitda") return projEbitda;
    if (item.code === "_ebit") return projEbit;
    if (item.code === "_totale_fin") return projFin;
    if (item.code === "_totale_straord") return projStraord;
    if (item.code === "_profit_before_tax") return projPBT;
    if (item.code === "_net_profit") return projNetProfit;
    if (EDITABLE_CE_CODES.includes(item.code)) return projCEVal(item.code);
    return item.annualized_value;
  };

  // --- BS data ---
  const balanceItems = buildBalanceItemsWithTotals(comparison.balance_items);
  const projBSMap = new Map(projectedBS.map(i => [i.code, i.annualized_value]));

  // --- Indicators ---
  const storicoBs: Record<string, number> = {};
  const storicoIs: Record<string, number> = {};
  for (const item of comparison.balance_items) storicoBs[item.code] = item.reference_value;
  for (const item of comparison.income_items) storicoIs[item.code] = item.reference_value;

  const infraBs: Record<string, number> = {};
  const infraIs: Record<string, number> = {};
  for (const item of comparison.balance_items) infraBs[item.code] = item.partial_value;
  for (const item of comparison.income_items) infraIs[item.code] = item.partial_value * annFactor;

  const storicoInd = computeIndicators(storicoBs, storicoIs);
  const infraInd = computeIndicators(infraBs, infraIs);
  const proiezioneInd = computeIndicators(forecastBs, forecastIs);

  const storicoScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, storicoInd));
  const infraScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, infraInd));
  const proiezioneScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, proiezioneInd));

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;
  const storicoRating = computeCrisisRating(storicoScores, 0);
  const infraRating = computeCrisisRating(infraScores, alertCount);
  const proiezioneRating = computeCrisisRating(proiezioneScores, alertCount);

  const oltreCount = (scores: number[]) => scores.filter(s => s < 0.33).length;

  const formatInd = (value: number, format: "euro" | "pct" | "ratio") => {
    if (format === "euro") return formatEuro(value);
    if (format === "pct") return formatPct(value);
    return `${value.toFixed(2)}x`;
  };

  // Helper: delta % between two values
  const deltaFmt = (proj: number, ref: number) => {
    if (ref === 0) return <span className="text-muted-foreground">-</span>;
    const d = ((proj - ref) / Math.abs(ref)) * 100;
    return (
      <span className={d > 1 ? "text-green-600 dark:text-green-400" : d < -1 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>
        {d > 0 ? "+" : ""}{formatPct(d)}
      </span>
    );
  };

  // Filter for visible rows
  const visibleIncome = incomeItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);
  const visibleBalance = balanceItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);

  return (
    <div id="stampa-content" className="space-y-8 print:space-y-6 bg-white dark:bg-slate-950 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 -mt-8 pt-8 pb-8">
      {/* Action buttons */}
      <div className="flex justify-end gap-2 print:hidden">
        <Button onClick={() => window.print()} variant="outline">
          <Printer className="h-4 w-4 mr-2" />
          Stampa PDF
        </Button>
        {companyId && scenarioId && (
          <Button
            onClick={async () => {
              setPromoting(true);
              try {
                if (onBeforePromote) await onBeforePromote();
                await promoteProjection(companyId, scenarioId);
                await refreshCompanies();
                await refreshYears();
                toast.success("Proiezione confermata come anno completo");
                router.push("/budget");
              } catch (err: unknown) {
                const detail = axios.isAxiosError(err)
                  ? (err.response?.data?.detail ?? "Errore durante la promozione")
                  : "Errore durante la promozione";
                toast.error(detail);
              } finally {
                setPromoting(false);
              }
            }}
            disabled={promoting}
          >
            {promoting ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4 mr-2" />
            )}
            {periodMonths === 12 ? "Conferma e passa al Budget" : "Conferma Proiezione e passa al Budget"}
          </Button>
        )}
      </div>

      {/* Header */}
      <div className="text-center space-y-1 print:mb-4">
        <h1 className="text-xl font-bold">{companyName}</h1>
        <p className="text-sm text-muted-foreground">
          Analisi Infrannuale {periodMonths === 12 ? "" : `${periodMonths}M `}{partialYear}{periodMonths !== 12 ? ` — Proiezione 12M ${partialYear}` : ""}
        </p>
        <p className="text-xs text-muted-foreground">
          Anno di riferimento: {refYear} | Data: {new Date().toLocaleDateString("it-IT")}
        </p>
      </div>

      {/* 1. CE CONFRONTO: Storico | Infrannuale | Infrann./Storico */}
      <div className="print:break-before-avoid">
        <h2 className="text-base font-semibold mb-2">
          Conto Economico — Confronto {periodMonths}M {partialYear} vs 12M {refYear}
        </h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Voce</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrannuale {periodMonths}M</TableHead>
              <TableHead className="text-right">Infrann./Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleIncome.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
                "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={4} className="text-sm font-bold py-2">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>{item.label}</TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {deltaFmt(item.partial_value, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* 2. SP CONFRONTO: Storico | Infrannuale | Infrann./Storico */}
      <div className="print:break-before-page">
        <h2 className="text-base font-semibold mb-2">
          Stato Patrimoniale — Confronto
        </h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Voce</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrannuale {periodMonths}M</TableHead>
              <TableHead className="text-right">Infrann./Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleBalance.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_attivo", "_totale_passivo",
                "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={4} className="text-sm font-bold py-2">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>{item.label}</TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {deltaFmt(item.partial_value, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* 3. CE PROIEZIONE: Storico | Infrannuale | Proiezione | Proiez./Storico (hidden when 12M) */}
      {periodMonths !== 12 && (
      <div className="print:break-before-page">
        <h2 className="text-base font-semibold mb-2">
          Conto Economico — Proiezione {partialYear}
        </h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Voce</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrannuale {periodMonths}M</TableHead>
              <TableHead className="text-right">Proiezione {partialYear}</TableHead>
              <TableHead className="text-right">Proiez./Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleIncome.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
                "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
              const projValue = getProjectedCE(item);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={5} className="text-sm font-bold py-2">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>{item.label}</TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium">
                    {formatEuro(projValue)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {deltaFmt(projValue, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      )}

      {/* 4. SP PROIEZIONE: Storico | Infrannuale | Proiezione | Proiez./Storico (hidden when 12M) */}
      {periodMonths !== 12 && (
      <div>
        <h2 className="text-base font-semibold mb-2">
          Stato Patrimoniale — Proiezione {partialYear}
        </h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Voce</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrannuale {periodMonths}M</TableHead>
              <TableHead className="text-right">Proiezione {partialYear}</TableHead>
              <TableHead className="text-right">Proiez./Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleBalance.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_attivo", "_totale_passivo",
                "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
              const projVal = projBSMap.get(item.code) ?? NaN;
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={5} className="text-sm font-bold py-2">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold" : "font-medium")}>{item.label}</TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium">
                    {isNaN(projVal) ? <span className="text-muted-foreground">-</span> : formatEuro(projVal)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {isNaN(projVal) ? (
                      <span className="text-muted-foreground">-</span>
                    ) : (
                      deltaFmt(projVal, item.reference_value)
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      )}

      {/* 5. INDICATORI DELLA CRISI D'IMPRESA */}
      <div className="print:break-before-page">
        <h2 className="text-base font-semibold mb-2">Indicatori della Crisi d&apos;Impresa</h2>

        {/* Rating cards */}
        <div className={cn("grid gap-4 mb-4", periodMonths === 12 ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${refYear}`, rating: storicoRating, oltre: oltreCount(storicoScores), alerts: 0 },
            { label: `Infrann. ${periodMonths}M ${partialYear}`, rating: infraRating, oltre: oltreCount(infraScores), alerts: alertCount },
            ...(periodMonths !== 12 ? [{ label: `Proiezione ${partialYear}`, rating: proiezioneRating, oltre: oltreCount(proiezioneScores), alerts: alertCount }] : []),
          ].map(col => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                <p className={cn("text-2xl font-bold", col.rating.color)}>{col.rating.code}</p>
              </div>
              <div className="text-right">
                <p className={cn("text-sm font-medium", col.rating.color)}>{col.rating.label}</p>
                <p className="text-xs text-muted-foreground">
                  {col.oltre}/14 oltre{col.alerts > 0 ? ` + ${col.alerts} segn.` : ""}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Indicator detail table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Indicatore</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrann. {periodMonths}M</TableHead>
              {periodMonths !== 12 && <TableHead className="text-right">Proiezione {partialYear}</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {INDICATOR_DEFS.map((def, idx) => (
              <TableRow key={def.key}>
                <TableCell className="font-medium">{def.label}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-muted-foreground">{formatInd(storicoInd[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(storicoScores[idx]))} />
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span>{formatInd(infraInd[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(infraScores[idx]))} />
                  </span>
                </TableCell>
                {periodMonths !== 12 && (
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-2">
                      <span className="font-medium">{formatInd(proiezioneInd[def.key], def.format)}</span>
                      <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(proiezioneScores[idx]))} />
                    </span>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* 6. SEGNALI EXTRACONTABILI */}
      <div>
        <h2 className="text-base font-semibold mb-2">
          Segnali Extracontabili
          {alertCount > 0 && (
            <span className="ml-2 text-sm font-normal text-red-600 dark:text-red-400">
              ({alertCount} segnale{alertCount > 1 ? "i" : ""} attivo{alertCount > 1 ? "i" : ""})
            </span>
          )}
        </h2>
        <div className="rounded-lg border border-border p-4 space-y-2">
          {EXTRA_ALERT_DEFS.map((def, idx) => {
            const isActive = !!extraAlerts[def.key];
            return (
              <div key={def.key} className="flex items-start gap-2 text-sm">
                <span className={cn(
                  "mt-0.5 inline-block h-4 w-4 shrink-0 rounded border text-center text-xs leading-4",
                  isActive
                    ? "bg-red-600 border-red-600 text-white dark:bg-red-500 dark:border-red-500"
                    : "border-border text-transparent"
                )}>
                  {isActive ? "✓" : ""}
                </span>
                <span className={isActive ? "font-medium" : "text-muted-foreground"}>
                  <span className="font-medium">{idx + 1}.</span> {def.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
