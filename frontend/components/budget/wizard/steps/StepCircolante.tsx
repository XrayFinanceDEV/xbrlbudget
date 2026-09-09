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
import {
  boolAssumption,
  circolantePreview,
  giorniMediAuto,
  giorniMediRows,
  minorFieldsRows,
} from "@/lib/budget-circolante-step";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable } from "../YearInputTable";

export function StepCircolante(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const baseBs = p.historical[p.baseYear]?.balance;

  const auto = useMemo(() => giorniMediAuto(baseInc, baseBs), [baseInc, baseBs]);
  const giorniRows = useMemo(() => giorniMediRows(auto), [auto]);
  const minorRows = useMemo(() => minorFieldsRows(baseBs), [baseBs]);
  const preview = useMemo(() => circolantePreview(baseBs, baseInc, p.preview.data), [baseBs, baseInc, p.preview.data]);

  const previdenzaChecked = boolAssumption(p.assumptions, p.forecastYears, "previdenza_scales_with_personnel");
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
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Voci minori dell&apos;attivo e del passivo · variazione %</CardTitle>
          </CardHeader>
          <CardContent>
            <Accordion type="single" collapsible>
              <AccordionItem value="voci-minori" className="border-b-0">
                <AccordionTrigger className="text-sm font-medium">Mostra tutte</AccordionTrigger>
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
                  checked={previdenzaChecked}
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
