"use client";

// Per-year editable table shared by the wizard steps: one row per field
// (or a group divider), one column per forecast year, base-year column
// read-only. Mirrors the markup of AssumptionsGrid.tsx but keyed on a
// declarative row list instead of AssumptionRowDef, so a step only supplies
// which fields it edits.
import type { JSX } from "react";
import { fieldRule, parseFieldValue } from "@/lib/budget-field-rules";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { yearCellState, type YearCellOff } from "@/lib/budget-year-cell";
import { cn } from "@/lib/utils";
import type { StepProps } from "./types";

/**
 * `off` spegne la riga intera; `offYears` spegne SOLO gli anni elencati e
 * lascia vivi gli altri — un `ce*_override` forza la voce su un anno, non su
 * tutto il piano. Quale delle due valga su una data casella, e con quale
 * spiegazione, lo decide `yearCellState` (`lib/budget-year-cell.ts`) con la
 * sua suite: qui non si decide nulla.
 *
 * `autoYears`/`autoNote` (Task 11, passo Costi) sono un'annotazione diversa da
 * `off`/`offYears`: rispondono a «questa cella segue ancora l'inflazione del
 * passo 1?», non a «e' modificabile?». Una cella puo' essere automatica E
 * disabilitata insieme (un anno forzato in CE Prev. che non e' mai stato
 * scritto a mano): le due si combinano, non si escludono — resta azzurra, ma
 * il titolo del disabilitato vince, perche' spiega perche' non si scrive lì,
 * non perche' si segue l'inflazione.
 */
export interface YearInputRow extends YearCellOff {
  field: string;
  label: string;
  sub?: string;
  baseLabel: string;
  placeholder?: (year: number) => string;
  /** Gli anni ancora «automatici»: la cella prende lo sfondo azzurro, e
   *  `autoNote` come `title` quando l'anno non e' gia' disabilitato. */
  autoYears?: number[];
  autoNote?: string;
  /**
   * Se presente, sostituisce il parsing standard (`parseFieldValue`) per
   * QUESTA riga: riceve la stringa grezza dell'input e decide da se' come
   * interpretarla. Serve alle righe che trattano «vuoto» diversamente da uno
   * zero (`fixed_*_growth_pct` del passo Costi: vuoto torna all'inflazione,
   * zero e' uno zero vero) senza cambiare la regola di campo condivisa
   * (`lib/budget-field-rules.ts`, Task 1 — non e' fra i file di questo
   * task), che per questi due campi non e' `nullable`.
   */
  onRawChange?: (year: number, raw: string) => void;
  /** Lo zero salvato vuol dire «non dichiarato» (`tax_advances_paid`: il
   *  motore ricade sull'automatico): la casella lo mostra vuota, cosi' il
   *  segnaposto dice che cosa si applica davvero, e svuotarla riscrive 0. */
  zeroIsEmpty?: boolean;
  group?: never;
}

export interface YearInputGroup {
  group: string;
  swatch?: "fixed" | "variable";
  /** Sottotitolo del gruppo, reso in piccolo accanto al titolo. */
  sub?: string;
}

function isGroup(row: YearInputRow | YearInputGroup): row is YearInputGroup {
  return typeof (row as YearInputGroup).group === "string";
}

const SWATCH_CLS: Record<"fixed" | "variable", string> = {
  fixed: "bg-blue-500 dark:bg-blue-400",
  variable: "bg-amber-500 dark:bg-amber-400",
};

function valueOf(assumptions: AssumptionsMap, year: number, field: string, zeroIsEmpty = false): string {
  const v = (assumptions[year] as Record<string, unknown> | undefined)?.[field];
  if (v === null || v === undefined) return "";
  return zeroIsEmpty && Number(v) === 0 ? "" : String(v);
}

