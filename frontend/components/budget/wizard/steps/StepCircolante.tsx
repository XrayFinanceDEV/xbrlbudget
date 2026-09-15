"use client";

// Passo 4 del wizard ipotesi (spec 2026-09-15 §4.4): i giorni medi di
// incasso/magazzino/pagamento — dove il proprietario vuole che si aggiusti
// il circolante "verso la fine del workflow" — e l'avviso quando i debiti
// verso fornitori dell'anno base sono zero (decisione 8: i giorni di
// pagamento non si possono calcolare, quasi sempre una riclassifica). Le
// voci minori dello SP e i driver di volume (`sp_indexing`) sono passate al
// passo 6 «Patrimoniale piano» (Task 15): `lib/budget-circolante-step.ts`
// resta il posto dove vivono, non tocca a questo passo renderle piu'.
//
// Presentazionale: ogni decisione (quale giorno "auto" mostrare, quali anni
// ha davvero prodotto il motore, l'avviso fornitori) sta in lib/, provata in
// environment: node. I tre campi giorni sono annullabili: vuoto significa
// "usa il valore derivato dall'anno base", mai zero giorni — la distinzione
// la fa il segnaposto `auto N`, mai un placeholder statico.
import type { JSX } from "react";
import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { circolantePreview, giorniMediAuto, giorniMediRows } from "@/lib/budget-circolante-step";
import { fornitoriZeroAvviso } from "@/lib/budget-fornitori-zero";
import { AlertTriangle } from "lucide-react";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable } from "../YearInputTable";

export function StepCircolante(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const baseBs = p.historical[p.baseYear]?.balance;

  const auto = useMemo(() => giorniMediAuto(baseInc, baseBs), [baseInc, baseBs]);
  const giorniRows = useMemo(() => giorniMediRows(auto), [auto]);
  const avviso = useMemo(() => fornitoriZeroAvviso(p.baseYear, baseBs, baseInc), [p.baseYear, baseBs, baseInc]);
  const preview = useMemo(() => circolantePreview(baseBs, baseInc, p.preview.data), [baseBs, baseInc, p.preview.data]);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-5">
        {avviso && (
          <div className="flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <b>{avviso.titolo}</b>
              <div className="text-xs">{avviso.dettaglio}</div>
            </div>
          </div>
        )}
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
              I giorni del {p.baseYear} sono calcolati sui soli crediti verso clienti e debiti verso fornitori, su
              360 giorni. Crediti e debiti del {p.baseYear} si chiudono nel {p.baseYear + 1} (passo 5): questi
              giorni generano quelli nuovi.
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
