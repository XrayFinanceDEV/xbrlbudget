"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Tooltip,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { ScenarioAnalysis, ScenarioAnalysisYearData } from "@/types/api";

interface ReportCompositionProps {
  data: ScenarioAnalysis;
}

const assetConfig: ChartConfig = {
  immobilizzazioni: { label: "Immobilizzazioni", color: "hsl(var(--chart-1))" },
  rimanenze: { label: "Rimanenze", color: "hsl(var(--chart-2))" },
  crediti: { label: "Crediti", color: "hsl(var(--chart-3))" },
  liquidita: { label: "Liquidita", color: "hsl(var(--chart-4))" },
  altro_attivo: { label: "Altro Attivo", color: "hsl(var(--chart-5))" },
};

const liabilityConfig: ChartConfig = {
  patrimonio_netto: { label: "Patrimonio Netto", color: "hsl(var(--chart-1))" },
  debiti_breve: { label: "Debiti Breve", color: "hsl(var(--chart-2))" },
  debiti_lungo: { label: "Debiti M/L", color: "hsl(var(--chart-3))" },
  fondi_tfr: { label: "Fondi/TFR", color: "hsl(var(--chart-4))" },
  altro_passivo: { label: "Altro Passivo", color: "hsl(var(--chart-5))" },
};

function getCompositionData(allYears: ScenarioAnalysisYearData[]) {
  return allYears.map((y) => {
    const bs = y.balance_sheet;
    const ta = bs.total_assets || 1;

    // Assets as % of total
    const immob = (bs.sp02_immob_immateriali || 0) + (bs.sp03_immob_materiali || 0) +
      (bs.sp04_immob_finanziarie || 0) + (bs.sp01_crediti_soci || 0);
    const rimanenze = bs.sp05_rimanenze || 0;
    const crediti = (bs.sp06_crediti_breve || 0) + (bs.sp07_crediti_lungo || 0);
    const liquidita = (bs.sp09_disponibilita_liquide || 0) + (bs.sp08_attivita_finanziarie || 0);
    const altroAttivo = bs.sp10_ratei_risconti_attivi || 0;

    return {
      year: y.year,
      // Asset %
      immobilizzazioni: +((immob / ta) * 100).toFixed(1),
      rimanenze: +((rimanenze / ta) * 100).toFixed(1),
      crediti: +((crediti / ta) * 100).toFixed(1),
      liquidita: +((liquidita / ta) * 100).toFixed(1),
      altro_attivo: +((altroAttivo / ta) * 100).toFixed(1),
      // Liability %
      patrimonio_netto: +(((bs.total_equity || 0) / ta) * 100).toFixed(1),
      debiti_breve: +(((bs.sp16_debiti_breve || 0) / ta) * 100).toFixed(1),
      debiti_lungo: +(((bs.sp17_debiti_lungo || 0) / ta) * 100).toFixed(1),
      fondi_tfr: +(((bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0)) / ta * 100).toFixed(1),
      altro_passivo: +(((bs.sp18_ratei_risconti_passivi || 0)) / ta * 100).toFixed(1),
    };
  });
}

export function ReportComposition({ data }: ReportCompositionProps) {
  const allYears = [...data.historical_years, ...data.forecast_years].sort(
    (a, b) => a.year - b.year
  );
  const chartData = getCompositionData(allYears);

  return (
    <section id="composition">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Composizione Patrimoniale</CardTitle>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Asset Composition */}
          <div>
            <h3 className="text-base font-semibold mb-3">Composizione Attivo (%)</h3>
            <ChartContainer config={assetConfig} className="h-[300px] w-full">
              <BarChart data={chartData} stackOffset="expand">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => `${value.toFixed(1)}%`}
                />
                <Legend />
                <Bar dataKey="immobilizzazioni" stackId="a" fill="hsl(var(--chart-1))" />
                <Bar dataKey="rimanenze" stackId="a" fill="hsl(var(--chart-2))" />
                <Bar dataKey="crediti" stackId="a" fill="hsl(var(--chart-3))" />
                <Bar dataKey="liquidita" stackId="a" fill="hsl(var(--chart-4))" />
                <Bar dataKey="altro_attivo" stackId="a" fill="hsl(var(--chart-5))" />
              </BarChart>
            </ChartContainer>
          </div>

          {/* Liability Composition */}
          <div>
            <h3 className="text-base font-semibold mb-3">Composizione Passivo (%)</h3>
            <ChartContainer config={liabilityConfig} className="h-[300px] w-full">
              <BarChart data={chartData} stackOffset="expand">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => `${value.toFixed(1)}%`}
                />
                <Legend />
                <Bar dataKey="patrimonio_netto" stackId="a" fill="hsl(var(--chart-1))" />
                <Bar dataKey="debiti_breve" stackId="a" fill="hsl(var(--chart-2))" />
                <Bar dataKey="debiti_lungo" stackId="a" fill="hsl(var(--chart-3))" />
                <Bar dataKey="fondi_tfr" stackId="a" fill="hsl(var(--chart-4))" />
                <Bar dataKey="altro_passivo" stackId="a" fill="hsl(var(--chart-5))" />
              </BarChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
