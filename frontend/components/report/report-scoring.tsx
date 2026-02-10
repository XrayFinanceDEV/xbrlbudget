"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Cell,
  ReferenceLine,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { cn } from "@/lib/utils";
import { formatNumber, getAltmanColor, getFGPMIColor } from "@/lib/formatters";
import { getEMScoreColor, EM_SCORE_TABLE, EM_SCORE_DESCRIPTIONS } from "./report-types";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportScoringProps {
  data: ScenarioAnalysis;
}

const altmanTrendConfig: ChartConfig = {
  z_score: { label: "Z-Score", color: "var(--chart-1)" },
};

const altmanComponentConfig: ChartConfig = {
  value: { label: "Valore", color: "var(--chart-1)" },
};

const fgpmiConfig: ChartConfig = {
  points: { label: "Punti", color: "var(--chart-1)" },
  max_points: { label: "Max Punti", color: "var(--chart-3)" },
};

const ALTMAN_LABELS: Record<string, string> = {
  A: "Capitale Circolante/Totale Attivo",
  B: "Utili Non Distribuiti/Totale Attivo",
  C: "EBIT/Totale Attivo",
  D: "Patrimonio Netto/Debiti Totali",
  E: "Fatturato/Totale Attivo",
};

export function ReportScoring({ data }: ReportScoringProps) {
  const allYears = [...data.historical_years, ...data.forecast_years]
    .map((y) => y.year)
    .sort((a, b) => a - b);

  // Latest year for component display
  const latestYear = allYears[allYears.length - 1];
  const latestCalc = data.calculations.by_year[String(latestYear)];
  if (!latestCalc) return null;

  // Altman trend data
  const altmanTrendData = allYears.map((year) => {
    const calc = data.calculations.by_year[String(year)];
    return {
      year,
      z_score: calc?.altman.z_score ?? 0,
      classification: calc?.altman.classification ?? "distress",
    };
  });

  // Altman components (horizontal bar)
  const altmanComponents = Object.entries(latestCalc.altman.components)
    .filter(([, v]) => v != null)
    .map(([key, value]) => ({
      name: key,
      label: ALTMAN_LABELS[key] || key,
      value: value as number,
    }));

  // FGPMI indicators
  const fgpmiIndicators = Object.entries(latestCalc.fgpmi.indicators).map(
    ([key, ind]) => ({
      name: ind.name || key,
      code: ind.code || key,
      points: ind.points,
      max_points: ind.max_points,
      value: ind.value,
      percentage: ind.percentage,
    })
  );

  // EM-Score trend
  const emTrendData = allYears.map((year) => {
    const calc = data.calculations.by_year[String(year)];
    return {
      year,
      rating: calc?.em_score?.rating ?? "N/D",
      z_used: calc?.em_score?.z_score_used ?? 0,
    };
  });

  return (
    <section id="scoring">
      <div className="space-y-6">
        {/* Altman Z-Score */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Altman Z-Score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-4 mb-2">
              <span className="text-sm text-muted-foreground">
                Modello: {latestCalc.altman.model_type === "manufacturing" ? "Manifatturiero (5 componenti)" : "Servizi (4 componenti)"}
              </span>
              <Badge
                variant="outline"
                className={cn(getAltmanColor(latestCalc.altman.classification))}
              >
                {latestCalc.altman.interpretation_it}
              </Badge>
            </div>

            {/* Z-Score Trend */}
            <div>
              <h4 className="text-sm font-medium mb-2">Andamento Z-Score</h4>
              <ChartContainer config={altmanTrendConfig} className="h-[250px] w-full">
                <LineChart data={altmanTrendData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <ReferenceLine y={2.6} stroke="var(--chart-1)" strokeDasharray="5 5" label={{ value: "Safe", position: "right", fontSize: 10 }} />
                  <ReferenceLine y={1.1} stroke="var(--chart-4)" strokeDasharray="5 5" label={{ value: "Distress", position: "right", fontSize: 10 }} />
                  <ChartTooltip
                    content={<ChartTooltipContent />}
                    formatter={(value: number) => formatNumber(value, 2)}
                  />
                  <Line type="monotone" dataKey="z_score" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ChartContainer>
            </div>

            {/* Components (horizontal bar) */}
            <div>
              <h4 className="text-sm font-medium mb-2">Componenti ({latestYear})</h4>
              <ChartContainer config={altmanComponentConfig} className="h-[200px] w-full">
                <BarChart data={altmanComponents} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={30} />
                  <ChartTooltip
                    formatter={(value: number, name: string, props: any) =>
                      [`${formatNumber(value, 4)}`, props.payload.label]
                    }
                  />
                  <Bar dataKey="value" fill="var(--chart-1)" radius={[0, 4, 4, 0]}>
                    {altmanComponents.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={entry.value >= 0 ? "var(--chart-1)" : "var(--chart-4)"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ChartContainer>
            </div>

            {/* Multi-year table */}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Anno</TableHead>
                  <TableHead className="text-right">Z-Score</TableHead>
                  <TableHead>Classificazione</TableHead>
                  {Object.keys(latestCalc.altman.components).filter(k => latestCalc.altman.components[k as keyof typeof latestCalc.altman.components] != null).map((k) => (
                    <TableHead key={k} className="text-right">{k}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {allYears.map((year) => {
                  const calc = data.calculations.by_year[String(year)];
                  if (!calc) return null;
                  return (
                    <TableRow key={year}>
                      <TableCell className="font-medium">{year}</TableCell>
                      <TableCell className={cn("text-right font-semibold", getAltmanColor(calc.altman.classification))}>
                        {formatNumber(calc.altman.z_score, 2)}
                      </TableCell>
                      <TableCell>{calc.altman.interpretation_it}</TableCell>
                      {Object.entries(calc.altman.components).filter(([, v]) => v != null).map(([k, v]) => (
                        <TableCell key={k} className="text-right">{formatNumber(v as number, 4)}</TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* EM-Score */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">EM-Score</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Anno</TableHead>
                  <TableHead className="text-right">Z-Score Utilizzato</TableHead>
                  <TableHead>Rating</TableHead>
                  <TableHead>Descrizione</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emTrendData.map((row) => (
                  <TableRow key={row.year}>
                    <TableCell className="font-medium">{row.year}</TableCell>
                    <TableCell className="text-right">{formatNumber(row.z_used, 2)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn(getEMScoreColor(row.rating))}>
                        {row.rating}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {EM_SCORE_DESCRIPTIONS[row.rating] || ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* FGPMI */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Rating FGPMI</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-4 mb-2">
              <span className="text-sm text-muted-foreground">
                Modello settore: {latestCalc.fgpmi.sector_model}
              </span>
              <Badge
                variant="outline"
                className={cn(getFGPMIColor(latestCalc.fgpmi.rating_code))}
              >
                {latestCalc.fgpmi.rating_code} - {latestCalc.fgpmi.rating_description}
              </Badge>
              <span className="text-sm text-muted-foreground">
                ({latestCalc.fgpmi.total_score}/{latestCalc.fgpmi.max_score} punti)
              </span>
            </div>

            {/* Indicators bar chart */}
            <ChartContainer config={fgpmiConfig} className="h-[250px] w-full">
              <BarChart data={fgpmiIndicators}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="code" tick={{ fontSize: 10 }} />
                <YAxis />
                <ChartTooltip
                  formatter={(value: number, name: string) => [
                    formatNumber(value, 0),
                    name === "points" ? "Punti" : "Max",
                  ]}
                />
                <Legend />
                <Bar dataKey="points" fill="var(--chart-1)" name="Punti" radius={[4, 4, 0, 0]} />
                <Bar dataKey="max_points" fill="var(--chart-5)" name="Max Punti" radius={[4, 4, 0, 0]} opacity={0.4} />
              </BarChart>
            </ChartContainer>

            {/* Indicators table */}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codice</TableHead>
                  <TableHead>Indicatore</TableHead>
                  <TableHead className="text-right">Valore</TableHead>
                  <TableHead className="text-right">Punti</TableHead>
                  <TableHead className="text-right">Max</TableHead>
                  <TableHead className="text-right">%</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fgpmiIndicators.map((ind) => (
                  <TableRow key={ind.code}>
                    <TableCell className="font-medium">{ind.code}</TableCell>
                    <TableCell>{ind.name}</TableCell>
                    <TableCell className="text-right">{formatNumber(ind.value, 4)}</TableCell>
                    <TableCell className="text-right font-semibold">{ind.points}</TableCell>
                    <TableCell className="text-right">{ind.max_points}</TableCell>
                    <TableCell className="text-right">{formatNumber(ind.percentage, 1)}%</TableCell>
                  </TableRow>
                ))}
                <TableRow className="border-t-2">
                  <TableCell className="font-bold" colSpan={3}>TOTALE</TableCell>
                  <TableCell className="text-right font-bold">{latestCalc.fgpmi.total_score}</TableCell>
                  <TableCell className="text-right font-bold">{latestCalc.fgpmi.max_score}</TableCell>
                  <TableCell className="text-right font-bold">
                    {latestCalc.fgpmi.max_score > 0
                      ? formatNumber((latestCalc.fgpmi.total_score / latestCalc.fgpmi.max_score) * 100, 1)
                      : "0"}%
                  </TableCell>
                </TableRow>
                {latestCalc.fgpmi.revenue_bonus > 0 && (
                  <TableRow>
                    <TableCell className="font-medium" colSpan={3}>Bonus Fatturato (&gt; 500K)</TableCell>
                    <TableCell className="text-right font-semibold text-green-600 dark:text-green-400">
                      +{latestCalc.fgpmi.revenue_bonus}
                    </TableCell>
                    <TableCell colSpan={2} />
                  </TableRow>
                )}
              </TableBody>
            </Table>

            {/* Multi-year FGPMI comparison */}
            <div>
              <h4 className="text-sm font-medium mb-2">Evoluzione Rating</h4>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Anno</TableHead>
                    <TableHead className="text-right">Punteggio</TableHead>
                    <TableHead>Rating</TableHead>
                    <TableHead>Rischio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allYears.map((year) => {
                    const calc = data.calculations.by_year[String(year)];
                    if (!calc) return null;
                    return (
                      <TableRow key={year}>
                        <TableCell className="font-medium">{year}</TableCell>
                        <TableCell className="text-right">
                          {calc.fgpmi.total_score}/{calc.fgpmi.max_score}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn(getFGPMIColor(calc.fgpmi.rating_code))}>
                            {calc.fgpmi.rating_code}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{calc.fgpmi.risk_level}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
