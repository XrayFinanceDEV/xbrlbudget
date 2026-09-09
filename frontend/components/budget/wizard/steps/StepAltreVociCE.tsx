"use client";

// Passo 4 del wizard ipotesi: le voci minori del CE (spec 2026-09-08 §4.4,
// task-13-brief.md). Presentazionale: ogni decisione — che cosa mostrare
// sotto "Ammortamenti"/"Oneri finanziari"/"Imposte", quali anni ha davvero
// prodotto il motore — sta in lib/budget-altre-voci-step.ts, provata in
// environment: node. L'unica eccezione e' l'aliquota effettiva dell'anno
// base: la calcola computeEffectiveTaxRate (components/budget/
// assumption-rows.ts), che lib/ non puo' importare — il numero passa da
// qui al modulo lib solo per la formattazione col fallback.
import type { JSX } from "react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeEffectiveTaxRate } from "@/components/budget/assumption-rows";
import { altreVociCalculated, altreVociPreview, altreVociTableRows } from "@/lib/budget-altre-voci-step";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable } from "../YearInputTable";

export function StepAltreVociCE(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const effectiveTaxRatePct = baseInc ? computeEffectiveTaxRate(baseInc) : null;

  const rows = altreVociTableRows(baseInc);
  const calculated = useMemo(
    () => altreVociCalculated(p.baseYear, baseInc, effectiveTaxRatePct, p.assumptions, p.forecastYears, p.preview.data),
    [p.baseYear, baseInc, effectiveTaxRatePct, p.assumptions, p.forecastYears, p.preview.data],
  );
  const preview = useMemo(() => altreVociPreview(baseInc, p.preview.data), [baseInc, p.preview.data]);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Voci minori · variazione %</CardTitle>
          </CardHeader>
          <CardContent>
            <YearInputTable
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
              rows={rows}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Calcolate dal piano</CardTitle>
            <Badge variant="secondary">automatico</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2">
              <div>
                <div className="text-sm font-medium text-foreground">Ammortamenti</div>
                <div className="text-xs text-muted-foreground">{calculated.ammortamenti.small}</div>
              </div>
              <div className="whitespace-nowrap text-right text-sm tabular-nums text-foreground">
                {calculated.ammortamenti.value}
              </div>
            </div>
            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2">
              <div>
                <div className="text-sm font-medium text-foreground">Oneri finanziari</div>
                <div className="text-xs text-muted-foreground">{calculated.oneriFinanziari.small}</div>
              </div>
              <div className="whitespace-nowrap text-right text-sm tabular-nums text-foreground">
                {calculated.oneriFinanziari.value}
              </div>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-foreground">Imposte</div>
                <div className="text-xs text-muted-foreground">{calculated.imposte.small}</div>
              </div>
              <div className="whitespace-nowrap text-right text-sm tabular-nums text-foreground">
                {calculated.imposte.value}
              </div>
            </div>
            <p className="pt-1 text-xs text-muted-foreground">
              Un valore forzato a mano nel CE previsionale vince sempre su queste regole, e resta finché non lo
              azzeri dal dialogo Ricalcola.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-4">
        <PreviewPanel
          title="Conto economico sintetico"
          baseYear={p.baseYear}
          years={preview.years}
          rows={preview.rows}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        />
      </div>
    </div>
  );
}
