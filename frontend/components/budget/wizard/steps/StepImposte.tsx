"use client";

// Passo 7 del wizard ipotesi: imposte (spec 2026-09-08 §4.7, task-14-brief.md).
// È l'ULTIMO passo — non c'è un ottavo passo di riepilogo: il wizard si
// chiude qui e il previsionale completo si legge e si ritocca nelle tab CE
// Prev. e SP Prev. esistenti.
//
// Presentazionale: ogni decisione — che cosa mostrare/scrivere per
// l'aliquota forzata, quali anni ha davvero prodotto il motore — sta in
// lib/budget-imposte-step.ts, provata in environment: node. Le imposte NON
// si ricalcolano qui: le produce il motore, rowsImposte le legge dal CE che
// il motore ha già scritto.
import type { JSX } from "react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TaxTemporaryDifferencesGrid } from "@/components/budget/TaxTemporaryDifferencesGrid";
import { computeEffectiveTaxRate } from "@/components/budget/assumption-rows";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { formatPercentage } from "@/lib/formatters";
import {
  DEFAULT_TAX_RATE,
  TAX_RATE_PLACEHOLDER,
  impostePreview,
  spTributariRows,
  taxRateInputDisplay,
  taxRateValue,
} from "@/lib/budget-imposte-step";
import { planTaxRate } from "@/lib/budget-tax-rate";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";

const pct1 = (v: number | null): string => (v === null ? "—" : formatPercentage(v / 100, 1));

const ADVANCES_ROWS: YearInputRow[] = [{ field: "tax_advances_paid", label: "Acconti versati nell'anno", baseLabel: "—" }];

/** Un Select disabilitato con un solo valore: segnaposto del lotto 2. */
function Lotto2Select({ text, className }: { text: string; className?: string }): JSX.Element {
  return (
    <Select disabled value="lotto2">
      <SelectTrigger className={className ?? "h-8 w-40 text-xs"}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="lotto2">{text}</SelectItem>
      </SelectContent>
    </Select>
  );
}

export function StepImposte(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const baseBs = p.historical[p.baseYear]?.balance;
  const effectiveRate = baseInc ? computeEffectiveTaxRate(baseInc) : null;

  const taxRate = taxRateValue(p.assumptions, p.forecastYears);
  const taxRateDisplay = taxRateInputDisplay(taxRate);
  // Quale aliquota il piano usera' davvero, e perche': una sola funzione, la
  // stessa che rende il passo 4 (lib/budget-tax-rate.ts). Prima i due passi
  // rispondevano in modo diverso sullo stesso caso.
  const plan = useMemo(
    () => planTaxRate(effectiveRate, p.assumptions, p.forecastYears),
    [effectiveRate, p.assumptions, p.forecastYears],
  );

  const tributariRows = useMemo(() => spTributariRows(baseBs), [baseBs]);
  const preview = useMemo(() => impostePreview(baseInc, p.preview.data), [baseInc, p.preview.data]);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Aliquota</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota effettiva {p.baseYear}</div>
                <div className="text-xs text-muted-foreground">imposte / utile ante imposte</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm tabular-nums text-foreground">{pct1(effectiveRate)}</span>
                {plan.source === "effettiva" && <Badge variant="secondary">usata dal piano</Badge>}
              </div>
            </div>

            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota forzata</div>
                <div className="text-xs text-muted-foreground">
                  vuota = usa l&apos;effettiva, o {pct1(DEFAULT_TAX_RATE)} se non derivabile
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  // 80 px non bastavano nemmeno al segnaposto: a schermo si
                  // leggeva «auto :». Qui ci sta il segnaposto e ci sta un
                  // valore digitato di quattro cifre e una virgola.
                  className="w-28 text-right"
                  aria-label="Aliquota forzata"
                  placeholder={TAX_RATE_PLACEHOLDER}
                  value={taxRateDisplay}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    const v = raw === "" ? DEFAULT_TAX_RATE : (parseFieldValue("tax_rate", raw) ?? DEFAULT_TAX_RATE);
                    p.updateAll("tax_rate", v);
                  }}
                />
                <span className="text-xs text-muted-foreground">%</span>
              </div>
            </div>

            {/* Nel caso comune questa riga ripeterebbe numero e badge di
                quella dell'aliquota effettiva: `addsInformation` (deciso in
                lib/budget-tax-rate.ts, col suo test) dice quando serve. */}
            {plan.addsInformation && (
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
                <div>
                  <div className="text-sm font-medium text-foreground">Aliquota usata dal piano</div>
                  {plan.nota && <div className="text-xs text-muted-foreground">{plan.nota}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm tabular-nums text-foreground">{plan.value}</span>
                  <Badge variant={plan.source === "effettiva" ? "secondary" : "outline"}>
                    {plan.sourceLabel}
                  </Badge>
                </div>
              </div>
            )}

            <div>
              <YearInputTable
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                assumptions={p.assumptions}
                update={p.update}
                rows={ADVANCES_ROWS}
              />
            </div>
          </CardContent>
        </Card>

        <TaxTemporaryDifferencesGrid
          forecastYears={p.forecastYears}
          assumptions={p.assumptions}
          onUpdate={p.updateTemporaryDifferences}
        />

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Pagamento dei debiti tributari</CardTitle>
            <Badge variant="outline">lotto 2</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <YearInputTable
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
              rows={tributariRows}
            />
            <div className="space-y-2 border-t border-border/50 pt-2.5">
              <Lotto2Select text="Correnti · anno successivo" className="h-8 w-full text-xs" />
              <Lotto2Select text="Rateizzati · 3 rate annuali" className="h-8 w-full text-xs" />
            </div>
            <p className="pt-1 text-xs text-muted-foreground">
              Oggi il motore muove la posizione tributaria come precedente + imposte dell&apos;anno − acconti. La
              divisione fra correnti e rateizzati entra con l&apos;estensione del motore.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3 lg:sticky lg:top-4">
        <PreviewPanel
          title="Imposte e risultato netto"
          baseYear={p.baseYear}
          years={preview.years}
          rows={preview.rows}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        />
        <p className="text-xs text-muted-foreground">
          È l&apos;ultimo passo: il previsionale completo si legge e si ritocca nelle tab CE Prev. e SP Prev.
        </p>
      </div>
    </div>
  );
}
