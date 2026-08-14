"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  BarChart as RechartsBarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatEuro } from "@/lib/pratica-format";
import { buildIndicatorChartData, type SerieIndicatori } from "@/lib/pratica-indicators";

/**
 * I due grafici della sezione Indicatori, resi sia dalla tab Indicatori sia
 * dalla Stampa.
 *
 * Stanno in un componente solo perché sono lo stesso grafico: duplicarne la
 * configurazione avrebbe creato due definizioni dello stesso oggetto, che è
 * esattamente ciò che il catalogo IV-CEE ha appena finito di eliminare per le
 * etichette. Le ETICHETTE delle serie restano invece di chi chiama, perché
 * divergono per davvero: "Infrann. 9M" nella tab, "Infrann. 9M 2026" in Stampa.
 */

const economicIncidenceChartConfig = {
  ebitda_margin: { label: "EBITDA / Ricavi", color: "hsl(var(--chart-2))" },
  materials_revenue: { label: "Materie / Ricavi", color: "hsl(var(--chart-3))" },
  services_revenue: { label: "Servizi / Ricavi", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

const financialMarginsChartConfig = {
  mt: { label: "Margine di Tesoreria", color: "hsl(var(--chart-1))" },
  ms: { label: "Margine di Struttura", color: "hsl(var(--chart-2))" },
  pfn: { label: "PFN", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

export function IndicatoriCharts({ serie }: { serie: SerieIndicatori[] }) {
  const data = buildIndicatorChartData(serie);

  return (
    // In stampa un A4 è ~794px, sotto il breakpoint `xl`: senza
    // `print:grid-cols-2` i due grafici si impilerebbero e spingerebbero la
    // tabella degli indicatori a pagina nuova. L'altezza scende in parallelo.
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 print:grid-cols-2 print:gap-2">
      <Card className="print:break-inside-avoid">
        <CardHeader>
          <CardTitle className="text-base print:text-sm">Incidenza economica sui ricavi</CardTitle>
          <CardDescription className="print:text-[10px]">
            EBITDA, materie prime e servizi in percentuale dei ricavi.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={economicIncidenceChartConfig}
            className="h-[260px] w-full print:h-[170px]"
          >
            <RechartsBarChart data={data}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="periodo" tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(value) => `${value}%`} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="ebitda_margin" fill="var(--color-ebitda_margin)" radius={3} />
              <Bar dataKey="materials_revenue" fill="var(--color-materials_revenue)" radius={3} />
              <Bar dataKey="services_revenue" fill="var(--color-services_revenue)" radius={3} />
            </RechartsBarChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <Card className="print:break-inside-avoid">
        <CardHeader>
          <CardTitle className="text-base print:text-sm">Equilibrio finanziario e strutturale</CardTitle>
          <CardDescription className="print:text-[10px]">
            Margine di tesoreria, margine di struttura e PFN.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={financialMarginsChartConfig}
            className="h-[260px] w-full print:h-[170px]"
          >
            <RechartsBarChart data={data}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="periodo" tickLine={false} axisLine={false} />
              <YAxis
                tickFormatter={(value) =>
                  new Intl.NumberFormat("it-IT", { notation: "compact" }).format(value)
                }
              />
              <ChartTooltip
                content={<ChartTooltipContent formatter={(value) => formatEuro(Number(value))} />}
              />
              <Bar dataKey="mt" fill="var(--color-mt)" radius={3} />
              <Bar dataKey="ms" fill="var(--color-ms)" radius={3} />
              <Bar dataKey="pfn" fill="var(--color-pfn)" radius={3} />
            </RechartsBarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  );
}
