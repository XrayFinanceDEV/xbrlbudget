"use client";

import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEuro, formatPct } from "@/lib/pratica-format";
import { ALWAYS_SHOW_CODES, DETAIL_PARENTS } from "@/lib/pratica-codes";
import type { IntraYearComparisonItem } from "@/types/api";

// Comparison Table Component
export function ComparisonTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  priorYear,
  showAnnualized,
  showRevenuePct = false,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  priorYear: number | null;
  showAnnualized: boolean;
  showRevenuePct?: boolean;
}) {
  const expectedPct = (periodMonths / 12) * 100;
  const hasPriorYear = priorYear != null && items.some((i) => i.prior_value !== 0);

  // Revenue values for % computation
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const priorRevenue = showRevenuePct && hasPriorYear
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.prior_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Column date labels
  const priorDate = priorYear ? `31/12/${priorYear}` : "";
  const refDate = `31/12/${referenceYear}`;
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue for annualized % computation
  const annualizedRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.annualized_value ?? 0)
    : 0;

  // Column spans for group headers
  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          {hasPriorYear && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
              Storico
            </TableHead>
          )}
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          {showAnnualized && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
              Proiezione
            </TableHead>
          )}
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            {showAnnualized ? "Proiezione / Storico" : "Infrannuale / Storico"}
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          {hasPriorYear && (
            <TableHead className="text-right text-xs font-semibold">{priorDate}</TableHead>
          )}
          {hasPriorYear && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          {showAnnualized && (
            <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          )}
          {showAnnualized && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit",
              "_totale_attivo", "_totale_passivo",
              "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isDetail = item.code in DETAIL_PARENTS;

            // Section headers: bold label spanning all columns
            if (isHeader) {
              // Count total columns: 1 (label) + [colSpan (prior)] + colSpan (ref) + colSpan (partial) + [colSpan (ann)] + 1 (delta)
              const totalCols = 1 + (hasPriorYear ? colSpan : 0) + colSpan + colSpan + (showAnnualized ? colSpan : 0) + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
                  {item.label}
                </TableCell>
                {/* Prior year (anno precedente) */}
                {hasPriorYear && (
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {isPctRow ? formatPct(item.prior_value) : formatEuro(item.prior_value)}
                  </TableCell>
                )}
                {hasPriorYear && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.prior_value, priorRevenue))}
                  </TableCell>
                )}
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {showAnnualized && (
                  <TableCell className="text-right text-sm font-medium">
                    {isNaN(item.annualized_value) ? (
                      <span className="text-muted-foreground">-</span>
                    ) : isPctRow ? "-" : formatEuro(item.annualized_value)}
                  </TableCell>
                )}
                {showAnnualized && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && !isNaN(item.annualized_value) && formatPct(pctOnRevenue(item.annualized_value, annualizedRevenue))}
                  </TableCell>
                )}
                {(() => {
                  const compareValue = showAnnualized ? item.annualized_value : item.partial_value;
                  if (isNaN(compareValue)) {
                    return <TableCell className="text-right text-sm text-muted-foreground">-</TableCell>;
                  }
                  const delta = item.reference_value !== 0
                    ? ((compareValue - item.reference_value) / Math.abs(item.reference_value)) * 100
                    : 0;
                  const isPositive = delta > 1;
                  const isNegative = delta < -1;
                  return (
                    <TableCell className="text-right text-sm">
                      {isPctRow ? (
                        <span className="text-muted-foreground">-</span>
                      ) : (
                        <span
                          className={
                            isPositive
                              ? "text-green-600 dark:text-green-400"
                              : isNegative
                              ? "text-red-600 dark:text-red-400"
                              : "text-muted-foreground"
                          }
                        >
                          {delta > 0 ? "+" : ""}{formatPct(delta)}
                        </span>
                      )}
                    </TableCell>
                  );
                })()}
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

