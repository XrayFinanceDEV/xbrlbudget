"use client";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEuro, formatPct } from "@/lib/pratica-format";
import {
  computeIndicators,
  scoreIndicator,
  INDICATOR_DEFS,
  crisisScores,
  scoreDotColor,
  computeCrisisRating,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";
import { IndicatoriCharts } from "@/components/pratica/IndicatoriCharts";
import type { IntraYearComparison } from "@/types/api";

// Indicatori Table Component
export function IndicatoriTable({
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

  // Il punteggio di crisi NON usa tutte le righe rese sopra: le bande di
  // `computeCrisisRating` sono tarate sul numero di indicatori che le
  // alimentano, quindi il set e' fissato in `CRISIS_SCORING_KEYS`. Gli array
  // qui sopra restano allineati a INDICATOR_DEFS perche' li indicizza il
  // pallino di riga.
  const storicoCrisis = crisisScores(storicoInd);
  const infraCrisis = crisisScores(infraInd);
  const proiezioneCrisis = proiezioneInd ? crisisScores(proiezioneInd) : null;

  // Crisis ratings: storico uses 0 alerts (historical), infra+proiezione include current alerts
  const storicoRating = computeCrisisRating(storicoCrisis, 0);
  const infraRating = computeCrisisRating(infraCrisis, alertCount);
  const proiezioneRating = proiezioneCrisis
    ? computeCrisisRating(proiezioneCrisis, alertCount)
    : null;

  const oltreCount = (scores: number[]) => scores.filter((s) => s < 0.33).length;
  const serieGrafici: SerieIndicatori[] = [
    { periodo: `Storico ${comparison.reference_year}`, indicatori: storicoInd },
    { periodo: `Infrann. ${comparison.period_months}M`, indicatori: infraInd },
    {
      periodo: `Proiezione ${comparison.partial_year}`,
      indicatori: hideProiezione ? null : proiezioneInd,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Overall Rating Cards - only shown after "Calcola Rating" */}
      {showRating && (
        <div className={cn("grid gap-4", hideProiezione ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${comparison.reference_year}`, rating: storicoRating, oltre: oltreCount(storicoCrisis), alerts: 0 },
            { label: `Infrann. ${comparison.period_months}M ${comparison.partial_year}`, rating: infraRating, oltre: oltreCount(infraCrisis), alerts: alertCount },
            ...(!hideProiezione ? [{
              label: `Proiezione ${comparison.partial_year}`,
              rating: proiezioneRating,
              oltre: proiezioneCrisis ? oltreCount(proiezioneCrisis) : null,
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

      <IndicatoriCharts serie={serieGrafici} />

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

