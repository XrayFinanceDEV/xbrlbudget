"use client";

// Per-year editable table shared by the wizard steps: one row per field
// (or a group divider), one column per forecast year, base-year column
// read-only. Mirrors the markup of AssumptionsGrid.tsx but keyed on a
// declarative row list instead of AssumptionRowDef, so a step only supplies
// which fields it edits.
import type { JSX } from "react";
import { FIELD_RULES, parseFieldValue } from "@/lib/budget-field-rules";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { cn } from "@/lib/utils";
import type { StepProps } from "./types";

export interface YearInputRow {
  field: string;
  label: string;
  sub?: string;
  baseLabel: string;
  off?: boolean;
  placeholder?: (year: number) => string;
  group?: never;
}

export interface YearInputGroup {
  group: string;
  swatch?: "fixed" | "variable";
}

function isGroup(row: YearInputRow | YearInputGroup): row is YearInputGroup {
  return typeof (row as YearInputGroup).group === "string";
}

const SWATCH_CLS: Record<"fixed" | "variable", string> = {
  fixed: "bg-blue-500 dark:bg-blue-400",
  variable: "bg-amber-500 dark:bg-amber-400",
};

function valueOf(assumptions: AssumptionsMap, year: number, field: string): string {
  const v = (assumptions[year] as Record<string, unknown> | undefined)?.[field];
  return v === null || v === undefined ? "" : String(v);
}

export function YearInputTable(props: {
  rows: (YearInputRow | YearInputGroup)[];
  forecastYears: number[];
  baseYear: number;
  assumptions: AssumptionsMap;
  update: StepProps["update"];
}): JSX.Element {
  const { rows, forecastYears, baseYear, assumptions, update } = props;
  const colCount = 2 + forecastYears.length;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="px-2 py-1.5 text-left text-xs font-semibold text-foreground">Voce</th>
            <th className="px-2 py-1.5 text-right text-xs font-semibold text-muted-foreground">{baseYear}</th>
            {forecastYears.map((year) => (
              <th key={year} className="px-2 py-1.5 text-right text-xs font-semibold text-primary">
                {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) =>
            isGroup(row) ? (
              <tr key={`group-${row.group}-${i}`} className="bg-muted/30">
                <td colSpan={colCount} className="px-2 py-1.5">
                  <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    {row.swatch && <span className={cn("h-2 w-2 rounded-sm", SWATCH_CLS[row.swatch])} />}
                    {row.group}
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={row.field} className={cn("border-b border-border/50", row.off && "opacity-40")}>
                <td className="px-2 py-1.5 align-top">
                  <div className="text-xs font-medium text-foreground">{row.label}</div>
                  {row.sub && <div className="text-[11px] text-muted-foreground">{row.sub}</div>}
                </td>
                <td className="px-2 py-1.5 text-right align-top text-xs text-muted-foreground">
                  {row.baseLabel}
                </td>
                {forecastYears.map((year) => {
                  const rule = FIELD_RULES[row.field];
                  return (
                    <td key={year} className="px-2 py-1.5 align-top">
                      <input
                        type="number"
                        inputMode="decimal"
                        step={rule?.step ?? "1"}
                        min={rule?.min}
                        max={rule?.max}
                        disabled={row.off}
                        placeholder={row.placeholder?.(year)}
                        value={valueOf(assumptions, year, row.field)}
                        onChange={(e) => update(year, row.field, parseFieldValue(row.field, e.target.value))}
                        className="w-full rounded border border-input bg-transparent px-2 py-1 text-right text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed"
                      />
                    </td>
                  );
                })}
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
