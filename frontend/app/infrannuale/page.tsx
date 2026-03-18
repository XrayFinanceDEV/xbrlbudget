"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
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
  getAdjustableFinancialYear,
  saveAdjustments,
} from "@/lib/api";
import axios from "axios";
import type {
  Company,
  BudgetScenario,
  IntraYearComparison,
  IntraYearComparisonItem,
  ScenarioAnalysis,
  AdjustableFinancialYear,
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
  Pencil,
  RotateCcw,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
  "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari",
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

  const v = (code: string, key: "partial_value" | "reference_value" | "annualized_value" | "prior_value") =>
    byCode.get(code)?.[key] ?? 0;

  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number, prior: number = 0): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    prior_value: prior,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0, 0);

  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, prior_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Relabel
  const relabel: Record<string, string> = {
    sp01_crediti_soci: "A) Crediti verso soci per versamenti ancora dovuti",
    sp02_immob_immateriali: "I - Immobilizzazioni immateriali",
    sp03_immob_materiali: "II - Immobilizzazioni materiali",
    sp04_immob_finanziarie: "III - Immobilizzazioni finanziarie",
    sp05_rimanenze: "I - Rimanenze",
    sp06_crediti_breve: "II - Crediti (entro esercizio successivo)",
    sp06a_crediti_clienti_breve: "  1) Verso clienti",
    sp06b_crediti_controllate_breve: "  2) Verso imprese controllate",
    sp06c_crediti_collegate_breve: "  3) Verso imprese collegate",
    sp06d_crediti_controllanti_breve: "  4) Verso controllanti",
    sp06e_crediti_tributari_breve: "  5-bis) Crediti tributari",
    sp06f_imposte_anticipate_breve: "  5-ter) Imposte anticipate",
    sp06g_crediti_altri_breve: "  5-quater) Verso altri",
    sp07_crediti_lungo: "II - Crediti (oltre esercizio successivo)",
    sp07a_crediti_clienti_lungo: "  1) Verso clienti",
    sp07b_crediti_controllate_lungo: "  2) Verso imprese controllate",
    sp07c_crediti_collegate_lungo: "  3) Verso imprese collegate",
    sp07d_crediti_controllanti_lungo: "  4) Verso controllanti",
    sp07e_crediti_tributari_lungo: "  5-bis) Crediti tributari",
    sp07f_imposte_anticipate_lungo: "  5-ter) Imposte anticipate",
    sp07g_crediti_altri_lungo: "  5-quater) Verso altri",
    sp08_attivita_finanziarie: "III - Attività finanziarie che non costituiscono immobilizzazioni",
    sp09_disponibilita_liquide: "IV - Disponibilità liquide",
    sp10_ratei_risconti_attivi: "D) Ratei e risconti attivi",
    sp11_capitale: "I - Capitale",
    sp12_riserve: "II-VIII - Riserve",
    sp13_utile_perdita: "IX - Utile (perdita) dell'esercizio",
    sp14_fondi_rischi: "B) Fondi per rischi e oneri",
    sp15_tfr: "C) Trattamento di fine rapporto di lavoro subordinato",
    sp16_debiti_breve: "Debiti (entro esercizio successivo)",
    sp16a_debiti_banche_breve: "  1) Debiti verso banche",
    sp16b_debiti_altri_finanz_breve: "  2) Debiti verso altri finanziatori",
    sp16c_debiti_obbligazioni_breve: "  3) Debiti obbligazionari",
    sp16d_debiti_fornitori_breve: "  7) Debiti verso fornitori",
    sp16e_debiti_tributari_breve: "  12) Debiti tributari",
    sp16f_debiti_previdenza_breve: "  13) Debiti previdenziali",
    sp16g_altri_debiti_breve: "  14) Altri debiti",
    sp17_debiti_lungo: "Debiti (oltre esercizio successivo)",
    sp17a_debiti_banche_lungo: "  1) Debiti verso banche",
    sp17b_debiti_altri_finanz_lungo: "  2) Debiti verso altri finanziatori",
    sp17c_debiti_obbligazioni_lungo: "  3) Debiti obbligazionari",
    sp17d_debiti_fornitori_lungo: "  7) Debiti verso fornitori",
    sp17e_debiti_tributari_lungo: "  12) Debiti tributari",
    sp17f_debiti_previdenza_lungo: "  13) Debiti previdenziali",
    sp17g_altri_debiti_lungo: "  14) Altri debiti",
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

  const sumCodes = (codes: string[], key: "partial_value" | "reference_value" | "annualized_value" | "prior_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);

  const totImmobP = sumCodes(IMMOB_CODES, "partial_value");
  const totImmobR = sumCodes(IMMOB_CODES, "reference_value");
  const totImmobA = sumCodes(IMMOB_CODES, "annualized_value");
  const totImmobPr = sumCodes(IMMOB_CODES, "prior_value");

  const totCircP = sumCodes(CIRC_CODES, "partial_value");
  const totCircR = sumCodes(CIRC_CODES, "reference_value");
  const totCircA = sumCodes(CIRC_CODES, "annualized_value");
  const totCircPr = sumCodes(CIRC_CODES, "prior_value");

  const totAttivoP = sumCodes(ATTIVO_CODES, "partial_value");
  const totAttivoR = sumCodes(ATTIVO_CODES, "reference_value");
  const totAttivoA = sumCodes(ATTIVO_CODES, "annualized_value");
  const totAttivoPr = sumCodes(ATTIVO_CODES, "prior_value");

  const totPNP = sumCodes(PN_CODES, "partial_value");
  const totPNR = sumCodes(PN_CODES, "reference_value");
  const totPNA = sumCodes(PN_CODES, "annualized_value");
  const totPNPr = sumCodes(PN_CODES, "prior_value");

  const totDebtP = sumCodes(DEBT_CODES, "partial_value");
  const totDebtR = sumCodes(DEBT_CODES, "reference_value");
  const totDebtA = sumCodes(DEBT_CODES, "annualized_value");
  const totDebtPr = sumCodes(DEBT_CODES, "prior_value");

  const totPassivoP = sumCodes(PASSIVO_CODES, "partial_value");
  const totPassivoR = sumCodes(PASSIVO_CODES, "reference_value");
  const totPassivoA = sumCodes(PASSIVO_CODES, "annualized_value");
  const totPassivoPr = sumCodes(PASSIVO_CODES, "prior_value");

  return [
    // ATTIVO
    hdr("_hdr_attivo", "ATTIVO"),
    labeled("sp01_crediti_soci"),
    // B) IMMOBILIZZAZIONI
    hdr("_hdr_immob", "B) IMMOBILIZZAZIONI"),
    labeled("sp02_immob_immateriali"),
    labeled("sp03_immob_materiali"),
    labeled("sp04_immob_finanziarie"),
    makeRow("_totale_immob", "Totale Immobilizzazioni", totImmobP, totImmobR, totImmobA, totImmobPr),
    // C) ATTIVO CIRCOLANTE
    hdr("_hdr_circ", "C) ATTIVO CIRCOLANTE"),
    labeled("sp05_rimanenze"),
    labeled("sp06_crediti_breve"),
    labeled("sp06a_crediti_clienti_breve"),
    labeled("sp06b_crediti_controllate_breve"),
    labeled("sp06c_crediti_collegate_breve"),
    labeled("sp06d_crediti_controllanti_breve"),
    labeled("sp06e_crediti_tributari_breve"),
    labeled("sp06f_imposte_anticipate_breve"),
    labeled("sp06g_crediti_altri_breve"),
    labeled("sp07_crediti_lungo"),
    labeled("sp07a_crediti_clienti_lungo"),
    labeled("sp07b_crediti_controllate_lungo"),
    labeled("sp07c_crediti_collegate_lungo"),
    labeled("sp07d_crediti_controllanti_lungo"),
    labeled("sp07e_crediti_tributari_lungo"),
    labeled("sp07f_imposte_anticipate_lungo"),
    labeled("sp07g_crediti_altri_lungo"),
    labeled("sp08_attivita_finanziarie"),
    labeled("sp09_disponibilita_liquide"),
    makeRow("_totale_circ", "Totale Attivo Circolante", totCircP, totCircR, totCircA, totCircPr),
    // D) Ratei
    labeled("sp10_ratei_risconti_attivi"),
    makeRow("_totale_attivo", "TOTALE ATTIVO", totAttivoP, totAttivoR, totAttivoA, totAttivoPr),
    // PASSIVO E PATRIMONIO NETTO
    hdr("_hdr_passivo", "PASSIVO E PATRIMONIO NETTO"),
    // A) PATRIMONIO NETTO
    hdr("_hdr_pn", "A) PATRIMONIO NETTO"),
    labeled("sp11_capitale"),
    labeled("sp12_riserve"),
    labeled("sp13_utile_perdita"),
    makeRow("_totale_pn", "Totale Patrimonio Netto", totPNP, totPNR, totPNA, totPNPr),
    // B) Fondi
    labeled("sp14_fondi_rischi"),
    // C) TFR
    labeled("sp15_tfr"),
    // D) DEBITI
    hdr("_hdr_debiti", "D) DEBITI"),
    labeled("sp16_debiti_breve"),
    labeled("sp16a_debiti_banche_breve"),
    labeled("sp16b_debiti_altri_finanz_breve"),
    labeled("sp16c_debiti_obbligazioni_breve"),
    labeled("sp16d_debiti_fornitori_breve"),
    labeled("sp16e_debiti_tributari_breve"),
    labeled("sp16f_debiti_previdenza_breve"),
    labeled("sp16g_altri_debiti_breve"),
    labeled("sp17_debiti_lungo"),
    labeled("sp17a_debiti_banche_lungo"),
    labeled("sp17b_debiti_altri_finanz_lungo"),
    labeled("sp17c_debiti_obbligazioni_lungo"),
    labeled("sp17d_debiti_fornitori_lungo"),
    labeled("sp17e_debiti_tributari_lungo"),
    labeled("sp17f_debiti_previdenza_lungo"),
    labeled("sp17g_altri_debiti_lungo"),
    makeRow("_totale_debiti", "Totale Debiti", totDebtP, totDebtR, totDebtA, totDebtPr),
    // E) Ratei passivi
    labeled("sp18_ratei_risconti_passivi"),
    makeRow("_totale_passivo", "TOTALE PASSIVO E PATRIMONIO NETTO", totPassivoP, totPassivoR, totPassivoA, totPassivoPr),
    // Differenza
    makeRow("_differenza", "DIFFERENZA (Attivo - Passivo)",
      totAttivoP - totPassivoP, totAttivoR - totPassivoR, totAttivoA - totPassivoA, totAttivoPr - totPassivoPr),
  ];
}

function buildIncomeItemsWithEbitda(
  items: IntraYearComparisonItem[],
  periodMonths: number,
): IntraYearComparisonItem[] {
  const byCode = new Map(items.map((i) => [i.code, i]));
  const factor = 12 / periodMonths;
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);

  const v = (code: string, key: "partial_value" | "reference_value" | "prior_value") =>
    byCode.get(code)?.[key] ?? 0;
  const ann = (code: string) => byCode.get(code)?.annualized_value ?? 0;
  const sum = (codes: string[], key: "partial_value" | "reference_value" | "prior_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);
  const sumAnn = (codes: string[]) =>
    codes.reduce((acc, c) => acc + ann(c), 0);

  // Lookup or zero-item helper
  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, prior_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Helper: create a synthetic row
  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number, prior: number = 0): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    prior_value: prior,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  // Header row (no values)
  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0, 0);

  // Subtotals
  const partialVP = sum(VP_CODES, "partial_value");
  const refVP = sum(VP_CODES, "reference_value");
  const priorVP = sum(VP_CODES, "prior_value");
  const annVP = sumAnn(VP_CODES);

  const COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
  const partialCP = sum(COST_CODES_ALL, "partial_value");
  const refCP = sum(COST_CODES_ALL, "reference_value");
  const priorCP = sum(COST_CODES_ALL, "prior_value");
  const annCP = sumAnn(COST_CODES_ALL);

  const partialEbitda = partialVP - (partialCP - v("ce09_ammortamenti", "partial_value"));
  const refEbitda = refVP - (refCP - v("ce09_ammortamenti", "reference_value"));
  const priorEbitda = priorVP - (priorCP - v("ce09_ammortamenti", "prior_value"));
  const annEbitda = annVP - (annCP - ann("ce09_ammortamenti"));

  const partialEbit = partialVP - partialCP;
  const refEbit = refVP - refCP;
  const priorEbit = priorVP - priorCP;
  const annEbit = annVP - annCP;

  const FIN_INCOME = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"];
  const FIN_COST = ["ce15_oneri_finanziari"];
  const partialFin = sum(FIN_INCOME, "partial_value") - sum(FIN_COST, "partial_value");
  const refFin = sum(FIN_INCOME, "reference_value") - sum(FIN_COST, "reference_value");
  const priorFin = sum(FIN_INCOME, "prior_value") - sum(FIN_COST, "prior_value");
  const annFin = sumAnn(FIN_INCOME) - sumAnn(FIN_COST);

  const partialStraord = v("ce18_proventi_straordinari", "partial_value") - v("ce19_oneri_straordinari", "partial_value");
  const refStraord = v("ce18_proventi_straordinari", "reference_value") - v("ce19_oneri_straordinari", "reference_value");
  const priorStraord = v("ce18_proventi_straordinari", "prior_value") - v("ce19_oneri_straordinari", "prior_value");
  const annStraord = ann("ce18_proventi_straordinari") - ann("ce19_oneri_straordinari");

  const partialRettifiche = v("ce17_rettifiche_attivita_fin", "partial_value");
  const refRettifiche = v("ce17_rettifiche_attivita_fin", "reference_value");
  const priorRettifiche = v("ce17_rettifiche_attivita_fin", "prior_value");
  const annRettifiche = ann("ce17_rettifiche_attivita_fin");

  const partialPBT = partialEbit + partialFin + partialRettifiche + partialStraord;
  const refPBT = refEbit + refFin + refRettifiche + refStraord;
  const priorPBT = priorEbit + priorFin + priorRettifiche + priorStraord;
  const annPBT = annEbit + annFin + annRettifiche + annStraord;

  const partialNetProfit = partialPBT - v("ce20_imposte", "partial_value");
  const refNetProfit = refPBT - v("ce20_imposte", "reference_value");
  const priorNetProfit = priorPBT - v("ce20_imposte", "prior_value");
  const annNetProfit = annPBT - ann("ce20_imposte");

  const partialRevenue = v("ce01_ricavi_vendite", "partial_value");
  const refRevenue = v("ce01_ricavi_vendite", "reference_value");

  // Relabel items to match IV CEE format
  const relabel: Record<string, string> = {
    ce01_ricavi_vendite: "1) Ricavi delle vendite e delle prestazioni",
    ce02_variazioni_rimanenze: "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti",
    ce03_lavori_interni: "4) Incrementi di immobilizzazioni per lavori interni",
    ce04_altri_ricavi: "5) Altri ricavi e proventi",
    ce05_materie_prime: "6) Per materie prime, sussidiarie, di consumo e di merci",
    ce06_servizi: "7) Per servizi",
    ce07_godimento_beni: "8) Per godimento di beni di terzi",
    ce08_costi_personale: "9) Per il personale",
    ce08b_salari_stipendi: "  a) Salari e stipendi",
    ce08c_oneri_sociali: "  b) Oneri sociali",
    ce08a_tfr_accrual: "  c) Trattamento di fine rapporto",
    ce08d_altri_costi_personale: "  e) Altri costi del personale",
    ce09_ammortamenti: "10) Ammortamenti e svalutazioni",
    ce09a_ammort_immateriali: "  a) Ammortamento immobilizzazioni immateriali",
    ce09b_ammort_materiali: "  b) Ammortamento immobilizzazioni materiali",
    ce09c_svalutazioni: "  c) Altre svalutazioni delle immobilizzazioni",
    ce09d_svalutazione_crediti: "  d) Svalutazione crediti attivo circolante",
    ce10_var_rimanenze_mat_prime: "11) Var. rimanenze di materie prime, suss., di cons. e merci",
    ce11_accantonamenti: "12) Accantonamenti per rischi",
    ce11b_altri_accantonamenti: "13) Altri accantonamenti",
    ce12_oneri_diversi: "14) Oneri diversi di gestione",
    ce13_proventi_partecipazioni: "15) Proventi da partecipazioni",
    ce14_altri_proventi_finanziari: "16) Altri proventi finanziari",
    ce15_oneri_finanziari: "17) Interessi e altri oneri finanziari",
    ce16_utili_perdite_cambi: "17-bis) Utili e perdite su cambi",
    ce17_rettifiche_attivita_fin: "Totale rettifiche di valore (18 - 19)",
    ce17a_rivalutazioni: "  18) Rivalutazioni",
    ce17b_svalutazioni: "  19) Svalutazioni",
    ce18_proventi_straordinari: "Proventi straordinari",
    ce19_oneri_straordinari: "Oneri straordinari",
    ce20_imposte: "20) Imposte sul reddito dell'esercizio",
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
    makeRow("_totale_vp", "Totale Valore della Produzione", partialVP, refVP, annVP, priorVP),
    // B) COSTI DELLA PRODUZIONE
    hdr("_hdr_b", "B) COSTI DELLA PRODUZIONE"),
    labeled("ce05_materie_prime"),
    labeled("ce06_servizi"),
    labeled("ce07_godimento_beni"),
    labeled("ce08_costi_personale"),
    labeled("ce08b_salari_stipendi"),
    labeled("ce08c_oneri_sociali"),
    labeled("ce08a_tfr_accrual"),
    labeled("ce08d_altri_costi_personale"),
    labeled("ce09_ammortamenti"),
    labeled("ce09a_ammort_immateriali"),
    labeled("ce09b_ammort_materiali"),
    labeled("ce09c_svalutazioni"),
    labeled("ce09d_svalutazione_crediti"),
    labeled("ce10_var_rimanenze_mat_prime"),
    labeled("ce11_accantonamenti"),
    labeled("ce11b_altri_accantonamenti"),
    labeled("ce12_oneri_diversi"),
    makeRow("_totale_cp", "Totale Costi della Produzione", partialCP, refCP, annCP, priorCP),
    makeRow("_ebitda", "EBITDA (MOL)", partialEbitda, refEbitda, annEbitda, priorEbitda),
    makeRow("_ebit", "EBIT (Risultato Operativo)", partialEbit, refEbit, annEbit, priorEbit),
    // C) PROVENTI E ONERI FINANZIARI
    hdr("_hdr_c", "C) PROVENTI E ONERI FINANZIARI"),
    labeled("ce13_proventi_partecipazioni"),
    labeled("ce14_altri_proventi_finanziari"),
    labeled("ce15_oneri_finanziari"),
    labeled("ce16_utili_perdite_cambi"),
    makeRow("_totale_fin", "Totale proventi e oneri finanziari (15 + 16 - 17 +/- 17-bis)", partialFin, refFin, annFin, priorFin),
    // D) RETTIFICHE DI VALORE
    hdr("_hdr_d", "D) RETTIFICHE DI VALORE DI ATTIVITÀ E PASSIVITÀ FINANZIARIE"),
    labeled("ce17a_rivalutazioni"),
    labeled("ce17b_svalutazioni"),
    labeled("ce17_rettifiche_attivita_fin"),
    // E) PROVENTI E ONERI STRAORDINARI
    hdr("_hdr_e", "E) PROVENTI E ONERI STRAORDINARI"),
    labeled("ce18_proventi_straordinari"),
    labeled("ce19_oneri_straordinari"),
    makeRow("_totale_straord", "Totale Proventi/Oneri Straordinari", partialStraord, refStraord, annStraord, priorStraord),
    // Risultato prima delle imposte
    makeRow("_profit_before_tax", "Risultato prima delle imposte (A - B +/- C +/- D +/- E)", partialPBT, refPBT, annPBT, priorPBT),
    labeled("ce20_imposte"),
    makeRow("_net_profit", "21) Utile (perdita) dell'esercizio", partialNetProfit, refNetProfit, annNetProfit, priorNetProfit),
  ];
}

