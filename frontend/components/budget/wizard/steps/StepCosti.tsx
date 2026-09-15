"use client";

// Passo 3 del percorso ipotesi: Costi (spec 2026-09-15 §4.3, giro di rilievi del 14/09).
// Due slider dividono materie prime e servizi fra quota fissa e quota variabile (invariati);
// la tabella raccoglie solo le percentuali di crescita che restano da scrivere a mano — la
// parte fissa (precompilata con l'inflazione del passo 1) e tre ipotesi manuali (personale,
// godimento beni di terzi, oneri diversi di gestione, spostata qui da «Altre voci CE»). La
// parte variabile non ha piu' una riga: segue i ricavi del passo 2 per costruzione (Task 10).
//
// Presentazionale: ogni decisione (quale quota mostrare, quali righe si spengono, quali anni
// sono ancora automatici) sta in lib/budget-costi-step.ts, provata in environment: node. Il
// pareggio sul MOL (lib/budget-pareggio.ts) e il CE fino all'ante imposte
// (lib/budget-preview-rows.ts) leggono solo cio' che il motore ha gia' dichiarato in
// `details` — un solo motore di proiezione, e sta in Python.
import { useMemo, type JSX } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { euro, pct1 } from "@/lib/budget-format";
import { inflazioneOf } from "@/lib/budget-inflazione";
import { previewNotice } from "@/lib/budget-preview-notice";
import { rowsCeAnteImposte, rowsCosti } from "@/lib/budget-preview-rows";
import { pareggioBarre, pareggioFormula, rowsPareggio } from "@/lib/budget-pareggio";
import {
  autoYearsOf,
  calcolateAltrove,
  costiBase,
  costiTableRows,
  fixedGrowthChange,
  fixedShareOf,
  forcedNote,
  forcedSplitYears,
  splitBaseAmount,
  type FixedShare,
  type FixedShareField,
  type ForcedSplit,
} from "@/lib/budget-costi-step";
import { cn } from "@/lib/utils";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputGroup, type YearInputRow } from "../YearInputTable";
import type { StepProps } from "../types";

function SplitSlider(props: {
  label: string;
  baseAmount: number | null;
  field: FixedShareField;
  share: number;
  uneven: boolean;
  /** Il testo del badge, che dice ANCHE in quali anni e' forzato; `null` =
   *  nessun anno forzato, nessun badge (deciso in `lib/budget-costi-step`). */
  forced: string | null;
  onChange: (v: number) => void;
}): JSX.Element {
  const { label, baseAmount, field, share, uneven, forced, onChange } = props;
  const { fixed, variable } = splitBaseAmount(baseAmount, share);

  return (
    <div className="border-b py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-baseline gap-2 font-medium">
          {label}
          {forced && (
            <Badge variant="outline" className="font-normal text-amber-700 dark:text-amber-300">
              {forced}
            </Badge>
          )}
        </span>
        <span className="tabular-nums text-muted-foreground">{euro(baseAmount)}</span>
      </div>
      <div className="mt-1.5 grid grid-cols-[1fr_92px] items-center gap-3">
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={share}
          aria-label={`Quota fissa ${label}`}
          className="w-full accent-blue-500"
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <div className="flex items-center gap-1">
          <Input
            type="number"
            min={0}
            max={100}
            className="w-16 text-right"
            value={share}
            onChange={(e) => onChange(parseFieldValue(field, e.target.value) ?? 0)}
          />
          <span className="text-[11px] text-muted-foreground">% fissa</span>
        </div>
      </div>
      <div className="mt-2 flex h-7 overflow-hidden rounded text-xs font-medium">
        <div
          className="flex items-center justify-center bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100"
          style={{ flex: share }}
        >
          {share > 12 && `Fissa · ${euro(fixed)}`}
        </div>
        <div
          className="flex items-center justify-center bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100"
          style={{ flex: 100 - share }}
        >
          {share < 88 && `Variabile · ${euro(variable)}`}
        </div>
      </div>
      {uneven && (
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
          Valori diversi per anno: muovendo lo slider — o digitando nella casella qui accanto — li
          allinei tutti a quello che imposti.
        </p>
      )}
    </div>
  );
}

function LegendSwatch({ tone, children }: { tone: "fixed" | "variable"; children: string }): JSX.Element {
  return (
    <span className="flex items-start gap-1.5">
      <span
        className={cn(
          "mt-1 h-2 w-2 shrink-0 rounded-sm",
          tone === "fixed" ? "bg-blue-500 dark:bg-blue-400" : "bg-amber-500 dark:bg-amber-400"
        )}
      />
      {children}
    </span>
  );
}

/** Una riga del mini grafico del pareggio: la traccia dei ricavi, la tacca del pareggio e il
 *  segmento del margine di sicurezza — verde sopra il pareggio, rosso sotto. Un anno `nd`
 *  (parte fissa/variabile non definita) non ha barra: solo il trattino a destra. */
