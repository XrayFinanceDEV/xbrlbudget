"use client";

// Passo 3 del percorso ipotesi: i costi principali (spec 2026-09-08 §4.3).
// Due slider dividono materie prime e servizi fra quota fissa e quota
// variabile, la tabella raccoglie le percentuali di crescita in due gruppi, e
// l'anteprima mostra il totale, di cui fisso e di cui variabile, in % dei
// ricavi — la domanda con cui questo lavoro e' stato chiesto.
//
// Presentazionale: ogni decisione (quale quota mostrare, quali righe si
// spengono, quanto pesano i fissi) sta in lib/budget-costi-step.ts, provata in
// environment: node. E i numeri degli anni previsti vengono dal motore, mai
// ricalcolati qui dallo slider — un solo motore di proiezione, e sta in Python.
import type { JSX } from "react";
import { AlignLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { describeCell } from "@/lib/budget-preview-cell";
import type { PreviewCell, PreviewRow } from "@/lib/budget-preview-rows";
import { previewNotice } from "@/lib/budget-preview-notice";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import {
  alignVariablesToRevenue,
  costiBase,
  costiPreview,
  costiTableRows,
  fixedShareOf,
  isSplitForced,
  splitBaseAmount,
  type FixedShare,
  type FixedShareField,
} from "@/lib/budget-costi-step";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputGroup, type YearInputRow } from "../YearInputTable";
import type { StepProps } from "../types";

const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));
const weightPct = (v: number | null): string => (v === null ? "—" : formatPercentage(v / 100, 1));

function SplitSlider(props: {
  label: string;
  baseAmount: number | null;
  field: FixedShareField;
  share: number;
  uneven: boolean;
  forced: boolean;
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
              forzato in CE Prev.
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
          allinei tutti a quello che imposti. Per differenziarli, usa la riga «quota fissa» della
          tabella.
        </p>
      )}
    </div>
  );
}

function LegendSwatch({ tone, children }: { tone: "fixed" | "variable"; children: string }): JSX.Element {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={
          tone === "fixed"
            ? "h-2 w-2 rounded-sm bg-blue-500 dark:bg-blue-400"
            : "h-2 w-2 rounded-sm bg-amber-500 dark:bg-amber-400"
        }
      />
      {children}
    </span>
  );
}

function PreviewCellTd({ cell }: { cell: PreviewCell }): JSX.Element {
  const { main, sub, note } = describeCell(cell);
  return (
    <td className="whitespace-nowrap px-2 py-1 text-right align-top" title={note ?? undefined}>
      <div className={cell.value === null ? "text-muted-foreground" : undefined}>{main}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </td>
  );
}

/** La sola riga dei fornitori, resa sotto l'occhiello dei giorni di pagamento. */
function FornitoriRow({ row, years }: { row: PreviewRow; years: number[] }): JSX.Element {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <tbody>
          <tr>
            <td className="px-2 py-1 align-top">{row.label}</td>
            <PreviewCellTd cell={row.base} />
            {years.map((y, i) => (
              <PreviewCellTd key={y} cell={row.years[i]} />
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function StepCosti(p: StepProps): JSX.Element {
  const mat: FixedShare = fixedShareOf(p.assumptions, p.forecastYears, "fixed_materials_percentage");
  const serv: FixedShare = fixedShareOf(p.assumptions, p.forecastYears, "fixed_services_percentage");
  const forced = {
    materials: isSplitForced(p.assumptions, p.forecastYears, "ce05_override"),
    services: isSplitForced(p.assumptions, p.forecastYears, "ce06_override"),
  };

  const base = costiBase(p.historical[p.baseYear]?.income);
  const rows: (YearInputRow | YearInputGroup)[] = costiTableRows(base, mat, serv, forced);

  const preview = costiPreview(
    p.historical[p.baseYear]?.income,
    { materials: mat.value, services: serv.value },
    p.preview.data
  );

  const alignToRevenue = () => {
    for (const w of alignVariablesToRevenue(p.assumptions, p.forecastYears)) {
      p.update(w.year, w.field, w.value);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)]">
      <div className="space-y-4">
        <Card className="border-border/80">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Quanto di questi costi e&apos; fisso</CardTitle>
            <p className="text-xs text-muted-foreground">
              La quota fissa segue l&apos;inflazione, la quota variabile segue i ricavi. Lo slider vale
              per tutti gli anni previsti; per differenziarli, la riga «quota fissa» della tabella qui
              sotto si compila anno per anno.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <SplitSlider
              label="Materie prime"
              baseAmount={base.mat}
              field="fixed_materials_percentage"
              share={mat.value}
              uneven={mat.uneven}
              forced={forced.materials}
              onChange={(v) => p.updateAll("fixed_materials_percentage", v)}
            />
            <SplitSlider
              label="Servizi"
              baseAmount={base.serv}
              field="fixed_services_percentage"
              share={serv.value}
              uneven={serv.uneven}
              forced={forced.services}
              onChange={(v) => p.updateAll("fixed_services_percentage", v)}
            />
          </CardContent>
        </Card>

        <Card className="border-border/80">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <LegendSwatch tone="fixed">quota fissa · segue l&apos;inflazione</LegendSwatch>
              <LegendSwatch tone="variable">quota variabile · segue i ricavi</LegendSwatch>
            </div>
            <Button variant="ghost" size="sm" onClick={alignToRevenue} className="shrink-0">
              <AlignLeft className="mr-1.5 h-3.5 w-3.5" />
              Allinea le variabili ai ricavi
            </Button>
          </CardHeader>
          <CardContent className="pt-0">
            <YearInputTable
              rows={rows}
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
            />
          </CardContent>
        </Card>
      </div>

      <PreviewPanel
        title="Costi principali e margine"
        baseYear={p.baseYear}
        years={preview.years}
        rows={preview.tableRows}
        loading={p.preview.loading}
        error={previewNotice(p.preview)}
      >
        {preview.bars.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {preview.bars.map((b) => (
              <div key={b.year}>
                <div className="flex items-baseline justify-between text-[11px] text-muted-foreground">
                  <span>{b.year}</span>
                  <span className="tabular-nums">
                    {euro(b.fixed)} fissi · {euro(b.variable)} variabili
                  </span>
                </div>
                <div className="mt-0.5 flex h-2 overflow-hidden rounded-full bg-muted">
                  <div className="bg-blue-500 dark:bg-blue-400" style={{ flex: b.fixedFlex }} />
                  <div className="bg-amber-500 dark:bg-amber-400" style={{ flex: b.variableFlex }} />
                </div>
              </div>
            ))}
            <p className="pt-0.5 text-[11px] text-muted-foreground">
              peso dei fissi: {weightPct(preview.weight.base)} → {weightPct(preview.weight.last)}
            </p>
          </div>
        )}

        {preview.fornitori && (
          <>
            <Separator className="my-3" />
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              {preview.dpo === null
                ? `CON I GIORNI DI PAGAMENTO FERMI AL ${p.baseYear}`
                : `CON I GIORNI DI PAGAMENTO FERMI AL ${p.baseYear} (${preview.dpo} GG)`}
            </p>
            <FornitoriRow row={preview.fornitori} years={preview.years} />
            <p className="mt-1 px-2 text-[11px] text-muted-foreground">
              I giorni medi si regolano al passo 5, Capitale circolante. Qui restano quelli dell&apos;ultimo
              bilancio per non mescolare le ipotesi.
            </p>
          </>
        )}
      </PreviewPanel>
    </div>
  );
}