// ===== PROPOSAL RULES =====
// When a field is edited, propose a counterpart adjustment shown in the review dialog.
// "same" = counterpart moves in same direction as delta (e.g. cost up → liability up)
// "inverse" = counterpart moves opposite (e.g. depreciation up → asset down)
interface ProposalRule {
  editable: string;
  counterpart: string;
  direction: "same" | "inverse";
  explanation: string; // Italian description of the double-entry logic
  // Optional: allow splitting the counterpart amount between two fields
  splitAlt?: { field: string; label: string };
  // Optional: alternative counterpart when the delta is negative (e.g. credit decrease → loss, not revenue decrease)
  counterpartNeg?: string;
  directionNeg?: "same" | "inverse";
  explanationNeg?: string;
  splitAltNeg?: { field: string; label: string };
}
const PROPOSAL_RULES: ProposalRule[] = [
  // ===== BS ATTIVO → CE =====
  { editable: "sp01_crediti_soci", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs soci → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti vs soci → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp02_immob_immateriali", counterpart: "ce03_lavori_interni", direction: "same", explanation: "Più immob. immateriali → più incrementi per lavori interni" },
  { editable: "sp03_immob_materiali", counterpart: "ce03_lavori_interni", direction: "same", explanation: "Più immob. materiali → più incrementi per lavori interni" },
  { editable: "sp04_immob_finanziarie", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più immob. finanziarie → più proventi finanziari" },
  { editable: "sp05_rimanenze", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più rimanenze → variazione positiva rimanenze" },
  { editable: "sp05a_materie_prime", counterpart: "ce10_var_rimanenze_mat_prime", direction: "inverse", explanation: "Più rimanenze materie → meno variazione mat. prime (costo)" },
  { editable: "sp05b_prodotti_in_corso", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più prodotti in c/lav → variazione positiva rimanenze" },
  { editable: "sp05c_lavori_in_corso", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più lavori in corso → variazione positiva rimanenze" },
  { editable: "sp05d_prodotti_finiti", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più prodotti finiti → variazione positiva rimanenze" },
  { editable: "sp05e_acconti", counterpart: "ce05_materie_prime", direction: "same", explanation: "Più acconti a fornitori → più costi materie prime" },
  { editable: "sp06_crediti_breve", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti commerciali → più ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06a_crediti_clienti_breve", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti vs clienti → più ricavi vendite", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti clienti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06b_crediti_controllate_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllate → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllate → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06c_crediti_collegate_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs collegate → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti collegate → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06d_crediti_controllanti_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllanti → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllanti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06e_crediti_tributari_breve", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più crediti tributari → meno imposte" },
  { editable: "sp06f_imposte_anticipate_breve", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più imposte anticipate → meno imposte correnti" },
  { editable: "sp06g_crediti_altri_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti diversi → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti diversi → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07_crediti_lungo", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti oltre → più ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07a_crediti_clienti_lungo", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti clienti oltre → più ricavi vendite", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti clienti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07b_crediti_controllate_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllate oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllate oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07c_crediti_collegate_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs collegate oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti collegate oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07d_crediti_controllanti_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllanti oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllanti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07e_crediti_tributari_lungo", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più crediti tributari oltre → meno imposte" },
  { editable: "sp07f_imposte_anticipate_lungo", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più imposte anticipate oltre → meno imposte correnti" },
  { editable: "sp07g_crediti_altri_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti diversi oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti diversi oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp08_attivita_finanziarie", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più attività finanziarie → più proventi finanziari" },
  { editable: "sp09_disponibilita_liquide", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più liquidità → più ricavi (incasso)" },
  { editable: "sp10_ratei_risconti_attivi", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più ratei attivi → più altri ricavi di competenza" },
  // ===== BS PASSIVO → CE =====
  { editable: "sp11_capitale", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più capitale → più liquidità (conferimento)" },
  { editable: "sp12_riserve", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserve → più liquidità (conferimento)" },
  { editable: "sp12g_utili_perdite_portati", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più utili a nuovo → più liquidità" },
  { editable: "sp14_fondi_rischi", counterpart: "ce11_accantonamenti", direction: "same", explanation: "Più fondi rischi → più accantonamenti" },
  { editable: "sp15_tfr", counterpart: "ce08a_tfr_accrual", direction: "same", explanation: "Più fondo TFR → più accantonamento TFR" },
  { editable: "sp16a_debiti_banche_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti vs banche → più oneri finanziari" },
  { editable: "sp16b_debiti_altri_finanz_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti finanziari → più oneri finanziari" },
  { editable: "sp16c_debiti_obbligazioni_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti obbligazionari → più oneri finanziari" },
  { editable: "sp16d_debiti_fornitori_breve", counterpart: "ce06_servizi", direction: "same", explanation: "Più debiti fornitori → più costi per servizi / materie prime", splitAlt: { field: "ce05_materie_prime", label: "6) Per materie prime" } },
  { editable: "sp16e_debiti_tributari_breve", counterpart: "ce20_imposte", direction: "same", explanation: "Più debiti tributari → più imposte" },
  { editable: "sp16f_debiti_previdenza_breve", counterpart: "ce08_costi_personale", direction: "same", explanation: "Più debiti previdenziali → più costi del personale" },
  { editable: "sp16g_altri_debiti_breve", counterpart: "ce12_oneri_diversi", direction: "same", explanation: "Più altri debiti → più oneri diversi" },
  { editable: "sp17a_debiti_banche_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti vs banche lungo → più oneri finanziari" },
  { editable: "sp17b_debiti_altri_finanz_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti finanziari lungo → più oneri finanziari" },
  { editable: "sp17c_debiti_obbligazioni_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti obbligazionari lungo → più oneri finanziari" },
  { editable: "sp17d_debiti_fornitori_lungo", counterpart: "ce06_servizi", direction: "same", explanation: "Più debiti fornitori lungo → più costi per servizi / materie prime", splitAlt: { field: "ce05_materie_prime", label: "6) Per materie prime" } },
  { editable: "sp17e_debiti_tributari_lungo", counterpart: "ce20_imposte", direction: "same", explanation: "Più debiti tributari lungo → più imposte" },
  { editable: "sp17f_debiti_previdenza_lungo", counterpart: "ce08_costi_personale", direction: "same", explanation: "Più debiti previdenziali lungo → più costi del personale" },
  { editable: "sp17g_altri_debiti_lungo", counterpart: "ce12_oneri_diversi", direction: "same", explanation: "Più altri debiti lungo → più oneri diversi" },
  { editable: "sp18_ratei_risconti_passivi", counterpart: "ce07_godimento_beni", direction: "same", explanation: "Più ratei passivi → più godimento beni di terzi" },
  // ===== CE → BS =====
  { editable: "ce01_ricavi_vendite", counterpart: "sp06a_crediti_clienti_breve", direction: "same", explanation: "Più ricavi → più crediti vs clienti" },
  { editable: "ce04_altri_ricavi", counterpart: "sp06g_crediti_altri_breve", direction: "same", explanation: "Più altri ricavi → più crediti diversi" },
  { editable: "ce05_materie_prime", counterpart: "sp16d_debiti_fornitori_breve", direction: "same", explanation: "Più costi materie prime → più debiti vs fornitori" },
  { editable: "ce06_servizi", counterpart: "sp16d_debiti_fornitori_breve", direction: "same", explanation: "Più costi servizi → più debiti vs fornitori" },
  { editable: "ce07_godimento_beni", counterpart: "sp18_ratei_risconti_passivi", direction: "same", explanation: "Più godimento beni terzi → più ratei e risconti passivi" },
  { editable: "ce08_costi_personale", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più costi personale → più debiti previdenziali" },
  { editable: "ce08b_salari_stipendi", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più salari e stipendi → più debiti previdenziali" },
  { editable: "ce08c_oneri_sociali", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più oneri sociali → più debiti previdenziali" },
  { editable: "ce08a_tfr_accrual", counterpart: "sp15_tfr", direction: "same", explanation: "Più TFR accantonato → più fondo TFR" },
  { editable: "ce08d_altri_costi_personale", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più altri costi personale → più altri debiti" },
  { editable: "ce09a_ammort_immateriali", counterpart: "sp02_immob_immateriali", direction: "inverse", explanation: "Più ammortamento → meno immobilizzazioni immateriali" },
  { editable: "ce09b_ammort_materiali", counterpart: "sp03_immob_materiali", direction: "inverse", explanation: "Più ammortamento → meno immobilizzazioni materiali" },
  { editable: "ce09c_svalutazioni", counterpart: "sp04_immob_finanziarie", direction: "inverse", explanation: "Più svalutazioni → meno immobilizzazioni finanziarie" },
  { editable: "ce09d_svalutazione_crediti", counterpart: "sp06_crediti_breve", direction: "inverse", explanation: "Più svalutazione crediti → meno crediti commerciali" },
  { editable: "ce11_accantonamenti", counterpart: "sp14_fondi_rischi", direction: "same", explanation: "Più accantonamenti rischi → più fondi per rischi e oneri" },
  { editable: "ce11b_altri_accantonamenti", counterpart: "sp14_fondi_rischi", direction: "same", explanation: "Più altri accantonamenti → più fondi rischi" },
  { editable: "ce12_oneri_diversi", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più oneri diversi → più altri debiti" },
  { editable: "ce13_proventi_partecipazioni", counterpart: "sp04_immob_finanziarie", direction: "same", explanation: "Più proventi partecipazioni → più immob. finanziarie" },
  { editable: "ce14_altri_proventi_finanziari", counterpart: "sp08_attivita_finanziarie", direction: "same", explanation: "Più proventi finanziari → più attività finanziarie" },
  { editable: "ce15_oneri_finanziari", counterpart: "sp16a_debiti_banche_breve", direction: "same", explanation: "Più oneri finanziari → più debiti vs banche" },
  { editable: "ce16_utili_perdite_cambi", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più utili su cambi → più liquidità" },
  { editable: "ce17a_rivalutazioni", counterpart: "sp04_immob_finanziarie", direction: "same", explanation: "Più rivalutazioni → più immob. finanziarie" },
  { editable: "ce17b_svalutazioni", counterpart: "sp04_immob_finanziarie", direction: "inverse", explanation: "Più svalutazioni → meno immob. finanziarie" },
  { editable: "ce18_proventi_straordinari", counterpart: "sp06g_crediti_altri_breve", direction: "same", explanation: "Più proventi straordinari → più crediti diversi" },
  { editable: "ce19_oneri_straordinari", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più oneri straordinari → più altri debiti" },
  { editable: "ce20_imposte", counterpart: "sp16e_debiti_tributari_breve", direction: "same", explanation: "Più imposte → più debiti tributari" },
];

// All editable fields = all proposal rule editables (every editable field has a proposal rule)
const EDITABLE_RETTIFICHE = new Set(PROPOSAL_RULES.map((r) => r.editable));
// Fields that are counterpart targets — shown with special styling after proposals are applied
const AUTO_ADJUSTED = new Set(PROPOSAL_RULES.map((r) => r.counterpart));

// Italian labels for rettifiche fields
const RETTIFICHE_LABELS: Record<string, string> = {
  // SP - Attivo
  sp01_crediti_soci: "A) Crediti verso soci",
  sp02_immob_immateriali: "B.I) Immobilizzazioni immateriali",
  sp03_immob_materiali: "B.II) Immobilizzazioni materiali",
  sp04_immob_finanziarie: "B.III) Immobilizzazioni finanziarie",
  sp05_rimanenze: "C.I) Rimanenze",
  sp05a_materie_prime: "  1) Materie prime, sussidiarie e di consumo",
  sp05b_prodotti_in_corso: "  2) Prodotti in c/lavorazione e semilavorati",
  sp05c_lavori_in_corso: "  3) Lavori in corso su ordinazione",
  sp05d_prodotti_finiti: "  4) Prodotti finiti e merci",
  sp05e_acconti: "  5) Acconti",
  sp06_crediti_breve: "C.II) Crediti (entro es. successivo)",
  sp06a_crediti_clienti_breve: "  1) Verso clienti",
  sp06b_crediti_controllate_breve: "  2) Verso imprese controllate",
  sp06c_crediti_collegate_breve: "  3) Verso imprese collegate",
  sp06d_crediti_controllanti_breve: "  4) Verso controllanti",
  sp06e_crediti_tributari_breve: "  5-bis) Crediti tributari",
  sp06f_imposte_anticipate_breve: "  5-ter) Imposte anticipate",
  sp06g_crediti_altri_breve: "  5-quater) Verso altri",
  sp07_crediti_lungo: "C.II) Crediti (oltre es. successivo)",
  sp07a_crediti_clienti_lungo: "  1) Verso clienti",
  sp07b_crediti_controllate_lungo: "  2) Verso imprese controllate",
  sp07c_crediti_collegate_lungo: "  3) Verso imprese collegate",
  sp07d_crediti_controllanti_lungo: "  4) Verso controllanti",
  sp07e_crediti_tributari_lungo: "  5-bis) Crediti tributari",
  sp07f_imposte_anticipate_lungo: "  5-ter) Imposte anticipate",
  sp07g_crediti_altri_lungo: "  5-quater) Verso altri",
  sp08_attivita_finanziarie: "C.III) Attività finanziarie",
  sp09_disponibilita_liquide: "C.IV) Disponibilità liquide",
  sp10_ratei_risconti_attivi: "D) Ratei e risconti attivi",
  // SP - Passivo
  sp11_capitale: "A.I) Capitale",
  sp12_riserve: "A.II-VIII) Riserve",
  sp12g_utili_perdite_portati: "  VIII) Utili (perdite) portati a nuovo",
  sp13_utile_perdita: "A.IX) Utile (perdita) esercizio",
  sp14_fondi_rischi: "B) Fondi per rischi e oneri",
  sp15_tfr: "C) Trattamento di fine rapporto di lavoro subordinato",
  sp18_ratei_risconti_passivi: "E) Ratei e risconti",
  // CE
  ce01_ricavi_vendite: "1) Ricavi delle vendite e delle prestazioni",
  ce02_variazioni_rimanenze: "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti",
  ce03_lavori_interni: "4) Incrementi di immobilizzazioni per lavori interni",
  ce04_altri_ricavi: "5) Altri ricavi e proventi",
  ce05_materie_prime: "6) Per materie prime, sussidiarie, di consumo e di merci",
  ce06_servizi: "7) Per servizi",
  ce07_godimento_beni: "8) Per godimento di beni di terzi",
  ce08_costi_personale: "9) Per il personale",
  ce08b_salari_stipendi: "  a) Salari e stipendi",
  ce08c_oneri_sociali: "  b) Oneri sociali",
  ce08a_tfr_accrual: "  c) Trattamento di fine rapporto",
  ce08d_altri_costi_personale: "  e) Altri costi",
  ce09_ammortamenti: "10) Ammortamenti e svalutazioni",
  ce09a_ammort_immateriali: "  a) Ammort. delle immobilizzazioni immateriali",
  ce09b_ammort_materiali: "  b) Ammort. delle immobilizzazioni materiali",
  ce09c_svalutazioni: "  c) Altre svalutazioni delle immobilizzazioni",
  ce09d_svalutazione_crediti: "  d) Svalutazioni dei crediti dell'attivo circ. e disp. liquide",
  ce10_var_rimanenze_mat_prime: "11) Var. rimanenze di materie prime, suss., di cons. e merci",
  ce11_accantonamenti: "12) Accantonamenti per rischi",
  ce11b_altri_accantonamenti: "13) Altri accantonamenti",
  ce12_oneri_diversi: "14) Oneri diversi di gestione",
  ce13_proventi_partecipazioni: "15) Proventi da partecipazioni",
  ce14_altri_proventi_finanziari: "16) Altri proventi finanziari",
  ce15_oneri_finanziari: "17) Interessi e altri oneri finanziari",
  ce16_utili_perdite_cambi: "17-bis) Utili e perdite su cambi",
  ce17a_rivalutazioni: "18) Rivalutazioni",
  ce17b_svalutazioni: "19) Svalutazioni",
  ce17_rettifiche_attivita_fin: "Totale rettifiche di valore (18 - 19)",
  ce18_proventi_straordinari: "Proventi straordinari",
  ce19_oneri_straordinari: "Oneri straordinari",
  ce20_imposte: "20) Imposte sul reddito dell'esercizio",
};

// Fields to show in the rettifiche table, organized by section
const RETTIFICHE_BS_ATTIVO = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp05_rimanenze",
  "sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti", "sp05e_acconti",
  "sp06_crediti_breve",
  "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07_crediti_lungo",
  "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
];
const RETTIFICHE_BS_PN = [
  "sp11_capitale", "sp12_riserve", "sp12g_utili_perdite_portati", "sp13_utile_perdita",
];
const RETTIFICHE_BS_OTHER_PASSIVO = [
  "sp14_fondi_rischi", "sp15_tfr",
];
// Synthetic debt groups: Banche, Fornitori, Altri (aggregated)
const DEBT_GROUPS: Array<{ label: string; entro: string[]; oltre: string[] }> = [
  {
    label: "Debiti verso banche",
    entro: ["sp16a_debiti_banche_breve"],
    oltre: ["sp17a_debiti_banche_lungo"],
  },
  {
    label: "Debiti verso fornitori",
    entro: ["sp16d_debiti_fornitori_breve"],
    oltre: ["sp17d_debiti_fornitori_lungo"],
  },
  {
    label: "Altri debiti",
    entro: ["sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
            "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve"],
    oltre: ["sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
            "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo"],
  },
];
// Main-level fields for total calculation (excludes detail sub-fields to avoid double-counting)
const PASSIVO_TOTAL_FIELDS = [
  "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
  "sp14_fondi_rischi", "sp15_tfr",
  "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
];
// Detail fields that should always show when their parent is non-zero
const DETAIL_PARENTS: Record<string, string> = {
  sp05a_materie_prime: "sp05_rimanenze",
  sp05b_prodotti_in_corso: "sp05_rimanenze",
  sp05c_lavori_in_corso: "sp05_rimanenze",
  sp05d_prodotti_finiti: "sp05_rimanenze",
  sp05e_acconti: "sp05_rimanenze",
  sp06a_crediti_clienti_breve: "sp06_crediti_breve",
  sp06b_crediti_controllate_breve: "sp06_crediti_breve",
  sp06c_crediti_collegate_breve: "sp06_crediti_breve",
  sp06d_crediti_controllanti_breve: "sp06_crediti_breve",
  sp06e_crediti_tributari_breve: "sp06_crediti_breve",
  sp06f_imposte_anticipate_breve: "sp06_crediti_breve",
  sp06g_crediti_altri_breve: "sp06_crediti_breve",
  sp07a_crediti_clienti_lungo: "sp07_crediti_lungo",
  sp07b_crediti_controllate_lungo: "sp07_crediti_lungo",
  sp07c_crediti_collegate_lungo: "sp07_crediti_lungo",
  sp07d_crediti_controllanti_lungo: "sp07_crediti_lungo",
  sp07e_crediti_tributari_lungo: "sp07_crediti_lungo",
  sp07f_imposte_anticipate_lungo: "sp07_crediti_lungo",
  sp07g_crediti_altri_lungo: "sp07_crediti_lungo",
  sp12g_utili_perdite_portati: "sp12_riserve",
  ce08b_salari_stipendi: "ce08_costi_personale",
  ce08c_oneri_sociali: "ce08_costi_personale",
  ce08a_tfr_accrual: "ce08_costi_personale",
  ce08d_altri_costi_personale: "ce08_costi_personale",
  ce09a_ammort_immateriali: "ce09_ammortamenti",
  ce09b_ammort_materiali: "ce09_ammortamenti",
  ce09c_svalutazioni: "ce09_ammortamenti",
  ce09d_svalutazione_crediti: "ce09_ammortamenti",
  ce17a_rivalutazioni: "ce17_rettifiche_attivita_fin",
  ce17b_svalutazioni: "ce17_rettifiche_attivita_fin",
};
// CE split by IV CEE section for proper subtotal placement
const CE_A = [
  "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni",
  "ce04_altri_ricavi",
];
const CE_B = [
  "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale",
  "ce09_ammortamenti",
  "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
  "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
  "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti",
  "ce12_oneri_diversi",
];
const CE_C = [
  "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
];
const CE_D = [
  "ce17a_rivalutazioni", "ce17b_svalutazioni", "ce17_rettifiche_attivita_fin",
];
const CE_E = [
  "ce18_proventi_straordinari", "ce19_oneri_straordinari",
];
const CE_IMPOSTE = ["ce20_imposte"];

// Proposal generated for the review dialog
interface DoubleEntryProposal {
  id: number;
  editedField: string;
  editedLabel: string;
  delta: number;
  counterpartField: string;
  counterpartLabel: string;
  proposedDelta: number;
  accepted: boolean;
  explanation: string;
  // Optional split: allows distributing the amount between two counterpart fields
  splitAlt?: {
    field: string;
    label: string;
    amount: number; // amount allocated to the alternative (rest goes to main counterpart)
  };
}

interface RettificheTabProps {
  adjustableData: AdjustableFinancialYear | null;
  referenceYearData: Record<string, number> | null;
  referenceYear: number;
  periodMonths: number;
  fiscalYear: number;
  corrections: Record<string, number>;
  setCorrections: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  loading: boolean;
  saving: boolean;
  adjustmentsApplied: boolean;
  onSave: (finalCorrections?: Record<string, number>) => Promise<void>;
  onReset: () => Promise<void>;
  onNext: () => void;
}

function RettificheTab({
  adjustableData,
  referenceYearData,
  referenceYear,
  periodMonths,
  fiscalYear,
  corrections,
  setCorrections,
  loading,
  saving,
  adjustmentsApplied,
  onSave,
  onReset,
  onNext,
}: RettificheTabProps) {
  // Compute end-of-period date label, e.g. "30/06/2025"
  const periodEndDate = (() => {
    const lastDay = new Date(fiscalYear, periodMonths, 0).getDate();
    const mm = String(periodMonths).padStart(2, "0");
    return `${lastDay}/${mm}/${fiscalYear}`;
  })();

  // Sticky column header bar — appears when the first table header scrolls out of view
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  // State for double-entry review dialog
  const [showProposalDialog, setShowProposalDialog] = useState(false);
  const [proposals, setProposals] = useState<DoubleEntryProposal[]>([]);
  // Track approved proposals to prevent re-proposing: Set of "editedField→counterpartField" keys
  const [approvedPairs, setApprovedPairs] = useState<Set<string>>(new Set());
  // Summary dialog shown before navigating to Confronto
  const [showSummaryDialog, setShowSummaryDialog] = useState(false);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyHeader(!entry.isIntersecting),
      { threshold: 0 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (loading || !adjustableData) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
          <p className="mt-2 text-muted-foreground">Caricamento dati...</p>
        </CardContent>
      </Card>
    );
  }

  const original = {
    ...adjustableData.original_balance_sheet,
    ...adjustableData.original_income_statement,
  } as Record<string, number>;
  // Reconcile debt sub-fields so "Altri debiti" absorbs any gap vs imported aggregate
  reconcileSubfields(original);

  // Handle field changes — only direct edit + conditional sub-field aggregates + sp13 recalc.
  // Double-entry counterparts are proposed via dialog, not auto-applied.
  // IMPORTANT: Only recalculate an aggregate when one of its component fields is edited,
  // to avoid corrupting aggregates when details don't sum to the original total.
  const SP16_DETAILS = [
    "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
    "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
    "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
    "sp16g_altri_debiti_breve",
  ];
  const SP17_DETAILS = [
    "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
    "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
    "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
    "sp17g_altri_debiti_lungo",
  ];
  const SP05_DETAILS = ["sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti"];
  const SP06_DETAILS = [
    "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve", "sp06c_crediti_collegate_breve",
    "sp06d_crediti_controllanti_breve", "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
    "sp06g_crediti_altri_breve",
  ];
  const SP07_DETAILS = [
    "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo", "sp07c_crediti_collegate_lungo",
    "sp07d_crediti_controllanti_lungo", "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
    "sp07g_crediti_altri_lungo",
  ];
  const CE08_DETAILS = ["ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale"];
  const CE09_DETAILS = ["ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti"];
  const CE17_DETAILS = ["ce17a_rivalutazioni", "ce17b_svalutazioni"];
  // All CE fields that affect the P&L result
  const CE_FIELDS = [
    "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi",
    "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni", "ce08_costi_personale",
    "ce09_ammortamenti", "ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
    "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi",
    "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
    "ce17_rettifiche_attivita_fin", "ce17a_rivalutazioni", "ce17b_svalutazioni",
    "ce18_proventi_straordinari", "ce19_oneri_straordinari", "ce20_imposte",
  ];

  const handleChange = (field: string, newValue: number) => {
    const updated = { ...corrections, [field]: newValue };
    // Clear approved pairs for this field so counterpart proposals can be regenerated
    if (approvedPairs.size > 0) {
      const newApproved = new Set<string>();
      for (const key of approvedPairs) {
        if (!key.startsWith(`${field}→`)) newApproved.add(key);
      }
      if (newApproved.size !== approvedPairs.size) setApprovedPairs(newApproved);
    }

    // Recalculate parent aggregates using delta-based approach:
    // parent = original_parent + sum(sub_field_deltas)
    // This preserves the original aggregate when sub-fields don't sum to it (common in imports).
    const applySubfieldDelta = (details: string[], parent: string) => {
      const totalDelta = details.reduce((s, k) => {
        const orig = original[k] ?? 0;
        const curr = updated[k] ?? orig;
        return s + (curr - orig);
      }, 0);
      updated[parent] = (original[parent] ?? 0) + totalDelta;
    };

    if (SP05_DETAILS.includes(field)) applySubfieldDelta(SP05_DETAILS, "sp05_rimanenze");
    if (SP06_DETAILS.includes(field)) applySubfieldDelta(SP06_DETAILS, "sp06_crediti_breve");
    if (SP07_DETAILS.includes(field)) applySubfieldDelta(SP07_DETAILS, "sp07_crediti_lungo");
    if (CE08_DETAILS.includes(field)) applySubfieldDelta(CE08_DETAILS, "ce08_costi_personale");
    if (SP16_DETAILS.includes(field)) applySubfieldDelta(SP16_DETAILS, "sp16_debiti_breve");
    if (SP17_DETAILS.includes(field)) applySubfieldDelta(SP17_DETAILS, "sp17_debiti_lungo");
    if (CE09_DETAILS.includes(field)) applySubfieldDelta(CE09_DETAILS, "ce09_ammortamenti");
    if (CE17_DETAILS.includes(field)) {
      // ce17 is special: rivalutazioni - svalutazioni
      const d17a = (updated["ce17a_rivalutazioni"] ?? original["ce17a_rivalutazioni"] ?? 0) - (original["ce17a_rivalutazioni"] ?? 0);
      const d17b = (updated["ce17b_svalutazioni"] ?? original["ce17b_svalutazioni"] ?? 0) - (original["ce17b_svalutazioni"] ?? 0);
      updated["ce17_rettifiche_attivita_fin"] = (original["ce17_rettifiche_attivita_fin"] ?? 0) + d17a - d17b;
    }

    // Only recalculate sp13 (P&L result → BS) if a CE field was edited
    if (CE_FIELDS.includes(field)) {
      const ceVal = (k: string) => updated[k] ?? original[k] ?? 0;
      const vp = ceVal("ce01_ricavi_vendite") + ceVal("ce02_variazioni_rimanenze")
        + ceVal("ce03_lavori_interni") + ceVal("ce04_altri_ricavi");
      const costs = ceVal("ce05_materie_prime") + ceVal("ce06_servizi")
        + ceVal("ce07_godimento_beni") + ceVal("ce08_costi_personale")
        + ceVal("ce09_ammortamenti") + ceVal("ce10_var_rimanenze_mat_prime")
        + ceVal("ce11_accantonamenti") + ceVal("ce11b_altri_accantonamenti")
        + ceVal("ce12_oneri_diversi");
      const ebit = vp - costs;
      const financial = ceVal("ce13_proventi_partecipazioni") + ceVal("ce14_altri_proventi_finanziari")
        - ceVal("ce15_oneri_finanziari") + ceVal("ce16_utili_perdite_cambi");
      const rettifiche = ceVal("ce17_rettifiche_attivita_fin");
      const straord = ceVal("ce18_proventi_straordinari") - ceVal("ce19_oneri_straordinari");
      const netProfit = ebit + financial + rettifiche + straord - ceVal("ce20_imposte");
      updated["sp13_utile_perdita"] = Math.round(netProfit * 100) / 100;
    }

    setCorrections(updated);
  };

  // Helper: recalculate all sub-field aggregates + sp13 on a corrections snapshot
  const recalcAggregates = (corr: Record<string, number>): Record<string, number> => {
    const u = { ...corr };
    // Delta-based: parent = original_parent + sum(sub_field_deltas)
    const applyDelta = (details: string[], parent: string) => {
      const totalDelta = details.reduce((s, k) => {
        const orig = original[k] ?? 0;
        const curr = u[k] ?? orig;
        return s + (curr - orig);
      }, 0);
      u[parent] = (original[parent] ?? 0) + totalDelta;
    };
    applyDelta(SP05_DETAILS, "sp05_rimanenze");
    applyDelta(SP06_DETAILS, "sp06_crediti_breve");
    applyDelta(SP07_DETAILS, "sp07_crediti_lungo");
    applyDelta(CE08_DETAILS, "ce08_costi_personale");
    applyDelta(SP16_DETAILS, "sp16_debiti_breve");
    applyDelta(SP17_DETAILS, "sp17_debiti_lungo");
    applyDelta(CE09_DETAILS, "ce09_ammortamenti");
    // ce17: rivalutazioni - svalutazioni
    const d17a = (u["ce17a_rivalutazioni"] ?? original["ce17a_rivalutazioni"] ?? 0) - (original["ce17a_rivalutazioni"] ?? 0);
    const d17b = (u["ce17b_svalutazioni"] ?? original["ce17b_svalutazioni"] ?? 0) - (original["ce17b_svalutazioni"] ?? 0);
    u["ce17_rettifiche_attivita_fin"] = (original["ce17_rettifiche_attivita_fin"] ?? 0) + d17a - d17b;
    // sp13 from P&L — Risultato calculated first in CE, then set in SP
    const cv = (k: string) => u[k] ?? original[k] ?? 0;
    const vp = cv("ce01_ricavi_vendite") + cv("ce02_variazioni_rimanenze")
      + cv("ce03_lavori_interni") + cv("ce04_altri_ricavi");
    const costs = cv("ce05_materie_prime") + cv("ce06_servizi") + cv("ce07_godimento_beni")
      + cv("ce08_costi_personale") + cv("ce09_ammortamenti") + cv("ce10_var_rimanenze_mat_prime")
      + cv("ce11_accantonamenti") + cv("ce11b_altri_accantonamenti") + cv("ce12_oneri_diversi");
    const ebit = vp - costs;
    const fin = cv("ce13_proventi_partecipazioni") + cv("ce14_altri_proventi_finanziari")
      - cv("ce15_oneri_finanziari") + cv("ce16_utili_perdite_cambi");
    const rett = cv("ce17_rettifiche_attivita_fin");
    const str = cv("ce18_proventi_straordinari") - cv("ce19_oneri_straordinari");
    u["sp13_utile_perdita"] = Math.round((ebit + fin + rett + str - cv("ce20_imposte")) * 100) / 100;
    return u;
  };

  // Compute double-entry proposals from user edits.
  // Only proposes the INCREMENTAL amount not yet covered by the counterpart's current delta.
  // This prevents re-proposing already-approved entries.
  const computeProposals = (): DoubleEntryProposal[] => {
    const result: DoubleEntryProposal[] = [];

    // Map parent aggregates → their subfield detail arrays.
    // When a subfield is edited, handleChange recalculates the parent via
    // applySubfieldDelta.  If both the parent rule and a subfield rule target
    // the same counterpart we must skip the parent rule to avoid double-counting.
    const PARENT_SUBFIELDS: Record<string, string[]> = {
      "sp05_rimanenze": SP05_DETAILS,
      "sp06_crediti_breve": SP06_DETAILS,
      "sp07_crediti_lungo": SP07_DETAILS,
      "ce08_costi_personale": CE08_DETAILS,
      "sp16_debiti_breve": SP16_DETAILS,
      "sp17_debiti_lungo": SP17_DETAILS,
      "ce09_ammortamenti": CE09_DETAILS,
    };
    const recalculatedParents = new Set<string>();
    for (const [parent, subfields] of Object.entries(PARENT_SUBFIELDS)) {
      if (subfields.some(sf => {
        const orig = original[sf] ?? 0;
        const corr = corrections[sf] ?? orig;
        return Math.abs(corr - orig) >= 0.01;
      })) recalculatedParents.add(parent);
    }

    for (const rule of PROPOSAL_RULES) {
      const origEditable = original[rule.editable] ?? 0;
      const corrEditable = corrections[rule.editable] ?? origEditable;
      const editDelta = corrEditable - origEditable;
      if (Math.abs(editDelta) < 0.01) continue;

      // Use alternative counterpart for negative deltas (e.g. credit decrease → loss, not revenue decrease)
      const useNeg = editDelta < 0 && rule.counterpartNeg;

      // Skip parent rule when its delta comes from subfield recalculation
      // and a subfield rule already covers the same counterpart
      if (recalculatedParents.has(rule.editable)) {
        const subs = PARENT_SUBFIELDS[rule.editable];
        const activeCP = useNeg ? rule.counterpartNeg! : rule.counterpart;
        if (subs && PROPOSAL_RULES.some(r => {
          if (!subs.includes(r.editable)) return false;
          // Check if subfield rule targets the same counterpart for its delta direction
          const sfOrig = original[r.editable] ?? 0;
          const sfCorr = corrections[r.editable] ?? sfOrig;
          const sfDelta = sfCorr - sfOrig;
          const sfNeg = sfDelta < 0 && r.counterpartNeg;
          const sfCP = sfNeg ? r.counterpartNeg! : r.counterpart;
          return sfCP === activeCP;
        })) {
          continue;
        }
      }
      const activeCounterpart = useNeg ? rule.counterpartNeg! : rule.counterpart;
      const activeDirection = useNeg ? (rule.directionNeg ?? rule.direction) : rule.direction;
      const activeExplanation = useNeg ? (rule.explanationNeg ?? rule.explanation) : rule.explanation;

      // Skip if this exact pair was already approved by the user
      if (approvedPairs.has(`${rule.editable}→${activeCounterpart}`)) continue;

      // What the counterpart delta SHOULD be based on the current edit
      const expectedCounterpartDelta = activeDirection === "same" ? editDelta : -editDelta;
      // What the counterpart delta ALREADY is (from prior approvals or manual edits)
      const origCounterpart = original[activeCounterpart] ?? 0;
      const corrCounterpart = corrections[activeCounterpart] ?? origCounterpart;
      const currentCounterpartDelta = corrCounterpart - origCounterpart;

      // Determine the active splitAlt (primary or negative variant)
      const activeSplitAlt = useNeg ? rule.splitAltNeg : rule.splitAlt;

      // Only propose the remaining amount not yet applied
      // For split rules, also account for the alt field's delta
      let alreadyApplied = currentCounterpartDelta;
      if (activeSplitAlt) {
        const origAlt = original[activeSplitAlt.field] ?? 0;
        const corrAlt = corrections[activeSplitAlt.field] ?? origAlt;
        alreadyApplied += (corrAlt - origAlt);
      }

      // How much is still needed? (accounting for direction)
      const remaining = expectedCounterpartDelta - alreadyApplied;
      if (Math.abs(remaining) < 0.01) continue; // fully covered already

      result.push({
        id: result.length,
        editedField: rule.editable,
        editedLabel: RETTIFICHE_LABELS[rule.editable] ?? rule.editable,
        delta: editDelta,
        counterpartField: activeCounterpart,
        counterpartLabel: RETTIFICHE_LABELS[activeCounterpart] ?? activeCounterpart,
        proposedDelta: remaining,
        accepted: true,
        explanation: activeExplanation,
        splitAlt: activeSplitAlt ? {
          field: activeSplitAlt.field,
          label: activeSplitAlt.label,
          amount: 0,
        } : undefined,
      });
    }
    return result;
  };

  // Called when user clicks "Applica Rettifiche"
  const handleApplyClick = () => {
    const computed = computeProposals();
    setProposals(computed);
    setShowProposalDialog(true);
  };

  // Called when user confirms proposals in dialog
  const applyProposalsAndSave = () => {
    const updated = { ...corrections };
    // Track which pairs were approved in this batch
    const newApproved = new Set(approvedPairs);
    // Apply accepted proposals as counterpart changes
    // Group by counterpart to accumulate multiple proposals targeting the same field
    const counterpartDeltas: Record<string, number> = {};
    for (const p of proposals) {
      if (!p.accepted) continue;
      // Record this pair as approved so it won't be re-proposed
      newApproved.add(`${p.editedField}→${p.counterpartField}`);
      if (p.splitAlt && Math.abs(p.splitAlt.amount) > 0.01) {
        newApproved.add(`${p.editedField}→${p.splitAlt.field}`);
      }
      // If split: main counterpart gets (proposedDelta - splitAlt.amount), alt gets splitAlt.amount
      if (p.splitAlt && Math.abs(p.splitAlt.amount) > 0.01) {
        const mainAmount = p.proposedDelta - p.splitAlt.amount;
        counterpartDeltas[p.counterpartField] = (counterpartDeltas[p.counterpartField] ?? 0) + mainAmount;
        counterpartDeltas[p.splitAlt.field] = (counterpartDeltas[p.splitAlt.field] ?? 0) + p.splitAlt.amount;
      } else {
        counterpartDeltas[p.counterpartField] = (counterpartDeltas[p.counterpartField] ?? 0) + p.proposedDelta;
      }
    }
    setApprovedPairs(newApproved);
    for (const [field, totalDelta] of Object.entries(counterpartDeltas)) {
      // Preserve any prior corrections — add new delta on top of existing value
      const currentVal = updated[field] ?? original[field] ?? 0;
      updated[field] = currentVal + totalDelta;
    }
    // Recalculate all aggregates and sp13
    const final = recalcAggregates(updated);
    setCorrections(final);
    setShowProposalDialog(false);
    // Pass final corrections directly (React state is async)
    onSave(final);
  };

  // Save without applying any counterpart proposals
  const saveWithoutProposals = () => {
    setShowProposalDialog(false);
    onSave();
  };

  // Compute totals
  const val = (k: string) => corrections[k] ?? original[k] ?? 0;
  const refVal = (k: string) => referenceYearData?.[k] ?? 0;
  const hasRef = !!referenceYearData;
  // Main-level attivo fields only (no detail sub-fields to avoid double-counting)
  const ATTIVO_TOTAL_FIELDS = [
    "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
    "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
    "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
    "sp10_ratei_risconti_attivi",
  ];
  const totalAttivo = ATTIVO_TOTAL_FIELDS.reduce((s, k) => s + val(k), 0);
  const pnFields = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita"];
  const totalPN = pnFields.reduce((s, k) => s + val(k), 0);
  const totalPassivo = totalPN + val("sp14_fondi_rischi") + val("sp15_tfr")
    + val("sp16_debiti_breve") + val("sp17_debiti_lungo") + val("sp18_ratei_risconti_passivi");
  const balanceDiff = Math.abs(totalAttivo - totalPassivo);
  const isBalanced = balanceDiff < 1;

  const colCount = hasRef ? 5 : 4;

  const renderSection = (title: string, fields: string[], isCE: boolean = false) => (
    <>
      {title && (
        <TableRow className="bg-muted/50">
          <TableCell colSpan={colCount} className="font-semibold text-sm py-1.5">
            {title}
          </TableCell>
        </TableRow>
      )}
      {fields.map((field) => {
        const origVal = original[field] ?? 0;
        const corrVal = val(field);
        const delta = corrVal - origVal;
        const isEditable = EDITABLE_RETTIFICHE.has(field);
        const isAutoAdj = AUTO_ADJUSTED.has(field);
        const isComputed = field === "sp13_utile_perdita" || field === "sp16_debiti_breve" || field === "sp17_debiti_lungo" || field === "ce09_ammortamenti" || field === "ce17_rettifiche_attivita_fin";
        const hasDelta = Math.abs(delta) > 0.01;
        const isDetail = (RETTIFICHE_LABELS[field] ?? "").startsWith("  ");

        // Show detail rows if parent is non-zero; otherwise skip zero rows unless editable/auto/computed
        const parentField = DETAIL_PARENTS[field];
        const parentNonZero = parentField ? Math.abs(val(parentField)) > 0.01 || Math.abs(original[parentField] ?? 0) > 0.01 : false;
        if (Math.abs(origVal) < 0.01 && Math.abs(corrVal) < 0.01 && !isEditable && !isAutoAdj && !isComputed && !parentNonZero) {
          return null;
        }

        return (
          <TableRow key={field} className={cn(
            hasDelta && "bg-yellow-50/50 dark:bg-yellow-950/10",
            isDetail && "text-muted-foreground"
          )}>
            <TableCell className={cn("text-xs py-1", isDetail ? "pl-6" : "font-medium")}>
              {RETTIFICHE_LABELS[field] ?? field}
            </TableCell>
            {hasRef && (
              <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground/50">
                {formatEuro(refVal(field))}
              </TableCell>
            )}
            <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground">
              {formatEuro(origVal)}
            </TableCell>
            <TableCell className={cn(
              "text-right text-xs py-1 font-mono tabular-nums",
              hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
            )}>
              {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
            </TableCell>
            <TableCell className="text-right py-1">
              {isEditable ? (
                <Input
                  className="h-7 w-32 ml-auto text-right text-xs font-mono tabular-nums"
                  value={formatInputNumber(Math.round(corrVal).toString())}
                  onChange={(e) => {
                    const raw = parseInputNumber(e.target.value);
                    const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                    if (!isNaN(num)) handleChange(field, num);
                  }}
                />
              ) : (
                <span className={cn(
                  "text-xs font-mono tabular-nums",
                  isComputed && hasDelta ? "font-semibold" : "",
                  isAutoAdj && hasDelta ? "text-blue-600 dark:text-blue-400" : ""
                )}>
                  {formatEuro(corrVal)}
                </span>
              )}
            </TableCell>
          </TableRow>
        );
      })}
    </>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Rettifiche di Bilancio</CardTitle>
          <CardDescription>
            Modifica le voci editabili per applicare rettifiche contabili. Le contropartite si aggiornano automaticamente in partita doppia.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Balance check */}
          <div className={cn(
            "mb-4 p-3 rounded-lg border text-sm flex items-center justify-between",
            isBalanced
              ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300"
              : "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800 text-red-800 dark:text-red-300"
          )}>
            <div>
              <span className="font-medium">Verifica quadratura: </span>
              Totale Attivo {formatEuro(totalAttivo)} | Totale Passivo {formatEuro(totalPassivo)}
              {!isBalanced && <span className="ml-2">(diff: {formatEuro(balanceDiff)})</span>}
            </div>
            {isBalanced ? (
              <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
            ) : (
              <span className="text-xs font-medium">SBILANCIATO</span>
            )}
          </div>

          {/* Sentinel: when this scrolls out of view, show the sticky header */}
          <div ref={sentinelRef} />

          {/* Sticky column header bar */}
          {showStickyHeader && (
            <div className="fixed top-0 left-0 right-0 z-50 bg-background/95 backdrop-blur-sm border-b shadow-sm">
              <div className="max-w-screen-xl mx-auto px-4">
                <div className="flex items-center h-9 text-xs font-medium text-muted-foreground">
                  <span className="flex-1">Voce</span>
                  {hasRef && <span className="w-28 text-right">{referenceYear}</span>}
                  <span className="w-28 text-right">{periodEndDate}</span>
                  <span className="w-28 text-right">Rettifica</span>
                  <span className="w-32 text-right">{periodEndDate} Rett.</span>
                </div>
              </div>
            </div>
          )}

          <div className="border rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Voce</TableHead>
                  {hasRef && <TableHead className="text-xs text-right">{referenceYear}</TableHead>}
                  <TableHead className="text-xs text-right">{periodEndDate}</TableHead>
                  <TableHead className="text-xs text-right">Rettifica</TableHead>
                  <TableHead className="text-xs text-right">{periodEndDate} Rett.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {renderSection("STATO PATRIMONIALE — ATTIVO", RETTIFICHE_BS_ATTIVO)}
                <TableRow className="bg-muted font-semibold">
                  <TableCell className="text-xs py-1.5">TOTALE ATTIVO</TableCell>
                  {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                    {formatEuro(ATTIVO_TOTAL_FIELDS.reduce((s, k) => s + refVal(k), 0))}
                  </TableCell>}
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums">
                    {formatEuro(ATTIVO_TOTAL_FIELDS.reduce((s, k) => s + (original[k] ?? 0), 0))}
                  </TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-semibold">
                    {formatEuro(totalAttivo)}
                  </TableCell>
                </TableRow>

                {/* PASSIVO — A) Patrimonio Netto */}
                {renderSection("STATO PATRIMONIALE — PASSIVO E NETTO", RETTIFICHE_BS_PN)}
                {renderSection("", RETTIFICHE_BS_OTHER_PASSIVO)}

                {/* D) Debiti — grouped by type with entro/oltre */}
                <TableRow className="bg-muted/50">
                  <TableCell colSpan={colCount} className="font-semibold text-sm py-1.5">
                    D) Debiti
                  </TableCell>
                </TableRow>
                {DEBT_GROUPS.map((group) => {
                  const sumFields = (fields: string[], src: Record<string, number>) =>
                    fields.reduce((s, k) => s + (src[k] ?? 0), 0);
                  const origEntro = sumFields(group.entro, original);
                  const origOltre = sumFields(group.oltre, original);
                  const corrEntro = group.entro.reduce((s, k) => s + val(k), 0);
                  const corrOltre = group.oltre.reduce((s, k) => s + val(k), 0);
                  const origTotal = origEntro + origOltre;
                  const corrTotal = corrEntro + corrOltre;
                  if (Math.abs(origTotal) < 0.01 && Math.abs(corrTotal) < 0.01) return null;

                  const refEntro = hasRef ? group.entro.reduce((s, k) => s + refVal(k), 0) : 0;
                  const refOltre = hasRef ? group.oltre.reduce((s, k) => s + refVal(k), 0) : 0;
                  const isSingleEntro = group.entro.length === 1;
                  const isSingleOltre = group.oltre.length === 1;

                  const debtRow = (label: string, key: string, rv: number, origV: number, corrV: number, indent: boolean, editField?: string) => {
                    const delta = corrV - origV;
                    const hasDelta = Math.abs(delta) > 0.01;
                    return (
                      <TableRow key={key} className={cn(hasDelta && "bg-yellow-50/50 dark:bg-yellow-950/10")}>
                        <TableCell className={cn("text-xs py-1", indent ? "pl-8 text-muted-foreground" : "pl-4 font-medium")}>
                          {label}
                        </TableCell>
                        {hasRef && <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground/50">
                          {formatEuro(rv)}
                        </TableCell>}
                        <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground">
                          {formatEuro(origV)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1 font-mono tabular-nums",
                          hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
                        )}>
                          {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
                        </TableCell>
                        <TableCell className="text-right py-1">
                          {editField ? (
                            <Input
                              className="h-7 w-32 ml-auto text-right text-xs font-mono tabular-nums"
                              value={formatInputNumber(Math.round(corrV).toString())}
                              onChange={(e) => {
                                const raw = parseInputNumber(e.target.value);
                                const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                                if (!isNaN(num)) handleChange(editField, num);
                              }}
                            />
                          ) : (
                            <span className={cn("text-xs font-mono tabular-nums", !indent && "font-medium",
                              hasDelta && indent ? "text-blue-600 dark:text-blue-400" : ""
                            )}>
                              {formatEuro(corrV)}
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  };

                  return (
                    <React.Fragment key={group.label}>
                      {debtRow(group.label, group.label, refEntro + refOltre, origTotal, corrTotal, false)}
                      {debtRow("entro 12 mesi", group.label + "_entro", refEntro, origEntro, corrEntro, true,
                        isSingleEntro ? group.entro[0] : undefined)}
                      {debtRow("oltre 12 mesi", group.label + "_oltre", refOltre, origOltre, corrOltre, true,
                        isSingleOltre ? group.oltre[0] : undefined)}
                    </React.Fragment>
                  );
                })}
                {/* Totale debiti */}
                {(() => {
                  const origDebtTotal = (original["sp16_debiti_breve"] ?? 0) + (original["sp17_debiti_lungo"] ?? 0);
                  const corrDebtTotal = val("sp16_debiti_breve") + val("sp17_debiti_lungo");
                  return (
                    <TableRow className="font-medium">
                      <TableCell className="text-xs py-1.5 pl-4">Totale debiti</TableCell>
                      {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                        {formatEuro(refVal("sp16_debiti_breve") + refVal("sp17_debiti_lungo"))}
                      </TableCell>}
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground">
                        {formatEuro(origDebtTotal)}
                      </TableCell>
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-medium">
                        {formatEuro(corrDebtTotal)}
                      </TableCell>
                    </TableRow>
                  );
                })()}

                {/* E) Ratei e risconti passivi */}
                {renderSection("", ["sp18_ratei_risconti_passivi"])}

                <TableRow className="bg-muted font-semibold">
                  <TableCell className="text-xs py-1.5">TOTALE PASSIVO</TableCell>
                  {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                    {formatEuro(PASSIVO_TOTAL_FIELDS.reduce((s, k) => s + refVal(k), 0))}
                  </TableCell>}
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums">
                    {formatEuro(PASSIVO_TOTAL_FIELDS.reduce((s, k) => s + (original[k] ?? 0), 0))}
                  </TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-semibold">
                    {formatEuro(totalPassivo)}
                  </TableCell>
                </TableRow>

              </TableBody>
            </Table>
          </div>

          <div className="border rounded-lg overflow-hidden mt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Voce</TableHead>
                  {hasRef && <TableHead className="text-xs text-right">{referenceYear}</TableHead>}
                  <TableHead className="text-xs text-right">{periodEndDate}</TableHead>
                  <TableHead className="text-xs text-right">Rettifica</TableHead>
                  <TableHead className="text-xs text-right">{periodEndDate} Rett.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* CE sectioned with subtotals */}
                {(() => {
                  const ceV = (k: string) => corrections[k] ?? original[k] ?? 0;
                  const origV = (k: string) => original[k] ?? 0;

                  const resultRow = (label: string, refValue: number, origVal: number, corrVal: number, bold = false) => {
                    const delta = corrVal - origVal;
                    const hasDelta = Math.abs(delta) > 0.01;
                    return (
                      <TableRow key={label} className={cn(bold && "bg-muted font-semibold")}>
                        <TableCell className={cn("text-xs py-1.5", bold && "font-semibold")}>{label}</TableCell>
                        {hasRef && (
                          <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                            {formatEuro(refValue)}
                          </TableCell>
                        )}
                        <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground">
                          {formatEuro(origVal)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1.5 font-mono tabular-nums",
                          hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
                        )}>
                          {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
                        </TableCell>
                        <TableCell className={cn("text-right text-xs py-1.5 font-mono tabular-nums", bold && "font-semibold")}>
                          {formatEuro(corrVal)}
                        </TableCell>
                      </TableRow>
                    );
                  };

                  // Compute subtotals
                  const sumF = (keys: string[], fn: (k: string) => number) => keys.reduce((s, k) => s + fn(k), 0);
                  const vp = sumF(CE_A, ceV);
                  const origVp = sumF(CE_A, origV);
                  const refVp = sumF(CE_A, refVal);
                  const costMainKeys = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
                    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
                    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
                  const costs = sumF(costMainKeys, ceV);
                  const origCosts = sumF(costMainKeys, origV);
                  const refCosts = sumF(costMainKeys, refVal);
                  const ebit = vp - costs;
                  const origEbit = origVp - origCosts;
                  const refEbit = refVp - refCosts;
                  const fin = ceV("ce13_proventi_partecipazioni") + ceV("ce14_altri_proventi_finanziari")
                    - ceV("ce15_oneri_finanziari") + ceV("ce16_utili_perdite_cambi");
                  const origFin = origV("ce13_proventi_partecipazioni") + origV("ce14_altri_proventi_finanziari")
                    - origV("ce15_oneri_finanziari") + origV("ce16_utili_perdite_cambi");
                  const refFinVal = refVal("ce13_proventi_partecipazioni") + refVal("ce14_altri_proventi_finanziari")
                    - refVal("ce15_oneri_finanziari") + refVal("ce16_utili_perdite_cambi");
                  const rett = ceV("ce17_rettifiche_attivita_fin");
                  const origRett = origV("ce17_rettifiche_attivita_fin");
                  const refRett = refVal("ce17_rettifiche_attivita_fin");
                  const straord = ceV("ce18_proventi_straordinari") - ceV("ce19_oneri_straordinari");
                  const origStraord = origV("ce18_proventi_straordinari") - origV("ce19_oneri_straordinari");
                  const refStraord = refVal("ce18_proventi_straordinari") - refVal("ce19_oneri_straordinari");
                  const pbt = ebit + fin + rett + straord;
                  const origPbt = origEbit + origFin + origRett + origStraord;
                  const refPbt = refEbit + refFinVal + refRett + refStraord;
                  const netProfit = pbt - ceV("ce20_imposte");
                  const origNetProfit = origPbt - origV("ce20_imposte");
                  const refNetProfit = refPbt - refVal("ce20_imposte");
                  const sp13 = val("sp13_utile_perdita");
                  const ceSpMatch = Math.abs(netProfit - sp13) < 1;

                  return (
                    <>
                      {renderSection("A) VALORE DELLA PRODUZIONE", CE_A, true)}
                      {resultRow("Totale valore della produzione", refVp, origVp, vp, false)}
                      {renderSection("B) COSTI DELLA PRODUZIONE", CE_B, true)}
                      {resultRow("Totale costi della produzione", refCosts, origCosts, costs, false)}
                      {resultRow("Differenza tra valore e costi della produzione (A - B)", refEbit, origEbit, ebit, true)}
                      {renderSection("C) PROVENTI E ONERI FINANZIARI", CE_C, true)}
                      {resultRow("Totale proventi e oneri finanziari (15 + 16 - 17 +/- 17-bis)", refFinVal, origFin, fin, false)}
                      {renderSection("D) RETTIFICHE DI VALORE DI ATTIVITÀ E PASSIVITÀ FINANZIARIE", CE_D, true)}
                      {renderSection("E) PROVENTI E ONERI STRAORDINARI", CE_E, true)}
                      {resultRow("Risultato prima delle imposte (A - B +/- C +/- D +/- E)", refPbt, origPbt, pbt, true)}
                      {renderSection("", CE_IMPOSTE, true)}
                      {resultRow("21) Utile (perdita) dell'esercizio", refNetProfit, origNetProfit, netProfit, true)}
                      <TableRow className={cn(
                        "border-t-2",
                        ceSpMatch
                          ? "bg-green-50/50 dark:bg-green-950/10"
                          : "bg-red-50/50 dark:bg-red-950/10"
                      )}>
                        <TableCell colSpan={hasRef ? 4 : 3} className="text-xs py-1.5 font-medium">
                          Verifica CE ↔ SP: Utile CE = {formatEuro(netProfit)} | SP13 = {formatEuro(sp13)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1.5 font-mono font-semibold",
                          ceSpMatch ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                        )}>
                          {ceSpMatch ? "OK" : `diff: ${formatEuro(Math.abs(netProfit - sp13))}`}
                        </TableCell>
                      </TableRow>
                    </>
                  );
                })()}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          {adjustmentsApplied && (
            <Button variant="outline" size="sm" onClick={onReset} disabled={saving}>
              <RotateCcw className="h-4 w-4 mr-1.5" />
              Ripristina originale
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleApplyClick}
            disabled={saving}
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Salvataggio...
              </>
            ) : (
              <>
                <Check className="h-4 w-4 mr-2" />
                Applica Rettifiche
              </>
            )}
          </Button>
          <Button variant="outline" onClick={() => setShowSummaryDialog(true)}>
            Passa al Confronto <ArrowRight className="h-4 w-4 ml-1.5" />
          </Button>
        </div>
      </div>

      {/* Double-entry review dialog */}
      <Dialog open={showProposalDialog} onOpenChange={setShowProposalDialog}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Registrazioni in Partita Doppia</DialogTitle>
            <DialogDescription>
              Le rettifiche inserite generano le seguenti contropartite contabili.
              Verifica gli importi proposti, modifica se necessario, o deseleziona le voci da non applicare.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 my-2">
            {proposals.length === 0 && (
              <div className="p-4 text-center text-sm text-muted-foreground border rounded-lg border-dashed">
                Nessuna contropartita automatica proposta per le modifiche effettuate.
              </div>
            )}
            {proposals.map((p, idx) => {
              const dirLabel = p.delta > 0 ? "+" : "";
              const cpDirLabel = p.proposedDelta > 0 ? "+" : "";
              return (
                <div
                  key={p.id}
                  className={cn(
                    "border rounded-lg p-3 transition-colors",
                    p.accepted
                      ? "bg-card border-border"
                      : "bg-muted/30 border-dashed opacity-60"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <Checkbox
                      checked={p.accepted}
                      onCheckedChange={(checked) => {
                        setProposals(prev => prev.map((pp, i) =>
                          i === idx ? { ...pp, accepted: !!checked } : pp
                        ));
                      }}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      {/* Edited field */}
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="text-sm font-medium">{p.editedLabel}</span>
                        <span className={cn(
                          "text-sm font-mono tabular-nums font-semibold",
                          p.delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                        )}>
                          {dirLabel}{formatEuro(p.delta)}
                        </span>
                      </div>

                      {/* Arrow + counterpart (with optional split) */}
                      {p.splitAlt ? (
                        <>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <span className="text-sm text-muted-foreground">{p.counterpartLabel}</span>
                            <Input
                              className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                              value={formatInputNumber(Math.round(p.proposedDelta - (p.splitAlt.amount ?? 0)).toString())}
                              disabled={!p.accepted}
                              onChange={(e) => {
                                const raw = parseInputNumber(e.target.value);
                                const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                                if (!isNaN(num)) {
                                  setProposals(prev => prev.map((pp, i) =>
                                    i === idx ? { ...pp, splitAlt: { ...pp.splitAlt!, amount: pp.proposedDelta - num } } : pp
                                  ));
                                }
                              }}
                            />
                          </div>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <span className="text-sm text-muted-foreground">{p.splitAlt.label}</span>
                            <Input
                              className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                              value={formatInputNumber(Math.round(p.splitAlt.amount).toString())}
                              disabled={!p.accepted}
                              onChange={(e) => {
                                const raw = parseInputNumber(e.target.value);
                                const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                                if (!isNaN(num)) {
                                  setProposals(prev => prev.map((pp, i) =>
                                    i === idx ? { ...pp, splitAlt: { ...pp.splitAlt!, amount: num } } : pp
                                  ));
                                }
                              }}
                            />
                          </div>
                          <p className="text-xs text-muted-foreground/60 mt-0.5 ml-6">
                            Totale: {formatEuro(p.proposedDelta)}
                          </p>
                        </>
                      ) : (
                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          <span className="text-sm text-muted-foreground">{p.counterpartLabel}</span>
                          <Input
                            className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                            value={formatInputNumber(Math.round(p.proposedDelta).toString())}
                            disabled={!p.accepted}
                            onChange={(e) => {
                              const raw = parseInputNumber(e.target.value);
                              const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                              if (!isNaN(num)) {
                                setProposals(prev => prev.map((pp, i) =>
                                  i === idx ? { ...pp, proposedDelta: num } : pp
                                ));
                              }
                            }}
                          />
                        </div>
                      )}

                      {/* Explanation */}
                      <p className="text-xs text-muted-foreground mt-1 italic">
                        {p.explanation}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Preview: P&L result after proposals */}
          {(() => {
            const preview = { ...corrections };
            const counterpartDeltas: Record<string, number> = {};
            for (const p of proposals) {
              if (!p.accepted) continue;
              if (p.splitAlt && Math.abs(p.splitAlt.amount) > 0.01) {
                counterpartDeltas[p.counterpartField] = (counterpartDeltas[p.counterpartField] ?? 0) + (p.proposedDelta - p.splitAlt.amount);
                counterpartDeltas[p.splitAlt.field] = (counterpartDeltas[p.splitAlt.field] ?? 0) + p.splitAlt.amount;
              } else {
                counterpartDeltas[p.counterpartField] = (counterpartDeltas[p.counterpartField] ?? 0) + p.proposedDelta;
              }
            }
            for (const [field, totalDelta] of Object.entries(counterpartDeltas)) {
              preview[field] = (original[field] ?? 0) + totalDelta;
            }
            const final = recalcAggregates(preview);
            const origNetProfit = (() => {
              const ov = (k: string) => original[k] ?? 0;
              const vp = ov("ce01_ricavi_vendite") + ov("ce02_variazioni_rimanenze") + ov("ce03_lavori_interni") + ov("ce04_altri_ricavi");
              const c = ov("ce05_materie_prime") + ov("ce06_servizi") + ov("ce07_godimento_beni") + ov("ce08_costi_personale")
                + ov("ce09_ammortamenti") + ov("ce10_var_rimanenze_mat_prime") + ov("ce11_accantonamenti") + ov("ce11b_altri_accantonamenti") + ov("ce12_oneri_diversi");
              const f = ov("ce13_proventi_partecipazioni") + ov("ce14_altri_proventi_finanziari") - ov("ce15_oneri_finanziari") + ov("ce16_utili_perdite_cambi");
              const r = ov("ce17_rettifiche_attivita_fin");
              const s = ov("ce18_proventi_straordinari") - ov("ce19_oneri_straordinari");
              return (vp - c) + f + r + s - ov("ce20_imposte");
            })();
            const newNetProfit = final["sp13_utile_perdita"];
            const ATTIVO_F = ["sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
              "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
              "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi"];
            const PASSIVO_F = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
              "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi"];
            const fv = (k: string) => final[k] ?? original[k] ?? 0;
            const tA = ATTIVO_F.reduce((s, k) => s + fv(k), 0);
            const tP = PASSIVO_F.reduce((s, k) => s + fv(k), 0);
            const balanced = Math.abs(tA - tP) < 1;

            return (
              <div className={cn(
                "p-3 rounded-lg border text-sm",
                balanced
                  ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                  : "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800"
              )}>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">Risultato d&apos;esercizio: </span>
                    <span className="font-mono tabular-nums">{formatEuro(origNetProfit)}</span>
                    <ArrowRight className="inline h-3.5 w-3.5 mx-1.5 text-muted-foreground" />
                    <span className="font-mono tabular-nums font-semibold">{formatEuro(newNetProfit)}</span>
                  </div>
                  <div className="text-xs">
                    {balanced ? (
                      <span className="text-green-600 dark:text-green-400 font-medium flex items-center gap-1">
                        <Check className="h-3.5 w-3.5" /> Quadrato
                      </span>
                    ) : (
                      <span className="text-yellow-600 dark:text-yellow-400 font-medium">
                        Attivo {formatEuro(tA)} / Passivo {formatEuro(tP)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })()}

          <DialogFooter className="gap-2 sm:gap-0">
            {proposals.length > 0 ? (
              <>
                <Button variant="ghost" size="sm" onClick={saveWithoutProposals}>
                  Salva senza contropartite
                </Button>
                <Button variant="outline" onClick={() => setShowProposalDialog(false)}>
                  Annulla
                </Button>
                <Button onClick={applyProposalsAndSave}>
                  <Check className="h-4 w-4 mr-1.5" />
                  Conferma e Applica
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setShowProposalDialog(false)}>
                  Annulla
                </Button>
                <Button onClick={saveWithoutProposals}>
                  <Check className="h-4 w-4 mr-1.5" />
                  Salva Rettifiche
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Summary dialog — shown before navigating to Confronto */}
      <Dialog open={showSummaryDialog} onOpenChange={setShowSummaryDialog}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Riepilogo Rettifiche</DialogTitle>
            <DialogDescription>
              Verifica tutte le modifiche apportate al bilancio originale prima di procedere al confronto.
            </DialogDescription>
          </DialogHeader>

          {(() => {
            // Collect all fields with deltas, grouped by section
            type ChangedField = { field: string; label: string; origVal: number; newVal: number; delta: number };
            const bsAttivoChanges: ChangedField[] = [];
            const bsPassivoChanges: ChangedField[] = [];
            const ceChanges: ChangedField[] = [];

            const BS_ATTIVO_FIELDS = [
              "sp01_crediti_soci",
              "sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie",
              "sp05_rimanenze", "sp05a_materie_prime", "sp05b_prodotti_in_corso",
              "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti",
              "sp06_crediti_breve", "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
              "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
              "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve", "sp06g_crediti_altri_breve",
              "sp07_crediti_lungo", "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
              "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
              "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo", "sp07g_crediti_altri_lungo",
              "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi",
            ];
            const BS_PASSIVO_FIELDS = [
              "sp11_capitale", "sp12_riserve", "sp12g_utili_perdite_portati",
              "sp13_utile_perdita", "sp14_fondi_rischi", "sp15_tfr",
              "sp16_debiti_breve", "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
              "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
              "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve",
              "sp17_debiti_lungo", "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
              "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
              "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo",
              "sp18_ratei_risconti_passivi",
            ];
            const CE_SUMMARY_FIELDS = [
              "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi",
              "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
              "ce08_costi_personale", "ce08b_salari_stipendi", "ce08c_oneri_sociali",
              "ce08a_tfr_accrual", "ce08d_altri_costi_personale",
              "ce09_ammortamenti", "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
              "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
              "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti",
              "ce12_oneri_diversi",
              "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
              "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
              "ce17_rettifiche_attivita_fin", "ce17a_rivalutazioni", "ce17b_svalutazioni",
              "ce18_proventi_straordinari", "ce19_oneri_straordinari", "ce20_imposte",
            ];

            const collectChanges = (fields: string[], target: ChangedField[]) => {
              for (const f of fields) {
                const origV = original[f] ?? 0;
                const corrV = corrections[f] ?? origV;
                const d = corrV - origV;
                if (Math.abs(d) >= 0.5) {
                  target.push({
                    field: f,
                    label: RETTIFICHE_LABELS[f] ?? f,
                    origVal: origV,
                    newVal: corrV,
                    delta: d,
                  });
                }
              }
            };
            collectChanges(BS_ATTIVO_FIELDS, bsAttivoChanges);
            collectChanges(BS_PASSIVO_FIELDS, bsPassivoChanges);
            collectChanges(CE_SUMMARY_FIELDS, ceChanges);

            const totalChanges = bsAttivoChanges.length + bsPassivoChanges.length + ceChanges.length;

            // Balance check
            const ATTIVO_AGG = ["sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
              "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
              "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi"];
            const PASSIVO_AGG = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
              "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi"];
            const fv = (k: string) => corrections[k] ?? original[k] ?? 0;
            const tA = ATTIVO_AGG.reduce((s, k) => s + fv(k), 0);
            const tP = PASSIVO_AGG.reduce((s, k) => s + fv(k), 0);
            const balanced = Math.abs(tA - tP) < 1;

            const renderSection = (title: string, changes: ChangedField[]) => {
              if (changes.length === 0) return null;
              return (
                <div key={title}>
                  <h4 className="text-sm font-semibold mb-2 text-muted-foreground">{title}</h4>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-muted/50 text-xs text-muted-foreground">
                          <th className="text-left px-3 py-1.5 font-medium">Voce</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Originale</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Rettificato</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Variazione</th>
                        </tr>
                      </thead>
                      <tbody>
                        {changes.map((c) => (
                          <tr key={c.field} className="border-t border-border/50">
                            <td className="px-3 py-1.5">{c.label}</td>
                            <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                              {formatEuro(c.origVal)}
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono tabular-nums font-medium">
                              {formatEuro(c.newVal)}
                            </td>
                            <td className={cn(
                              "px-3 py-1.5 text-right font-mono tabular-nums font-semibold",
                              c.delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                            )}>
                              {c.delta > 0 ? "+" : ""}{formatEuro(c.delta)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            };

            return (
              <div className="space-y-4 my-2">
                {totalChanges === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground border rounded-lg border-dashed">
                    Nessuna rettifica applicata. Il bilancio originale verr&agrave; utilizzato per il confronto.
                  </div>
                ) : (
                  <>
                    {renderSection("Stato Patrimoniale — Attivo", bsAttivoChanges)}
                    {renderSection("Stato Patrimoniale — Passivo e Netto", bsPassivoChanges)}
                    {renderSection("Conto Economico", ceChanges)}
                  </>
                )}

                {/* Balance check */}
                <div className={cn(
                  "p-3 rounded-lg border text-sm",
                  balanced
                    ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                    : "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800"
                )}>
                  <div className="flex items-center justify-between">
                    <div className="space-x-4">
                      <span className="text-muted-foreground">Totale Attivo:</span>
                      <span className="font-mono tabular-nums font-medium">{formatEuro(tA)}</span>
                      <span className="text-muted-foreground ml-4">Totale Passivo:</span>
                      <span className="font-mono tabular-nums font-medium">{formatEuro(tP)}</span>
                    </div>
                    {balanced ? (
                      <span className="text-green-600 dark:text-green-400 font-medium flex items-center gap-1 text-xs">
                        <Check className="h-3.5 w-3.5" /> Quadrato
                      </span>
                    ) : (
                      <span className="text-yellow-600 dark:text-yellow-400 font-medium text-xs">
                        Sbilancio: {formatEuro(tA - tP)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })()}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setShowSummaryDialog(false)}>
              Torna alle Rettifiche
            </Button>
            <Button onClick={() => { setShowSummaryDialog(false); onNext(); }}>
              <Check className="h-4 w-4 mr-1.5" />
              Conferma e Prosegui
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Reconcile sub-fields with imported aggregates.
// When imported aggregates don't match the sum of detail sub-fields,
// allocate the gap to the designated plug field.
function reconcileSubfields(data: Record<string, number>) {
  const reconcile = (details: string[], parent: string, plug: string) => {
    const total = data[parent] ?? 0;
    const sum = details.reduce((s, k) => s + (data[k] ?? 0), 0);
    const gap = total - sum;
    if (Math.abs(gap) > 0.01) {
      data[plug] = (data[plug] ?? 0) + gap;
    }
  };

  // Rimanenze: gap → sp05e_acconti
  reconcile(
    ["sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti"],
    "sp05_rimanenze", "sp05e_acconti"
  );
  // Crediti breve: gap → sp06g_crediti_altri_breve
  reconcile(
    ["sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve", "sp06c_crediti_collegate_breve",
     "sp06d_crediti_controllanti_breve", "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve", "sp06g_crediti_altri_breve"],
    "sp06_crediti_breve", "sp06g_crediti_altri_breve"
  );
  // Crediti lungo: gap → sp07g_crediti_altri_lungo
  reconcile(
    ["sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo", "sp07c_crediti_collegate_lungo",
     "sp07d_crediti_controllanti_lungo", "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo", "sp07g_crediti_altri_lungo"],
    "sp07_crediti_lungo", "sp07g_crediti_altri_lungo"
  );
  // Personale: gap → ce08b_salari_stipendi (main account)
  reconcile(
    ["ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale"],
    "ce08_costi_personale", "ce08b_salari_stipendi"
  );
  // Ammortamenti: gap → ce09c_svalutazioni
  reconcile(
    ["ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti"],
    "ce09_ammortamenti", "ce09c_svalutazioni"
  );
  // Debiti breve: gap → sp16g_altri_debiti_breve
  reconcile(
    ["sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
     "sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve"],
    "sp16_debiti_breve", "sp16g_altri_debiti_breve"
  );
  // Debiti lungo: gap → sp17g_altri_debiti_lungo
  reconcile(
    ["sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
     "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo"],
    "sp17_debiti_lungo", "sp17g_altri_debiti_lungo"
  );
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

  // Step 1b: Rettifiche (Adjustments)
  const [adjustableData, setAdjustableData] = useState<AdjustableFinancialYear | null>(null);
  const [referenceYearData, setReferenceYearData] = useState<Record<string, number> | null>(null);
  const [corrections, setCorrections] = useState<Record<string, number>>({});
  const [loadingAdjustable, setLoadingAdjustable] = useState(false);
  const [savingAdjustments, setSavingAdjustments] = useState(false);
  const [adjustmentsApplied, setAdjustmentsApplied] = useState(false);

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
    setActiveTab("rettifiche");
  };

  // STEP 1: Import Handler (infra-year PDF/XBRL)
  const handleImport = async () => {
    if (!file) {
      toast.error("Seleziona un file da importare");
      return;
    }

    setImporting(true);
    // Clear stale rettifiche state from any previous import
    setAdjustableData(null);
    setReferenceYearData(null);
    setCorrections({});
    setAdjustmentsApplied(false);
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
      let msg = "Errore durante l'importazione";
      if (error && typeof error === "object" && "response" in error) {
        const resp = (error as { response?: { status?: number; data?: { detail?: string } } }).response;
        if (resp?.status === 400 || resp?.status === 422) {
          msg = resp.data?.detail || "Dati non validi. Verificare il file e l'anno fiscale.";
        } else if (resp?.data?.detail) {
          msg = resp.data.detail;
        }
      } else if (error instanceof Error) {
        msg = error.message;
      }
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

  // Load adjustable data when rettifiche tab is active
  const loadAdjustable = useCallback(async () => {
    if (!importResult) return;
    setLoadingAdjustable(true);
    try {
      const refYear = fiscalYear - 1;
      // Fetch current year adjustable data + reference year in parallel
      const [data, refData] = await Promise.all([
        getAdjustableFinancialYear(
          importResult.companyId,
          fiscalYear,
          periodMonths < 12 ? periodMonths : undefined
        ),
        getAdjustableFinancialYear(importResult.companyId, refYear).catch(() => null),
      ]);
      setAdjustableData(data);
      // Merge reference year BS+IS into a single dict
      if (refData) {
        setReferenceYearData({ ...refData.balance_sheet, ...refData.income_statement });
      }
      // Initialize corrections from SAVED values (balance_sheet/income_statement),
      // which include any previously applied rettifiche. Original values are used
      // only for delta display and proposal calculation.
      const initial: Record<string, number> = {};
      for (const [k, v] of Object.entries(data.balance_sheet)) initial[k] = v;
      for (const [k, v] of Object.entries(data.income_statement)) initial[k] = v;
      reconcileSubfields(initial);
      setCorrections(initial);
      // Check if adjustments were previously applied (saved values differ from originals)
      const hasExisting = data.original_balance_sheet && Object.keys(data.balance_sheet).some(k => {
        const saved = data.balance_sheet[k] ?? 0;
        const orig = data.original_balance_sheet![k] ?? 0;
        return Math.abs(saved - orig) > 0.01;
      });
      setAdjustmentsApplied(!!hasExisting);
    } catch (error: unknown) {
      // 404 = year not found (user may have entered wrong fiscal year)
      const is404 = error && typeof error === "object" && "response" in error &&
        (error as { response?: { status?: number } }).response?.status === 404;
      if (is404) {
        toast.error(
          `Dati per l'anno ${fiscalYear} non trovati. Verificare l'anno fiscale inserito.`
        );
      } else {
        const msg = error instanceof Error ? error.message : "Errore nel caricamento dati";
        toast.error(msg);
      }
    } finally {
      setLoadingAdjustable(false);
    }
  }, [importResult, fiscalYear, periodMonths]);

  useEffect(() => {
    if (activeTab === "rettifiche" && !adjustableData && importResult) {
      loadAdjustable();
    }
  }, [activeTab, adjustableData, importResult, loadAdjustable]);

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
          ce14_override: parseFloat(overrides["ce14_altri_proventi_finanziari"] || "0") || null,
          ce15_override: parseFloat(overrides["ce15_oneri_finanziari"] || "0") || null,
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
          ce14_override: comparison.income_items.find(i => i.code === "ce14_altri_proventi_finanziari")?.partial_value ?? null,
          ce15_override: comparison.income_items.find(i => i.code === "ce15_oneri_finanziari")?.partial_value ?? null,
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
    // Clear rettifiche state so it reloads for the new scenario
    setAdjustableData(null);
    setReferenceYearData(null);
    setCorrections({});
    setAdjustmentsApplied(false);
    setComparison(null);
    setAnalysis(null);
    setActiveTab("comparison");
  };

  const handleDeleteCompany = async (id: number, name: string) => {
    try {
      await deleteCompany(id);
      // Immediately remove stale scenarios for this company so the list
      // doesn't show clickable entries for a deleted company.
      setExistingScenarios((prev) => prev.filter((e) => e.company.id !== id));
      await refreshCompanies();
      if (selectedCompany === id) setSelectedCompany(null);
      if (importResult?.companyId === id) {
        // Reset all wizard state tied to the deleted company
        setImportResult(null);
        setScenario(null);
        setComparison(null);
        setAnalysis(null);
        setOverrides({});
        setProjectedBS(null);
        setMissingRefYear(null);
        setFile(null);
        setRefFile(null);
        setAdjustableData(null);
        setReferenceYearData(null);
        setCorrections({});
        setAdjustmentsApplied(false);
      }
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
    { id: "rettifiche", label: "Rettifiche", icon: Pencil, enabled: !!importResult },
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
                    key={file ? "has-file" : "no-file"}
                    type="file"
                    accept={importType === "pdf" ? ".pdf,.PDF" : ".xbrl,.XBRL,.xml,.XML"}
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
                        key={refFile ? "has-ref" : "no-ref"}
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
                    onClick={() => setActiveTab("rettifiche")}
                  >
                    Vai alle Rettifiche
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
                </div>
              ) : (
                <div className="flex justify-end">
                <Button
                  onClick={handleImport}
                  disabled={importing || !file}
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
                </div>
              )}
            </CardContent>
          </Card>
        </div>}

        {/* STEP 1b: RETTIFICHE */}
        {activeTab === "rettifiche" && <RettificheTab
          adjustableData={adjustableData}
          referenceYearData={referenceYearData}
          referenceYear={fiscalYear - 1}
          periodMonths={periodMonths}
          fiscalYear={fiscalYear}
          corrections={corrections}
          setCorrections={setCorrections}
          loading={loadingAdjustable}
          saving={savingAdjustments}
          adjustmentsApplied={adjustmentsApplied}
          onSave={async (finalCorrections?: Record<string, number>) => {
            if (!importResult || !adjustableData) return;
            setSavingAdjustments(true);
            try {
              const corr = finalCorrections ?? corrections;
              const bs: Record<string, number> = {};
              const is_: Record<string, number> = {};
              for (const k of Object.keys(adjustableData.balance_sheet)) {
                bs[k] = corr[k] ?? adjustableData.balance_sheet[k];
              }
              for (const k of Object.keys(adjustableData.income_statement)) {
                is_[k] = corr[k] ?? adjustableData.income_statement[k];
              }
              const result = await saveAdjustments(
                importResult.companyId,
                fiscalYear,
                bs,
                is_,
                periodMonths < 12 ? periodMonths : undefined
              );
              setAdjustableData(result);
              setAdjustmentsApplied(true);
              setComparison(null); // Force reload comparison with corrected data
              toast.success("Rettifiche salvate");
            } catch (error: unknown) {
              const msg = axios.isAxiosError(error) ? error.response?.data?.detail || error.message : "Errore nel salvataggio";
              toast.error(msg);
            } finally {
              setSavingAdjustments(false);
            }
          }}
          onReset={async () => {
            if (!importResult || !adjustableData?.original_balance_sheet || !adjustableData?.original_income_statement) return;
            setSavingAdjustments(true);
            try {
              const result = await saveAdjustments(
                importResult.companyId,
                fiscalYear,
                adjustableData.original_balance_sheet,
                adjustableData.original_income_statement,
                periodMonths < 12 ? periodMonths : undefined
              );
              setAdjustableData(result);
              // Reset corrections to original values
              const initial: Record<string, number> = {};
              for (const [k, v] of Object.entries(result.balance_sheet)) initial[k] = v;
              for (const [k, v] of Object.entries(result.income_statement)) initial[k] = v;
              reconcileSubfields(initial);
              setCorrections(initial);
              setAdjustmentsApplied(false);
              setComparison(null);
              toast.success("Rettifiche annullate — ripristinati i valori originali");
            } catch (error: unknown) {
              toast.error("Errore nel ripristino");
            } finally {
              setSavingAdjustments(false);
            }
          }}
          onNext={() => setActiveTab("comparison")}
        />}

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
                    priorYear={comparison.prior_year}
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
                    priorYear={comparison.prior_year}
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
                priorYear={comparison.prior_year}
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
  priorYear,
  showAnnualized,
  showRevenuePct = false,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  priorYear: number | null;
  showAnnualized: boolean;
  showRevenuePct?: boolean;
}) {
  const expectedPct = (periodMonths / 12) * 100;
  const hasPriorYear = priorYear != null && items.some((i) => i.prior_value !== 0);

  // Revenue values for % computation
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const priorRevenue = showRevenuePct && hasPriorYear
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.prior_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Column date labels
  const priorDate = priorYear ? `31/12/${priorYear}` : "";
  const refDate = `31/12/${referenceYear}`;
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
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
          {hasPriorYear && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
              Storico
            </TableHead>
          )}
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
          {hasPriorYear && (
            <TableHead className="text-right text-xs font-semibold">{priorDate}</TableHead>
          )}
          {hasPriorYear && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
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
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit",
              "_totale_attivo", "_totale_passivo",
              "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isDetail = item.code in DETAIL_PARENTS;

            // Section headers: bold label spanning all columns
            if (isHeader) {
              // Count total columns: 1 (label) + [colSpan (prior)] + colSpan (ref) + colSpan (partial) + [colSpan (ann)] + 1 (delta)
              const totalCols = 1 + (hasPriorYear ? colSpan : 0) + colSpan + colSpan + (showAnnualized ? colSpan : 0) + 1;
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
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
                  {item.label}
                </TableCell>
                {/* Prior year (anno precedente) */}
                {hasPriorYear && (
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {isPctRow ? formatPct(item.prior_value) : formatEuro(item.prior_value)}
                  </TableCell>
                )}
                {hasPriorYear && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.prior_value, priorRevenue))}
                  </TableCell>
                )}
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
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
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
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isEditable = EDITABLE_CE_CODES.includes(item.code);
            const isDetail = item.code in DETAIL_PARENTS;

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
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
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
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale/<br />Storico</TableHead>
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
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
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
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale/<br />Storico</TableHead>
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
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
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
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione<br />{partialYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione/<br />Storico</TableHead>
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
                  <TableCell className={cn(isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs font-medium">
                    {formatEuro(projValue)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
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
      <div className="print:break-before-page">
        <h2 className="text-base font-semibold mb-2">
          Stato Patrimoniale — Proiezione {partialYear}
        </h2>
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione<br />{partialYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione/<br />Storico</TableHead>
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
                  <TableCell className={cn(isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs font-medium">
                    {isNaN(projVal) ? <span className="text-muted-foreground">-</span> : formatEuro(projVal)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
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
        <div className="rounded-lg border border-border p-4 print:p-2 space-y-2 print:space-y-0.5">
          {EXTRA_ALERT_DEFS.map((def, idx) => {
            const isActive = !!extraAlerts[def.key];
            return (
              <div key={def.key} className="flex items-start gap-2 text-sm print:text-[10px] print:leading-tight">
                <span className={cn(
                  "mt-0.5 inline-block h-4 w-4 print:h-3 print:w-3 shrink-0 rounded border text-center text-xs print:text-[8px] leading-4 print:leading-3",
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
