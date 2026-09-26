"use client";

// Renders the engine-computed preview rows (lib/budget-preview-rows.ts) for
// one wizard step. Presentational only: every number here already came out
// of POST /scenarios/{id}/preview — nothing is derived in this component.
// What to show for a cell (value vs "—", pct vs days, the note) and the
// per-kind row class are decided in lib/budget-preview-cell.ts, testable
// without a DOM.
import type { JSX, ReactNode } from "react";
import { Info, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { describeCell, rowClass } from "@/lib/budget-preview-cell";
import type { PreviewCell, PreviewRow } from "@/lib/budget-preview-rows";

function Cell({ cell }: { cell: PreviewCell }): JSX.Element {
  const { main, sub, note } = describeCell(cell);
  return (
    <td className="whitespace-nowrap px-2 py-1 text-right align-top" title={note ?? undefined}>
      <div className={cell.value === null ? "text-muted-foreground" : undefined}>{main}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
      {note && <div className="text-[11px] italic text-muted-foreground">{note}</div>}
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
  baseYearLast?: boolean;
  children?: ReactNode;
}): JSX.Element {
  const { title, baseYear, years, rows, loading, error, baseYearLast = false, children } = props;
  const columns = baseYearLast
    ? [...years.map((year, index) => ({ year, index })), { year: baseYear, index: -1 }]
    : [{ year: baseYear, index: -1 }, ...years.map((year, index) => ({ year, index }))];

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
        <TooltipProvider>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-2 py-1 text-left font-medium text-muted-foreground"></th>
                {columns.map(({ year }) => (
                  <th key={year} className="px-2 py-1 text-right font-medium text-muted-foreground">
                    {year}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={rowClass(row.kind)}>
                  <td className={cn("px-2 py-1 align-top", row.kind === "sub" && "pl-4")}>
                    <span className="inline-flex items-center gap-1">
                      {row.label}
                      {row.hint && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button type="button" aria-label={`Spiegazione: ${row.label}`} className="inline-flex text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                              <Info className="h-3 w-3" aria-hidden="true" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>{row.hint}</TooltipContent>
                        </Tooltip>
                      )}
                    </span>
                  </td>
                  {columns.map(({ year, index }) => (
                    <Cell key={year} cell={index === -1 ? row.base : row.years[index]} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </TooltipProvider>
        {error && (
          <div className="mt-2 rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{error}</div>
        )}
        {children}
      </CardContent>
    </Card>
  );
}