function BepRow({ b }: { b: ReturnType<typeof pareggioBarre>[number] }): JSX.Element {
  const lo = Math.min(b.margineDaPct, b.margineAPct);
  const hi = Math.max(b.margineDaPct, b.margineAPct);
  const titolo = b.nd
    ? "Non definito: materie prime o servizi forzati in CE Prev."
    : `${b.year}: ricavi ${pct1(b.ricaviPct)} della scala · pareggio a ${pct1(b.pareggioPct)} · margine di sicurezza ${euro(b.margine)} (${pct1(b.marginePct)})`;
  return (
    <div className="grid grid-cols-[38px_1fr_60px] items-center gap-2.5 text-[11px]" title={titolo}>
      <span className="text-muted-foreground">{b.year}</span>
      <div className="relative h-[18px] overflow-hidden rounded-r bg-muted">
        <div className="absolute inset-y-0 left-0 rounded-r bg-border" style={{ width: `${b.ricaviPct}%` }} />
        {!b.nd && (
          <>
            <div
              className={cn(
                "absolute top-[3px] bottom-[3px] rounded-sm",
                b.ok ? "bg-green-500 dark:bg-green-400" : "bg-red-400/70 dark:bg-red-500/60"
              )}
              style={{ left: `${lo}%`, width: `${Math.max(0, hi - lo)}%` }}
            />
            <div className="absolute -top-[3px] -bottom-[3px] w-[2px] bg-foreground" style={{ left: `${b.pareggioPct}%` }} />
          </>
        )}
      </div>
      <span className="text-right font-semibold tabular-nums">{b.nd ? "—" : pct1(b.marginePct)}</span>
    </div>
  );
}

