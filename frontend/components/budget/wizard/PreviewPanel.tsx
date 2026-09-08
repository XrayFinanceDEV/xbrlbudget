"use client";

// Renders the engine-computed preview rows (lib/budget-preview-rows.ts) for
// one wizard step. Presentational only: every number here already came out
// of POST /scenarios/{id}/preview — nothing is derived in this component.
import type { JSX, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { PreviewCell, PreviewRow, PreviewRowKind } from "@/lib/budget-preview-rows";

function rowClass(kind: PreviewRowKind): string {
  switch (kind) {
    case "sub":
      return "text-muted-foreground text-xs";
    case "total":
      return "font-semibold border-t border-border bg-muted/40";
    case "kpi":
      return "font-semibold";
    default:
      return "";
  }
}

function Cell({ cell }: { cell: PreviewCell }): JSX.Element {
  if (cell.value === null) {
    return (
      <td className="whitespace-nowrap px-2 py-1 text-right align-top" title={cell.note}>
        <div className="text-muted-foreground">—</div>
        {cell.note && <div className="text-[11px] italic text-muted-foreground">{cell.note}</div>}
      </td>
    );
  }
  const hasPct = cell.pct !== undefined && cell.pct !== null;
  const hasDays = cell.days !== undefined && cell.days !== null;
  return (
    <td className="whitespace-nowrap px-2 py-1 text-right align-top">
      <div>{formatCurrency(cell.value)}</div>
      {hasPct && <div className="text-[11px] text-muted-foreground">{formatPercentage(cell.pct! / 100)}</div>}
      {!hasPct && hasDays && <div className="text-[11px] text-muted-foreground">{cell.days} gg</div>}
    </td>
  );
}

export function PreviewPanel(props: {
  title: string;
  baseYear: number;
  years: number[];
  rows: PreviewRow[];
  loading: boolean;
  error: string | null;
  children?: ReactNode;
}): JSX.Element {
  const { title, baseYear, years, rows, loading, error, children } = props;

  return (
    <Card className="sticky top-4 border-border/80">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-green-500 dark:bg-green-400" />
          <CardTitle className="text-sm">{title}</CardTitle>
        </div>
        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-2 py-1 text-left font-medium text-muted-foreground"></th>
                <th className="px-2 py-1 text-right font-medium text-muted-foreground">{baseYear}</th>
                {years.map((y) => (
                  <th key={y} className="px-2 py-1 text-right font-medium text-muted-foreground">
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={rowClass(row.kind)}>
                  <td className={cn("px-2 py-1 align-top", row.kind === "sub" && "pl-4")}>{row.label}</td>
                  <Cell cell={row.base} />
                  {row.years.map((c, i) => (
                    <Cell key={i} cell={c} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {error && (
          <div className="mt-2 rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{error}</div>
        )}
        {children}
      </CardContent>
    </Card>
  );
}
