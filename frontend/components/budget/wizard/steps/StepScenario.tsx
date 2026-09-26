"use client";

// Passo 1 del wizard delle ipotesi (Task 11 §1): informazioni dello scenario
// e punto di partenza (inflazione + tendenza storica). Nessuna chiamata di
// anteprima qui — a differenza degli altri sei passi, che leggono
// `p.preview` — perche' non c'e' nulla che il motore debba proiettare: la
// scheda a destra ricapitola il bilancio storico gia' caricato
// (`rowsAnnoBase`, lib/budget-preview-rows.ts).
//
// L'inflazione attesa si SALVA (`inflation_pct`, Task 10, spec 2026-09-15
// §4.1): niente piu' stato locale, si legge da `assumptions` con
// `inflazioneOf` e si scrive con `updateAll("inflation_pct", v)`, intercettato
// nell'hook (`use-scenario-assumptions.ts`) per riallineare anche le caselle
// automatiche della parte fissa del passo 3. Il seed dalla tendenza storica
// e' sparito (decisione 3): la tabella resta come riferimento in sola
// lettura, senza pulsante di ripristino.
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { calculateTrend, TREND_ITEMS } from "@/lib/budget-trend";
import { inflazioneOf } from "@/lib/budget-inflazione";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { rowsAnnoBase } from "@/lib/budget-preview-rows";
import { PercentInput } from "@/components/budget/PercentInput";
import { PreviewPanel } from "../PreviewPanel";
import type { StepProps } from "../types";

export interface StepScenarioProps extends StepProps {
  name: string;
  setName: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  isActive: boolean;
  setIsActive: (v: boolean) => void;
  numYears: number;
  setNumYears: (v: number) => void;
  notaAnnoBase: string | null;
  isNew: boolean;
}

export function StepScenario(props: StepScenarioProps) {
  const {
    baseYear, forecastYears, historical, historicalYears, assumptions, updateAll,
    name, setName, description, setDescription, isActive, setIsActive,
    numYears, setNumYears, notaAnnoBase,
  } = props;

  // Il campo tiene il testo battuto finche' ha il fuoco (stessa logica
  // anti-rimbalzo di app/budget/page.tsx: rimandare `numYears` a ogni tasto
  // faceva rimbalzare il valore, vedi lib/budget-horizon.ts).
  const [testoAnni, setTestoAnni] = useState<string | null>(null);

  const inflazione = inflazioneOf(assumptions, forecastYears);

  const hasTwoYears = historicalYears.length >= 2;
  const year1 = hasTwoYears ? historicalYears[historicalYears.length - 2] : 0;
  const year2 = hasTwoYears ? historicalYears[historicalYears.length - 1] : 0;
  const trendRows = useMemo(
    () => TREND_ITEMS.map((item) => ({
      ...item,
      trend: hasTwoYears ? calculateTrend(historical, year1, year2, item.getValue) : null,
    })),
    [hasTwoYears, historical, year1, year2],
  );

  const annoBaseRows = useMemo(() => rowsAnnoBase(baseYear, historicalYears, historical), [baseYear, historicalYears, historical]);
  const anniPrecedenti = useMemo(() => historicalYears.filter((y) => y !== baseYear), [historicalYears, baseYear]);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-5">
        <Card>
          <CardHeader><CardTitle className="text-base">Informazioni</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wiz-scenario-name">Nome scenario</Label>
              <Input
                id="wiz-scenario-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="es. Budget 2026-2028"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="wiz-scenario-base-year">Anno base</Label>
              <Input id="wiz-scenario-base-year" disabled value={`${baseYear} · bilancio annuale importato`} />
              {notaAnnoBase && <p className="text-xs text-muted-foreground">{notaAnnoBase}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="wiz-scenario-description">Descrizione</Label>
              <Textarea
                id="wiz-scenario-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descrizione dello scenario..."
                rows={2}
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox id="wiz-scenario-active" checked={isActive} onCheckedChange={(c) => setIsActive(c === true)} />
              <Label htmlFor="wiz-scenario-active" className="text-sm font-normal">Scenario attivo</Label>
            </div>
            <div className="space-y-2 border-t border-border pt-4">
              <Label>Orizzonte di piano</Label>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant={numYears === 3 ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setTestoAnni(null); setNumYears(3); }}
                >
                  3 anni
                </Button>
                <Button
                  type="button"
                  variant={numYears === 5 ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setTestoAnni(null); setNumYears(5); }}
                >
                  5 anni
                </Button>
                <Input
                  id="wiz-scenario-num-years"
                  type="number"
                  min={1}
                  max={5}
                  // Il campo tiene il testo battuto finche' ha il fuoco: vedi
                  // il commento sopra `testoAnni`.
                  value={testoAnni ?? String(numYears)}
                  onChange={(e) => {
                    const grezzo = e.target.value;
                    setTestoAnni(grezzo);
                    const n2 = parseInt(grezzo, 10);
                    if (n2 >= 1 && n2 <= 5) setNumYears(n2);
                  }}
                  onBlur={() => setTestoAnni(null)}
                  className="w-20"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Se accorci l&apos;orizzonte, al primo «Salva e calcola previsionale» le ipotesi degli anni
                tolti vengono cancellate, insieme ai loro anni di proiezione.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Punto di partenza</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Label htmlFor="wiz-inflation" className="text-xs font-medium whitespace-nowrap">Inflazione attesa</Label>
              <PercentInput
                id="wiz-inflation"
                value={inflazione}
                onRawChange={(raw) => updateAll("inflation_pct", parseFieldValue("inflation_pct", raw) ?? 0)}
                allowNegative
                className="flex h-10 w-24 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <span className="text-xs text-muted-foreground">%</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Precompila la crescita della parte fissa di materie prime e servizi (passo 3), dove puoi
              correggerla anno per anno. L&apos;inflazione non tocca i ricavi: le ipotesi sul fatturato le
              scrivi al passo 2, partendo da 0.
            </p>
            {!hasTwoYears && (
              <p className="text-xs text-muted-foreground">
                Serve almeno 2 anni storici per calcolare il trend. Verranno usati i valori di inflazione.
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-2 py-1.5 text-left font-semibold text-foreground">Voce</th>
                    <th className="px-2 py-1.5 text-center font-semibold text-muted-foreground">
                      {hasTwoYears ? `Tendenza ${year1}-${year2}` : "Tendenza storica"}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {trendRows.map((r) => (
                    <tr key={r.label} className="border-b border-border/50">
                      <td className="px-2 py-1.5 font-medium text-foreground">{r.label}</td>
                      <td className="px-2 py-1.5 text-center text-muted-foreground">
                        {r.trend !== null ? `${r.trend >= 0 ? "+" : ""}${r.trend.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Solo per riferimento: il piano parte da 0 al passo 2.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-4">
        <PreviewPanel
          title={`Bilancio ${baseYear} · anno base`}
          baseYear={baseYear}
          years={anniPrecedenti}
          rows={annoBaseRows}
          baseYearLast
          loading={false}
          error={null}
        >
          {anniPrecedenti.length > 0 && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Gli anni storici sono in ordine cronologico; non sono anni di previsione.
            </p>
          )}
        </PreviewPanel>
      </div>
    </div>
  );
}