export function StepCosti(p: StepProps): JSX.Element {
  const mat: FixedShare = fixedShareOf(p.assumptions, p.forecastYears, "fixed_materials_percentage");
  const serv: FixedShare = fixedShareOf(p.assumptions, p.forecastYears, "fixed_services_percentage");
  // Quali ANNI CE Prev. forza, non «se» li forza: il badge dice dove e' vero,
  // e le sole caselle di quegli anni si spengono.
  const forced: ForcedSplit = {
    years: p.forecastYears,
    materials: forcedSplitYears(p.assumptions, p.forecastYears, "ce05_override"),
    services: forcedSplitYears(p.assumptions, p.forecastYears, "ce06_override"),
  };
  const forcedBadge = {
    materials: forcedNote(forced.materials, forced.years),
    services: forcedNote(forced.services, forced.years),
  };
  const auto = {
    materials: autoYearsOf(p.assumptions, p.forecastYears, "fixed_materials_growth_auto"),
    services: autoYearsOf(p.assumptions, p.forecastYears, "fixed_services_growth_auto"),
  };
  const inflazione = inflazioneOf(p.assumptions, p.forecastYears);

  const baseInc = p.historical[p.baseYear]?.income;
  const base = costiBase(baseInc);

  // Una casella «Parte fissa» vuota torna all'inflazione (auto=true); un numero — anche
  // uno zero — resta suo (auto=false). `YearInputTable` chiama questo handler con la
  // stringa grezza al posto del parsing standard, perche' `fixed_*_growth_pct` non e'
  // `nullable` in `lib/budget-field-rules.ts` (Task 1, non fra i file di questo task) e
  // «vuoto» deve restare distinto da «zero scritto a mano».
  const onFixedRawChange = (field: "fixed_materials_growth_pct" | "fixed_services_growth_pct") =>
    (year: number, raw: string) => {
      const t = raw.trim();
      const parsed = t === "" ? null : parseFieldValue(field, raw);
      const { value, auto: isAuto } = fixedGrowthChange(parsed, inflazione);
      p.update(year, field, value);
      p.update(year, field === "fixed_materials_growth_pct" ? "fixed_materials_growth_auto" : "fixed_services_growth_auto", isAuto);
    };

  const rows: (YearInputRow | YearInputGroup)[] = useMemo(
    () =>
      costiTableRows(base, mat, serv, forced, auto).map((r): YearInputRow | YearInputGroup => {
        if (!("field" in r)) return r;
        if (r.field === "fixed_materials_growth_pct" || r.field === "fixed_services_growth_pct") {
          return { ...r, onRawChange: onFixedRawChange(r.field) };
        }
        return r;
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, mat.value, mat.uneven, serv.value, serv.uneven, forced.materials, forced.services, auto.materials, auto.services, inflazione]
  );

  const riallineaAllInflazione = () => {
    for (const y of p.forecastYears) {
      p.update(y, "fixed_materials_growth_pct", inflazione);
      p.update(y, "fixed_materials_growth_auto", true);
      p.update(y, "fixed_services_growth_pct", inflazione);
      p.update(y, "fixed_services_growth_auto", true);
    }
  };

  // Gli anni delle colonne sono quelli che il motore ha davvero prodotto, non quelli
  // richiesti: se si e' fermato a meta' (fabbisogno scoperto) le intestazioni non
  // restano senza celle sotto (stessa convenzione degli altri passi).
  const previewYears = useMemo(() => p.preview.data?.forecast_years ?? [], [p.preview.data]);
  const costiRows = useMemo(
    () => (baseInc ? rowsCosti(baseInc, { materials: mat.value, services: serv.value }, previewYears) : []),
    [baseInc, mat.value, serv.value, previewYears]
  );
  const pareggioRows = useMemo(() => rowsPareggio(previewYears), [previewYears]);
  const barre = useMemo(() => pareggioBarre(previewYears), [previewYears]);
  const formula = useMemo(() => pareggioFormula(previewYears[0]), [previewYears]);
  const ceRows = useMemo(
    () => (baseInc ? rowsCeAnteImposte(baseInc, { materials: mat.value, services: serv.value }, previewYears) : []),
    [baseInc, mat.value, serv.value, previewYears]
  );
  const calcolate = calcolateAltrove(p.baseYear);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-4">
        <Card className="border-border/80">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Quanto è fisso</CardTitle>
            <p className="text-xs text-muted-foreground">
              Al variare del fatturato, quale parte resta costante?
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <SplitSlider
              label="Materie prime"
              baseAmount={base.mat}
              field="fixed_materials_percentage"
              share={mat.value}
              uneven={mat.uneven}
              forced={forcedBadge.materials}
              onChange={(v) => p.updateAll("fixed_materials_percentage", v)}
            />
            <SplitSlider
              label="Servizi"
              baseAmount={base.serv}
              field="fixed_services_percentage"
              share={serv.value}
              uneven={serv.uneven}
              forced={forcedBadge.services}
              onChange={(v) => p.updateAll("fixed_services_percentage", v)}
            />
            <div className="mt-2.5 flex flex-col gap-1.5">
              <LegendSwatch tone="variable">
                la parte variabile segue il fatturato in proporzione: nessuna ipotesi da inserire
              </LegendSwatch>
              <LegendSwatch tone="fixed">
                la parte fissa parte dall&apos;inflazione, correggibile qui sotto
              </LegendSwatch>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Come si muovono i costi</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <YearInputTable
              rows={rows}
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
            />
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>
                Le caselle azzurre seguono ancora l&apos;inflazione: cambiano se la cambi al passo 1.
                Una casella che hai scritto resta tua; svuotala per tornare all&apos;inflazione.
              </span>
              <Button variant="outline" size="sm" onClick={riallineaAllInflazione} className="shrink-0">
                Riallinea all&apos;inflazione
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-muted/20">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-2">
            <CardTitle className="text-sm">Calcolate in altri passi</CardTitle>
            <Badge variant="outline" className="font-normal">automatico</Badge>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {calcolate.map((c) => (
              <div key={c.label} className="flex items-center justify-between gap-3 border-b py-1.5 last:border-b-0">
                <div>
                  <div className="text-xs font-medium text-foreground">{c.label}</div>
                  <div className="text-[11px] text-muted-foreground">{c.small}</div>
                </div>
                <Badge variant="outline" className="shrink-0 font-normal">{c.passo}</Badge>
              </div>
            ))}
            <p className="pt-1 text-[11px] text-muted-foreground">
              Un valore forzato a mano in CE Prev. vince su queste regole finché non lo azzeri dal
              dialogo Ricalcola.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-4 space-y-4">
        <PreviewPanel
          title="Costi e margine"
          baseYear={p.baseYear}
          years={previewYears.map((y) => y.year)}
          rows={costiRows}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        >
          <p className="mt-1 text-[11px] text-muted-foreground">
            Le percentuali in tabella sono sui ricavi dell&apos;anno.
          </p>
        </PreviewPanel>

        <PreviewPanel
          title="Punto di pareggio sul MOL"
          baseYear={p.baseYear}
          years={previewYears.map((y) => y.year)}
          rows={pareggioRows}
          loading={p.preview.loading}
          error={null}
        >
          <div className="space-y-1.5">
            {barre.map((b) => (
              <BepRow key={b.year} b={b} />
            ))}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3.5 gap-y-1 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-border" />ricavi</span>
            <span className="flex items-center gap-1"><span className="h-2 w-[2px] bg-foreground" />fatturato di pareggio</span>
            <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-green-500 dark:bg-green-400" />margine di sicurezza</span>
            <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-red-400/70 dark:bg-red-500/60" />ricavi sotto il pareggio</span>
          </div>
          {formula && (
            <div className="mt-3 space-y-1 rounded-md bg-muted/40 p-2.5 text-[11px]">
              <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                Come si calcola · {formula.anno}
              </p>
              {formula.righe.map((r) => (
                <div key={r.testo} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <span className="text-muted-foreground">{r.testo}</span>
                  <span className="font-mono tabular-nums">{r.calcolo}</span>
                </div>
              ))}
            </div>
          )}
        </PreviewPanel>

        <PreviewPanel
          title="Conto economico fino all'ante imposte"
          baseYear={p.baseYear}
          years={previewYears.map((y) => y.year)}
          rows={ceRows}
          loading={p.preview.loading}
          error={null}
        />
      </div>
    </div>
  );
}
