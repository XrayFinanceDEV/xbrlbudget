"use client";

// Passo 6 del wizard ipotesi: pregresso e nuovo (spec 2026-09-08 §4.6,
// task-14-brief.md). Presentazionale: ogni decisione — i saldi dell'anno
// base, quale anno mostrare per un campo scritto con updateAll, quali anni
// ha davvero prodotto il motore — sta in lib/budget-pregresso-step.ts,
// provata in environment: node.
//
// Un solo motore di proiezione, e sta in Python: debito, cassa e PFN
// previsti vengono da rowsPregressoNuovo (via pregressoPreview), mai
// ricalcolati qui. FinancingLoansGrid e TaxTemporaryDifferencesGrid
// (Task 7) si riusano cosi' come sono: non sono duplicate qui dentro.
import type { JSX, ReactNode } from "react";
import { useMemo } from "react";
import { AlertTriangle, Check } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { FinancingLoansGrid } from "@/components/budget/FinancingLoansGrid";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { formatCurrency } from "@/lib/formatters";
import { boolAssumption, pregressoBase, pregressoPreview, singleYearValue } from "@/lib/budget-pregresso-step";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";

const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));

/** Riga «etichetta / nota piccola» a sinistra, controllo a destra — lo
 *  schema di Card «Calcolate dal piano» di StepAltreVociCE, qui con un
 *  controllo interattivo invece di un valore. */
