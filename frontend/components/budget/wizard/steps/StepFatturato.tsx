"use client";

// Passo 2 del wizard delle ipotesi (Task 11 §2): ricavi e altri ricavi.
// L'unica variazione % editabile e' quella sull'anno precedente; tutto il
// resto — subtotali, crescita cumulata, valore della produzione — arriva
// gia' calcolato da `rowsFatturato` (lib/budget-preview-rows.ts), che a sua
// volta ricapitola solo numeri che il motore ha gia' restituito nel preview.
import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { euro, num, numOrNull } from "@/lib/budget-format";
import { rowsFatturato } from "@/lib/budget-preview-rows";
import { previewNotice } from "@/lib/budget-preview-notice";
import { revenueBarGeometry } from "@/lib/budget-revenue-bars";
import type { ForecastPreviewYear } from "@/types/api";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable } from "../YearInputTable";
import type { StepProps } from "../types";

/**
 * Mini-grafico a barre dei ricavi: base + anni proiettati, sulla stessa
 * scala. La geometria (altezza, posizione) e' calcolata in
 * `lib/budget-revenue-bars.ts` — qui solo il rendering SVG.
 */
function RevenueBars({ base, years }: { base: number; years: ForecastPreviewYear[] }) {
  const bars = revenueBarGeometry(base, years);
  if (bars.length === 0) return null;
  const slot = 400 / bars.length;
  return (
    <svg viewBox="0 0 400 56" preserveAspectRatio="none" className="mt-3 h-14 w-full">
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={i * slot + slot * 0.15}
          y={bar.y}
          width={slot * 0.7}
          height={bar.height}
          className={bar.isBase ? "fill-muted-foreground/60" : "fill-primary"}
        />
      ))}
    </svg>
  );
}

export function StepFatturato(p: StepProps) {
  const baseInc = p.historical[p.baseYear]?.income;
  // Gli anni delle colonne sono quelli che il motore ha davvero prodotto
  // (`data.forecast_years`), non quelli richiesti (`p.forecastYears`): se il
  // motore si e' fermato a meta' (fabbisogno scoperto) le intestazioni non
  // restano senza celle sotto. Stessa convenzione di lib/budget-costi-step.ts
  // (fix round 1, rilievo 3-a).
  // La `useMemo` sotto dipende da questo array: ricavarlo fuori da una memo
  // ne cambiava l'identita' a ogni render e la memo non memoizzava piu' nulla.
  const previewYears = useMemo(() => p.preview.data?.forecast_years ?? [], [p.preview.data]);
  const rows = useMemo(() => (baseInc ? rowsFatturato(baseInc, previewYears) : []),
    [baseInc, previewYears]);
  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <Card>
        <CardHeader><CardTitle className="text-base">Variazione % sull&apos;anno precedente</CardTitle></CardHeader>
        <CardContent>
          <YearInputTable forecastYears={p.forecastYears} baseYear={p.baseYear} assumptions={p.assumptions} update={p.update}
            rows={[
              // Senza anno base si scrive «—», non «€ 0»: uno zero vero e uno
              // zero di ripiego non sono la stessa cosa, ed e' la regola degli
              // altri sei passi (lib/budget-costi-step.ts).
              { field: "revenue_growth_pct", label: "Ricavi delle vendite", baseLabel: euro(numOrNull(baseInc?.ce01_ricavi_vendite)) },
              { field: "other_revenue_growth_pct", label: "Altri ricavi e proventi", baseLabel: euro(numOrNull(baseInc?.ce04_altri_ricavi)) },
            ]} />
          <p className="mt-2 text-xs text-muted-foreground">Le percentuali si applicano all&apos;anno precedente, non al {p.baseYear}.</p>
        </CardContent>
      </Card>
      <div className="lg:sticky lg:top-4">
        <PreviewPanel title="Ricavi proiettati" baseYear={p.baseYear} years={previewYears.map((y) => y.year)} rows={rows}
          loading={p.preview.loading} error={previewNotice(p.preview)}>
          <RevenueBars base={num(baseInc?.ce01_ricavi_vendite)} years={previewYears} />
        </PreviewPanel>
      </div>
    </div>
  );
}
