"use client";

// Passo 1 del wizard delle ipotesi (Task 11 §1): informazioni dello scenario
// e punto di partenza (inflazione + tendenza storica). Nessuna chiamata di
// anteprima qui — a differenza degli altri sei passi, che leggono
// `p.preview` — perche' non c'e' nulla che il motore debba proiettare: la
// scheda a destra ricapitola il bilancio storico gia' caricato
// (`rowsAnnoBase`, lib/budget-preview-rows.ts).
import { useEffect, useMemo, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { blendedRate, calculateTrend, shouldSeedTrend, TREND_ITEMS, trendAssumptions } from "@/lib/budget-trend";
import { rowsAnnoBase } from "@/lib/budget-preview-rows";
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
  inflation: number;
  setInflation: (v: number) => void;
}

/** Applica la tendenza storica su tutto l'orizzonte: TREND_ITEMS x forecastYears,
 *  ogni campo scritto con blendedRate (spec 2026-09-08 §4.1). Chiamata sia
 *  dal seed automatico (una tantum, scenario nuovo) sia dal pulsante
 *  "Riparti dalla tendenza". */
function applyTrendToAssumptions(
  historicalYears: number[],
  forecastYears: number[],
  historical: StepProps["historical"],
  inflation: number,
  update: StepProps["update"],
) {
  const t = trendAssumptions(historicalYears, forecastYears, historical, inflation);
  for (const [year, fields] of Object.entries(t))
    for (const [f, v] of Object.entries(fields)) update(Number(year), f, v);
}

export function StepScenario(props: StepScenarioProps) {
  const {
    baseYear, forecastYears, historical, historicalYears, update,
    name, setName, description, setDescription, isActive, setIsActive,
    numYears, setNumYears, notaAnnoBase, isNew, inflation, setInflation,
  } = props;

  // Il campo tiene il testo battuto finche' ha il fuoco (stessa logica
  // anti-rimbalzo di app/budget/page.tsx: rimandare `numYears` a ogni tasto
  // faceva rimbalzare il valore, vedi lib/budget-horizon.ts).
  const [testoAnni, setTestoAnni] = useState<string | null>(null);

  // Scenario nuovo: precompila UNA volta, appena idratato — e «idratato» vuol
  // dire che i dati storici sono ARRIVATI, non che l'elenco degli anni e' lungo
  // due. La decisione sta in `shouldSeedTrend` (lib/budget-trend.ts), col suo
  // test; qui resta il solo one-shot, che scatta quando il seed avviene davvero.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || !shouldSeedTrend(isNew, historicalYears, historical)) return;
    seeded.current = true;
    applyTrendToAssumptions(historicalYears, forecastYears, historical, inflation, update);
  }, [isNew, historicalYears, forecastYears, historical, inflation, update]);

  const hasTwoYears = historicalYears.length >= 2;
  const year1 = hasTwoYears ? historicalYears[historicalYears.length - 2] : 0;
  const year2 = hasTwoYears ? historicalYears[historicalYears.length - 1] : 0;
  const n = forecastYears.length;
  const trendRows = useMemo(
    () => TREND_ITEMS.map((item) => {
      const trend = hasTwoYears ? calculateTrend(historical, year1, year2, item.getValue) : null;
      const rates = forecastYears.map((_, i) => blendedRate(trend, inflation, i, n));
      return { ...item, trend, rates };
    }),
    [hasTwoYears, historical, year1, year2, forecastYears, inflation, n],
  );

  const annoBaseRows = useMemo(() => rowsAnnoBase(baseYear, historicalYears, historical), [baseYear, historicalYears, historical]);
  const anniPrecedenti = useMemo(() => historicalYears.filter((y) => y !== baseYear), [historicalYears, baseYear]);

  const riapplicaTendenza = () => {
    applyTrendToAssumptions(historicalYears, forecastYears, historical, inflation, update);
    toast.success("Ipotesi applicate con successo");
  };

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
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Punto di partenza</CardTitle>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <RotateCcw className="h-3.5 w-3.5" />
                  Riparti dalla tendenza
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Riapplicare la tendenza storica?</AlertDialogTitle>
                  <AlertDialogDescription asChild>
                    <div>
                      Sovrascrive le ipotesi correnti su tutto l&apos;orizzonte per queste voci:
                      <ul className="mt-2 list-disc pl-5">
                        {TREND_ITEMS.map((item) => <li key={item.label}>{item.label}</li>)}
                      </ul>
                    </div>
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Annulla</AlertDialogCancel>
                  <AlertDialogAction onClick={riapplicaTendenza}>Applica</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Label htmlFor="wiz-inflation" className="text-xs font-medium whitespace-nowrap">Inflazione attesa</Label>
              <Input
                id="wiz-inflation"
                type="number"
                step="0.1"
                min="-10"
                max="50"
                value={inflation}
                onChange={(e) => setInflation(parseFloat(e.target.value) || 0)}
                className="w-24"
              />
              <span className="text-xs text-muted-foreground">%</span>
            </div>
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
                    <th className="px-2 py-1.5 text-center font-semibold text-muted-foreground">Trend storico</th>
                    {forecastYears.map((year) => (
                      <th key={year} className="px-2 py-1.5 text-center font-semibold text-primary">{year}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trendRows.map((r) => (
                    <tr key={r.label} className="border-b border-border/50">
                      <td className="px-2 py-1.5 font-medium text-foreground">{r.label}</td>
                      <td className="px-2 py-1.5 text-center text-muted-foreground">
                        {r.trend !== null ? `${r.trend >= 0 ? "+" : ""}${r.trend.toFixed(1)}%` : "—"}
                      </td>
                      {r.rates.map((rate, i) => (
                        <td key={i} className="px-2 py-1.5 text-center font-medium text-primary">{rate.toFixed(1)}%</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-4">
        <PreviewPanel
          title={`Bilancio ${baseYear} · anno base`}
          baseYear={baseYear}
          years={anniPrecedenti}
          rows={annoBaseRows}
          loading={false}
          error={null}
        >
          {anniPrecedenti.length > 0 && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Le colonne a destra sono gli anni storici precedenti, non anni di previsione.
            </p>
          )}
        </PreviewPanel>
      </div>
    </div>
  );
}
