"use client";

// Passo 5 del wizard ipotesi (spec 2026-09-08 §4.5): i giorni medi di
// incasso/magazzino/pagamento — dove il proprietario vuole che si aggiusti
// il circolante "verso la fine del workflow" — e le voci minori
// dell'attivo/passivo che seguono una propria variazione % invece dei
// giorni (task-13-brief.md).
//
// Presentazionale: ogni decisione (quale giorno "auto" mostrare, l'importo
// base di ciascuna voce minore, con quale anno leggere gli interruttori,
// quali anni ha davvero prodotto il motore) sta in
// lib/budget-circolante-step.ts, provata in environment: node. I tre campi
// giorni sono annullabili: vuoto significa "usa il valore derivato
// dall'anno base", mai zero giorni — la distinzione la fa il segnaposto
// `auto N`, mai un placeholder statico.
import type { JSX } from "react";
import { useMemo } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  boolAssumption,
  circolantePreview,
  giorniMediAuto,
  giorniMediRows,
  minorFieldsRows,
  spIndexingOf,
  DRIVERS,
  DRIVER_LABELS,
} from "@/lib/budget-circolante-step";
import { AlertTriangle, Link2, Minus } from "lucide-react";
import type { SpIndexingDriver } from "@/types/api";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable } from "../YearInputTable";

export function StepCircolante(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const baseBs = p.historical[p.baseYear]?.balance;

  const auto = useMemo(() => giorniMediAuto(baseInc, baseBs), [baseInc, baseBs]);
  const giorniRows = useMemo(() => giorniMediRows(auto), [auto]);
  const previdenzaChecked0 = boolAssumption(p.assumptions, p.forecastYears, "previdenza_scales_with_personnel");
  const indexing = useMemo(
    () => spIndexingOf(p.assumptions, p.forecastYears),
    [p.assumptions, p.forecastYears],
  );
  const minorRows = useMemo(
    () => minorFieldsRows(baseBs, indexing, previdenzaChecked0),
    [baseBs, indexing, previdenzaChecked0],
  );
  const preview = useMemo(() => circolantePreview(baseBs, baseInc, p.preview.data), [baseBs, baseInc, p.preview.data]);

  const tfrChecked = boolAssumption(p.assumptions, p.forecastYears, "tfr_accrual_suspended");

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Giorni medi</CardTitle>
          </CardHeader>
          <CardContent>
            <YearInputTable
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
              rows={giorniRows}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              I giorni del {p.baseYear} sono calcolati sui soli crediti e debiti commerciali, su 360 giorni. Le
              voci non commerciali (tributari, imposte anticipate) non seguono i ricavi.
            </p>
            {/* Un giorno medio dedotto e poi SCARTATO dal motore va detto qui,
                dove i giorni si leggono: altrimenti si guarda un numero che il
                previsionale non ha applicato. */}
            {preview.degenerateDays.length > 0 && (
              <div className="mt-2 space-y-1 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
                {preview.degenerateDays.map((m) => (
                  <div key={m} className="flex gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{m}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Voci minori dell&apos;attivo e del passivo · andamento nel piano</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Che cosa fa ciascuna voce nel piano: la sorpresa vera non e'
                l'assenza dell'aggancio, e' che una voce lasciata vuota resti
                FERMA per tutto il piano senza che nulla lo dica. */}
            <div className="divide-y divide-border/50">
              {minorRows.map((row) => (
                <div key={row.field} className="flex items-center justify-between gap-3 py-1.5">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-foreground">{row.label}</div>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      {row.agganciata
                        ? <Link2 className="h-3 w-3 shrink-0" />
                        : <Minus className="h-3 w-3 shrink-0" />}
                      <span className="truncate">{row.andamento}</span>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-[11px] text-muted-foreground">{row.baseLabel}</div>
                    {row.code !== null && (
                      <Select
                        value={row.driver ?? "costante"}
                        onValueChange={(v) =>
                          p.updateSpIndexing(row.code as string, v === "costante" ? null : (v as SpIndexingDriver))
                        }
                      >
                        <SelectTrigger className="mt-1 h-7 w-[190px] text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="costante">Costante (variazione %)</SelectItem>
                          {DRIVERS.map((d) => (
                            <SelectItem key={d} value={d}>{`Cresce con ${DRIVER_LABELS[d]}`}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <Accordion type="single" collapsible className="mt-3 border-t border-border/50 pt-1">
              <AccordionItem value="voci-minori" className="border-b-0">
                <AccordionTrigger className="text-sm font-medium">Variazione % per anno</AccordionTrigger>
                <AccordionContent>
                  <YearInputTable
                    forecastYears={p.forecastYears}
                    baseYear={p.baseYear}
                    assumptions={p.assumptions}
                    update={p.update}
                    rows={minorRows}
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            <div className="mt-3 space-y-2 border-t border-border/50 pt-3">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="previdenza-scales"
                  checked={previdenzaChecked0}
                  onCheckedChange={(checked) => p.updateAll("previdenza_scales_with_personnel", checked === true)}
                />
                <Label htmlFor="previdenza-scales" className="text-sm font-normal">
                  Debiti previdenziali scalano col costo del personale
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="tfr-suspended"
                  checked={tfrChecked}
                  onCheckedChange={(checked) => p.updateAll("tfr_accrual_suspended", checked === true)}
                />
                <Label htmlFor="tfr-suspended" className="text-sm font-normal">
                  TFR versato a INPS/fondi (accantonamento sospeso)
                </Label>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-4">
        <PreviewPanel
          title="Circolante proiettato"
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