/** Una casella: la stessa nei due orientamenti della tabella. */
function YearCell({ row, year, assumptions, update }: {
  row: YearInputRow; year: number; assumptions: AssumptionsMap; update: StepProps["update"];
}): JSX.Element {
  const rule = fieldRule(row.field);
  // Il `title` sta anche sul `td`: un input `disabled` non riceve eventi del
  // mouse in tutti i browser, e il tooltip e' l'unica cosa che spiega perche'
  // la casella e' inerte.
  const cell = yearCellState(row, year);
  // L'automatico e' indipendente da `disabled`: una cella puo' essere
  // entrambe (Task 11). Il titolo del disabilitato, quando c'e', vince —
  // spiega perche' non si scrive lì.
  const auto = row.autoYears?.includes(year) ?? false;
  const title = cell.title ?? (auto ? row.autoNote : undefined);
  return (
    <td className="px-2 py-1.5 align-top" title={title}>
      <input
        type="number"
        inputMode="decimal"
        step={rule?.step ?? "1"}
        min={rule?.min}
        max={rule?.max}
        disabled={cell.disabled}
        title={title}
        aria-label={`${row.label} ${year}`}
        placeholder={row.placeholder?.(year)}
        value={valueOf(assumptions, year, row.field, row.zeroIsEmpty)}
        onChange={(e) =>
          row.onRawChange
            ? row.onRawChange(year, e.target.value)
            : row.zeroIsEmpty && e.target.value.trim() === ""
            ? update(year, row.field, 0)
            : update(year, row.field, parseFieldValue(row.field, e.target.value))
        }
        className={cn(
          "w-full rounded border border-input bg-transparent px-2 py-1 text-right text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:border-dashed disabled:bg-muted/50 disabled:text-muted-foreground",
          auto && "bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-100"
        )}
      />
    </td>
  );
}

/**
 * `yearsAsRows`: un anno per riga e una voce per colonna. Serve ai riquadri
 * stretti (la colonna di destra del passo Imposte), dove sei anni affiancati
 * lasciavano caselle troppo piccole per scriverci e schiacciavano le note in
 * una colonna altissima. Le note delle voci (`sub`) vanno sotto la tabella; i
 * divisori di gruppo non hanno senso in questo verso e non si rendono.
 */
export function YearInputTable(props: {
  rows: (YearInputRow | YearInputGroup)[];
  forecastYears: number[];
  baseYear: number;
  assumptions: AssumptionsMap;
  update: StepProps["update"];
  yearsAsRows?: boolean;
}): JSX.Element {
  const { rows, forecastYears, baseYear, assumptions, update } = props;
  const colCount = 2 + forecastYears.length;

  if (props.yearsAsRows) {
    const fields = rows.filter((r): r is YearInputRow => !isGroup(r));
    const note = fields.filter((r) => r.sub);
    return (
      <div className="space-y-2">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-2 py-1.5 text-left text-xs font-semibold text-foreground">Anno</th>
                {fields.map((r) => (
                  <th key={r.field} className="px-2 py-1.5 text-right text-xs font-semibold text-foreground">{r.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-border/50">
                <td className="px-2 py-1.5 text-xs text-muted-foreground">{baseYear}</td>
                {fields.map((r) => (
                  <td key={r.field} className="px-2 py-1.5 text-right text-xs text-muted-foreground">{r.baseLabel}</td>
                ))}
              </tr>
              {forecastYears.map((year) => (
                <tr key={year} className="border-b border-border/50">
                  <td className="px-2 py-1.5 text-xs font-semibold text-primary">{year}</td>
                  {fields.map((r) => (
                    <YearCell key={r.field} row={r} year={year} assumptions={assumptions} update={update} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {note.length > 0 && (
          <dl className="space-y-1 text-[11px] text-muted-foreground">
            {note.map((r) => (
              <div key={r.field}>
                <dt className="inline font-medium text-foreground">{r.label}: </dt>
                <dd className="inline">{r.sub}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    );
  }

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
                    {row.sub && <span className="normal-case tracking-normal text-muted-foreground/80">· {row.sub}</span>}
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
                {forecastYears.map((year) => (
                  <YearCell key={year} row={row} year={year} assumptions={assumptions} update={update} />
                ))}
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
