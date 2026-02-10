"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ReportGauge } from "./report-gauge";
import { getEMScoreColor } from "./report-types";
import { formatCurrency, formatNumber, getAltmanColor, getFGPMIColor } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportDashboardProps {
  data: ScenarioAnalysis;
}

export function ReportDashboard({ data }: ReportDashboardProps) {
  // Use the latest year's calculations
  const allYears = [
    ...data.historical_years.map((y) => y.year),
    ...data.forecast_years.map((y) => y.year),
  ].sort((a, b) => a - b);

  const latestYear = allYears[allYears.length - 1];
  const calc = data.calculations.by_year[String(latestYear)];
  if (!calc) return null;

  const baseYear = data.scenario.base_year;
  const baseCalc = data.calculations.by_year[String(baseYear)];

  // Find latest year data for KPIs
  const latestYearData = [...data.historical_years, ...data.forecast_years].find(
    (y) => y.year === latestYear
  );

  const altmanZones = [
    { from: -4, to: 1.1, color: "hsl(215, 25%, 47%)" },
    { from: 1.1, to: 2.6, color: "hsl(220, 14%, 60%)" },
    { from: 2.6, to: 10, color: "hsl(221, 83%, 53%)" },
  ];

  const fgpmiZones = [
    { from: 0, to: 30, color: "hsl(215, 25%, 47%)" },
    { from: 30, to: 60, color: "hsl(220, 14%, 60%)" },
    { from: 60, to: 100, color: "hsl(221, 83%, 53%)" },
  ];

  const emScoreToNum = (rating: string): number => {
    const scale: Record<string, number> = {
      AAA: 95, "AA+": 90, AA: 85, "AA-": 80,
      "A+": 75, A: 70, "A-": 65,
      "BBB+": 60, BBB: 55, "BBB-": 50,
      "BB+": 45, BB: 40, "BB-": 35,
      "B+": 30, B: 25, "B-": 20,
      "CCC+": 15, CCC: 10, "CCC-": 5, D: 2,
    };
    return scale[rating] ?? 50;
  };

  const emZones = [
    { from: 0, to: 30, color: "hsl(215, 25%, 47%)" },
    { from: 30, to: 60, color: "hsl(220, 14%, 60%)" },
    { from: 60, to: 100, color: "hsl(221, 83%, 53%)" },
  ];

  const fgpmiPct = calc.fgpmi.max_score > 0
    ? (calc.fgpmi.total_score / calc.fgpmi.max_score) * 100
    : 0;

  return (
    <section id="dashboard">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Dashboard Sintetica</CardTitle>
          <p className="text-sm text-muted-foreground">
            Ultimo anno analizzato: {latestYear}
          </p>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Gauges */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="flex flex-col items-center">
              <ReportGauge
                value={calc.altman.z_score}
                min={-4}
                max={10}
                label={formatNumber(calc.altman.z_score, 2)}
                sublabel={calc.altman.interpretation_it}
                zones={altmanZones}
              />
              <Badge
                variant="outline"
                className={cn("mt-2", getAltmanColor(calc.altman.classification))}
              >
                Altman Z-Score
              </Badge>
            </div>

            <div className="flex flex-col items-center">
              <ReportGauge
                value={fgpmiPct}
                min={0}
                max={100}
                label={calc.fgpmi.rating_code}
                sublabel={`${calc.fgpmi.total_score}/${calc.fgpmi.max_score} punti`}
                zones={fgpmiZones}
              />
              <Badge
                variant="outline"
                className={cn("mt-2", getFGPMIColor(calc.fgpmi.rating_code))}
              >
                Rating FGPMI
              </Badge>
            </div>

            <div className="flex flex-col items-center">
              <ReportGauge
                value={emScoreToNum(calc.em_score?.rating ?? "N/D")}
                min={0}
                max={100}
                label={calc.em_score?.rating ?? "N/D"}
                sublabel={calc.em_score?.description ?? ""}
                zones={emZones}
              />
              <Badge
                variant="outline"
                className={cn("mt-2", getEMScoreColor(calc.em_score?.rating ?? ""))}
              >
                EM-Score
              </Badge>
            </div>
          </div>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {latestYearData && (
              <>
                <MetricCard
                  label="Fatturato"
                  value={formatCurrency(latestYearData.income_statement.revenue || latestYearData.income_statement.ce01_ricavi_vendite || 0)}
                />
                <MetricCard
                  label="EBITDA"
                  value={formatCurrency(latestYearData.income_statement.ebitda || 0)}
                />
                <MetricCard
                  label="Utile Netto"
                  value={formatCurrency(latestYearData.income_statement.net_profit || 0)}
                />
                <MetricCard
                  label="Totale Attivo"
                  value={formatCurrency(latestYearData.balance_sheet.total_assets || 0)}
                />
              </>
            )}
            <MetricCard
              label="ROE"
              value={formatNumber(calc.ratios.profitability.roe * 100, 2) + "%"}
            />
            <MetricCard
              label="ROI"
              value={formatNumber(calc.ratios.profitability.roi * 100, 2) + "%"}
            />
            <MetricCard
              label="Current Ratio"
              value={formatNumber(calc.ratios.liquidity.current_ratio, 2)}
            />
            <MetricCard
              label="D/E Ratio"
              value={formatNumber(calc.ratios.solvency.debt_to_equity, 2)}
            />
          </div>

          {/* Year comparison if base year exists */}
          {baseCalc && baseYear !== latestYear && (
            <div className="text-sm text-muted-foreground text-center">
              Confronto anno base {baseYear}: Z-Score{" "}
              {formatNumber(baseCalc.altman.z_score, 2)} | FGPMI{" "}
              {baseCalc.fgpmi.rating_code}
              {baseCalc.em_score && <> | EM-Score {baseCalc.em_score.rating}</>}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card p-3 text-center">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold text-foreground mt-0.5">{value}</div>
    </div>
  );
}
