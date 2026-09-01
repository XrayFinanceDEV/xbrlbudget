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
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  INDICATOR_CHART_BOXES,
  buildIndicatorChartData,
  formatIndicatorAxis,
  formatIndicatorTooltip,
  type IndicatorChartBox,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";

/**
 * I sei grafici della sezione Indicatori, resi sia dalla tab Indicatori sia
 * dalla Stampa.
 *
 * Stanno in un componente solo perché sono lo stesso grafico: duplicarne la
 * configurazione avrebbe creato due definizioni dello stesso oggetto, che è
 * esattamente ciò che il catalogo IV-CEE ha appena finito di eliminare per le
 * etichette. Le ETICHETTE delle serie restano invece di chi chiama, perché
 * divergono per davvero: "Infrann. 9M" nella tab, "Infrann. 9M 2026" in Stampa.
 *
 * Quale serie sta in quale riquadro, con quale unità e con quale colore, è dato
 * puro e vive in `lib/pratica-indicators.ts` (`INDICATOR_CHART_BOXES`): la
 * suite gira senza DOM, quindi questo file non è verificabile e la
 * configurazione sì. Qui non si aggiunge un riquadro scritto a mano — si
 * aggiunge una voce là, e il test sulle unità la vede.
 */

function chartConfig(box: IndicatorChartBox): ChartConfig {
  return Object.fromEntries(
    box.series.map((s) => [s.key, { label: s.label, color: s.color }]),
  ) satisfies ChartConfig;
}

export function IndicatoriCharts({ serie }: { serie: SerieIndicatori[] }) {
  // Una serie assente viene SCARTATA, non resa a zero: una barra a zero su CCN
  // o DSCR sarebbe indistinguibile da un'azienda senza circolante.
  const data = buildIndicatorChartData(serie);

  return (
    // Due griglie diverse, di proposito.
    //
    // A schermo 2×3 (`xl:grid-cols-2`): l'ordine dei riquadri accosta su ogni
    // riga un'unità percentuale e una in euro o in volte.
    //
    // In stampa 3×2. Un A4 utile è ~718px, sotto il breakpoint `xl`: senza una
    // regola `print:` i sei grafici si impilerebbero in una colonna sola,
    // occupando due pagine e spingendo la tabella degli indicatori a finire da
    // sola su una terza. Con tre colonne le righe diventano due e l'intero
    // blocco Indicatori — cartellini di rating, grafici e tabella — sta in una
    // pagina; è la stessa ragione per cui la versione a due grafici forzava
    // `print:grid-cols-2`, ricalcolata su sei.
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 print:grid-cols-3 print:gap-2">
      {INDICATOR_CHART_BOXES.map((box) => (
        <Card key={box.id} className="print:break-inside-avoid">
          <CardHeader>
            <CardTitle className="text-base print:text-[11px] print:leading-tight">
              {box.title}
            </CardTitle>
            {/* In stampa la descrizione sparisce: a un terzo di A4 andrebbe a
                capo tre volte, alzando le righe di misura diversa l'una
                dall'altra. La legenda dice già che cosa sono le barre. */}
            <CardDescription className="print:hidden">{box.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer
              config={chartConfig(box)}
              className="h-[260px] w-full print:h-[150px] print:text-[8px]"
            >
              <RechartsBarChart data={data}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="periodo" tickLine={false} axisLine={false} />
                <YAxis
                  tickFormatter={(value) => formatIndicatorAxis(Number(value), box.format)}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      formatter={(value) => formatIndicatorTooltip(Number(value), box.format)}
                    />
                  }
                />
                {/* La legenda non è una rifinitura: su carta il tooltip non
                    esiste, e senza di lei sei riquadri sono diciotto barre
                    colorate senza nome. */}
                <ChartLegend content={<ChartLegendContent className="print:pt-1" />} />
                {box.series.map((s) => (
                  <Bar key={s.key} dataKey={s.key} fill={`var(--color-${s.key})`} radius={3} />
                ))}
              </RechartsBarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