function ScheduleRow({ label, small, children }: { label: string; small: string; children: ReactNode }): JSX.Element {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 py-2.5 last:border-b-0">
      <div>
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="text-xs text-muted-foreground">{small}</div>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** «rimborso in [n] anni», scritto su tutti gli anni con updateAll. */
function RepaymentInput({ field, value, uneven, onChange }: {
  field: string; value: number | null; uneven: boolean; onChange: (v: number | null) => void;
}): JSX.Element {
  return (
    <div className="text-right">
      <div className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
        <span>rimborso in</span>
        <Input
          type="number"
          min={0}
          max={30}
          step={1}
          className="w-14 text-right"
          aria-label={`Anni di rimborso — ${field}`}
          value={value ?? ""}
          onChange={(e) => onChange(parseFieldValue(field, e.target.value))}
        />
        <span>anni</span>
      </div>
      {uneven && <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">valori diversi per anno</p>}
    </div>
  );
}

/** Un Select disabilitato con un solo valore: segnaposto del lotto 2. */
function Lotto2Select({ text }: { text: string }): JSX.Element {
  return (
    <Select disabled value="lotto2">
      <SelectTrigger className="h-8 w-36 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="lotto2">{text}</SelectItem>
      </SelectContent>
    </Select>
  );
}

const FINANCING_ROWS: YearInputRow[] = [
  { field: "financing_amount", label: "Importo €", baseLabel: "—" },
  { field: "financing_duration_years", label: "Durata (anni)", baseLabel: "—" },
  { field: "financing_interest_rate", label: "Tasso %", baseLabel: "—" },
];

const INVESTMENT_ROWS: YearInputRow[] = [
  { field: "tangible_investments", label: "Investimenti materiali €", baseLabel: "—" },
  { field: "intangible_investments", label: "Investimenti immateriali €", baseLabel: "—" },
];

const ADVANCED_ROWS: YearInputRow[] = [
  { field: "depreciation_rate", label: "Ammortamento nuovi investimenti materiali %", baseLabel: "—" },
  { field: "depreciation_rate_intangible", label: "Ammortamento nuovi investimenti immateriali %", baseLabel: "—" },
  { field: "asset_disposal_nbv", label: "Cessioni: valore contabile netto €", baseLabel: "—" },
  { field: "asset_disposal_proceeds", label: "Cessioni: corrispettivo €", baseLabel: "—" },
  { field: "cash_sweep_min_cash", label: "Cash sweep: cassa minima €", baseLabel: "—" },
];

export function StepPregressoNuovo(p: StepProps): JSX.Element {
  const baseBs = p.historical[p.baseYear]?.balance;
  const base = useMemo(() => pregressoBase(baseBs), [baseBs]);
  const preview = useMemo(() => pregressoPreview(baseBs, p.preview.data), [baseBs, p.preview.data]);

  const existingDebt = singleYearValue(p.assumptions, p.forecastYears, "existing_debt_repayment_years");
  const altriFinanz = singleYearValue(p.assumptions, p.forecastYears, "altri_finanz_repayment_years");
  const cashSweepEnabled = boolAssumption(p.assumptions, p.forecastYears, "cash_sweep_enabled");

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Scadenziamento del pregresso</CardTitle>
            <CardDescription>saldi al 31/12/{p.baseYear}</CardDescription>
          </CardHeader>
          <CardContent>
            <ScheduleRow
              label="Debiti bancari esistenti"
              small={`${euro(base.bankDebt)} · di cui ${euro(base.bankDebtShort)} a breve`}
            >
              <RepaymentInput
                field="existing_debt_repayment_years"
                value={existingDebt.value}
                uneven={existingDebt.uneven}
                onChange={(v) => p.updateAll("existing_debt_repayment_years", v)}
              />
            </ScheduleRow>
            <ScheduleRow label="Altri finanziatori" small={euro(base.altriFinanziatori)}>
              <RepaymentInput
                field="altri_finanz_repayment_years"
                value={altriFinanz.value}
                uneven={altriFinanz.uneven}
                onChange={(v) => p.updateAll("altri_finanz_repayment_years", v)}
              />
            </ScheduleRow>
            <ScheduleRow label={`Crediti verso clienti al ${p.baseYear}`} small={euro(base.creditiClienti)}>
              <div className="flex items-center gap-2">
                <Badge variant="outline">lotto 2</Badge>
                <Lotto2Select text="entro l'anno" />
              </div>
            </ScheduleRow>
            <ScheduleRow label="Debiti tributari" small={euro(base.debitiTributari)}>
              <div className="flex items-center gap-2">
                <Badge variant="outline">lotto 2</Badge>
                <span className="text-xs text-muted-foreground">si regola al passo 7</span>
              </div>
            </ScheduleRow>
            <p className="pt-3 text-xs text-muted-foreground">
              Con un piano dettagliato in Finanziamenti la durata generica del rimborso viene ignorata: vale il
              piano.
            </p>
          </CardContent>
        </Card>

        <FinancingLoansGrid
          forecastYears={p.forecastYears}
          baseYear={p.baseYear}
          assumptions={p.assumptions}
          onUpdate={p.updateFinancingLoans}
          baseBalance={baseBs}
        />
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Generato dal previsionale</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Nuovo finanziamento
              </p>
              <YearInputTable
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                assumptions={p.assumptions}
                update={p.update}
                rows={FINANCING_ROWS}
              />
            </div>

            <Separator />

            <div>
              <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Nuovi investimenti
              </p>
              <YearInputTable
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                assumptions={p.assumptions}
                update={p.update}
                rows={INVESTMENT_ROWS}
              />
            </div>

            <Accordion type="single" collapsible>
              <AccordionItem value="avanzate" className="border-b-0">
                <AccordionTrigger className="text-sm font-medium">Mostra tutte</AccordionTrigger>
                <AccordionContent>
                  <YearInputTable
                    forecastYears={p.forecastYears}
                    baseYear={p.baseYear}
                    assumptions={p.assumptions}
                    update={p.update}
                    rows={ADVANCED_ROWS}
                  />
                  <div className="mt-3 flex items-center space-x-2">
                    <Checkbox
                      id="cash-sweep-enabled"
                      checked={cashSweepEnabled}
                      onCheckedChange={(checked) => p.updateAll("cash_sweep_enabled", checked === true)}
                    />
                    <Label htmlFor="cash-sweep-enabled" className="text-sm font-normal">
                      Cash sweep (usa cassa in eccesso per rimborsare debito)
                    </Label>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </CardContent>
        </Card>

        <PreviewPanel
          title="Debito, cassa e PFN"
          baseYear={p.baseYear}
          years={preview.years}
          rows={preview.rows}
          loading={p.preview.loading}
          error={p.preview.error}
        >
          {preview.unfunded ? (
            <div className="mt-3 flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <b>
                  Fabbisogno scoperto nel {preview.unfunded.year}: {formatCurrency(preview.unfunded.amount)}.
                </b>{" "}
                Il previsionale non verrà generato finché non lo copri: un nuovo finanziamento, meno investimenti,
                o un rimborso più lungo del pregresso.
              </div>
            </div>
          ) : (
            p.preview.data && (
              <div className="mt-3 flex gap-2 rounded-md bg-muted p-3 text-sm">
                <Check className="h-4 w-4 shrink-0 mt-0.5" /> La cassa resta positiva in tutti gli anni: nessun
                fabbisogno da coprire.
              </div>
            )
          )}
        </PreviewPanel>
      </div>
    </div>
  );
}
