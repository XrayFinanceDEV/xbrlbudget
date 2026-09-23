"use client";

// Passo 6 del wizard ipotesi: Patrimoniale piano (spec 2026-09-15 §4.6). Ciò
// che il previsionale GENERA — a differenza del passo 5 «Patrimoniale
// pregresso», che chiude ciò che c'è già: le voci minori dello SP con la
// loro regola nel piano, il fondo TFR con le liquidazioni per anno, i nuovi
// investimenti, uno o più nuovi finanziamenti con il proprio nome, e infine
// debito/cassa/PFN come il motore li ha davvero prodotti.
//
// Presentazionale: ogni decisione (quale anno mostrare, quale riga costa,
// quali anni ha davvero prodotto il motore, l'avviso dei fidi) sta in
// lib/budget-piano-step.ts, provata in environment: node. Un solo motore di
// proiezione, e sta in Python: debito, cassa, PFN, TFR e il pareggio si
// leggono da ciò che `POST /preview` ha già restituito, mai ricalcolati qui.
import type { JSX } from "react";
import { useMemo } from "react";
import { AlertTriangle, Check, Plus, TrendingDown, X } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NumericDraftInput } from "@/components/budget/PercentInput";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { boolAssumption } from "@/lib/budget-horizon";
import { manualSpValue, previewTotalAssets } from "@/lib/budget-sp-manuale";
import {
  DRIVERS, DRIVER_LABELS, minorFieldsRows, pianiPregressoOf, spIndexingOf,
} from "@/lib/budget-circolante-step";
import {
  annoLibero, avvisiFidi, nuoviFinanziamenti, nuovoPrestito, regimeEsplicito, regoleVociMinori, riepilogoNuovo,
  rowsAltriCreditiDebiti, rowsDebitoCassaPfn, tfrRighe, withNuovoCampo,
} from "@/lib/budget-piano-step";
import { euro, numOrNull, pct1, pctOf } from "@/lib/budget-format";
import { formatCurrencyDetailed, formatNumber } from "@/lib/formatters";
import { previewNotice } from "@/lib/budget-preview-notice";
import { confermaCassaPositiva, scopertoAvvisi } from "@/lib/budget-preview-rows";
import type { SpIndexingDriver } from "@/types/api";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";

const INVESTMENT_ROWS: YearInputRow[] = [
  { field: "tangible_investments", label: "Investimenti materiali €", baseLabel: "—" },
  { field: "intangible_investments", label: "Investimenti immateriali €", baseLabel: "—" },
];

// Il tetto e' per anno come ogni ipotesi; vuoto = concesso senza tetto, cioe'
// la modalita' di MISURA: il piano stressato gira, e l'anteprima dice quanta
// finanza richiede. Solo fuori dal regime esplicito (§5.2-bis): con i fidi
// separati il piano non si ferma mai per fabbisogno scoperto.
const OVERDRAFT_ROWS: YearInputRow[] = [
  { field: "overdraft_limit", label: "Tetto dello scoperto €", sub: "vuoto = senza tetto", baseLabel: "—" },
];

const INVESTMENT_DETAIL_ROWS: YearInputRow[] = [
  { field: "depreciation_rate", label: "Ammortamento nuovi investimenti materiali %", baseLabel: "—" },
  { field: "depreciation_rate_intangible", label: "Ammortamento nuovi investimenti immateriali %", baseLabel: "—" },
  { field: "asset_disposal_nbv", label: "Cessioni: valore contabile netto €", baseLabel: "—" },
  { field: "asset_disposal_proceeds", label: "Cessioni: corrispettivo €", baseLabel: "—" },
];

const CASH_SWEEP_ROWS: YearInputRow[] = [
  { field: "cash_sweep_min_cash", label: "Cash sweep: cassa minima €", baseLabel: "—" },
];

export function StepPatrimonialePiano(p: StepProps): JSX.Element {
  const baseBs = p.historical[p.baseYear]?.balance;
  const baseInc = p.historical[p.baseYear]?.income;
  const firstYear = p.forecastYears[0];
  const previewYears = p.preview.data?.forecast_years ?? [];

  // ── Voci minori: la stessa card di prima (Task 12), spostata qui com'era ──
  const previdenzaChecked = boolAssumption(p.assumptions, p.forecastYears, "previdenza_scales_with_personnel");
  const indexing = useMemo(() => spIndexingOf(p.assumptions, p.forecastYears), [p.assumptions, p.forecastYears]);
  const piani = useMemo(() => pianiPregressoOf(p.assumptions, p.forecastYears), [p.assumptions, p.forecastYears]);
  const minorRows = useMemo(
    () => minorFieldsRows(baseBs, indexing, previdenzaChecked, piani),
    [baseBs, indexing, previdenzaChecked, piani],
  );
  const regoleAttive = minorRows.filter((row) => row.code !== null && row.baseAmount !== 0);
  const saldiZero = minorRows.filter((row) => row.code !== null && row.baseAmount === 0);
  const anniStorici = p.historicalYears.filter((year) => year <= p.baseYear).slice(-2);
  const previewByYear = useMemo(() => new Map(previewYears.map((y) => [y.year, y])), [previewYears]);
  const projectedOf = (field: string): Record<number, number | null> =>
    Object.fromEntries(p.forecastYears.map((year) => [
      year,
      numOrNull((previewByYear.get(year)?.balance_sheet as unknown as Record<string, unknown> | undefined)?.[field]),
    ]));
  const renderMinorRow = (row: (typeof minorRows)[number]) => {
    const projected = projectedOf(row.balanceField);
    return (
      <div key={row.field} className="border-b border-border/50 py-3 last:border-b-0">
        <div className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_7rem] lg:grid-cols-[minmax(0,1fr)_7rem_15rem] lg:items-center lg:gap-4">
          <div className="min-w-0 text-sm font-medium text-foreground">{row.label}</div>
          <div className="text-sm tabular-nums text-muted-foreground sm:text-right">{row.baseLabel}</div>
          {row.code !== null && (
            <Select
              value={row.driver ?? "manuale"}
              onValueChange={(v) => p.updateSpRule(
                row.code as string, row.balanceField, row.field,
                v === "manuale" ? null : (v as SpIndexingDriver), projected,
              )}
            >
              <SelectTrigger className="w-full text-xs sm:col-span-2 lg:col-span-1" aria-label={`Regola ${row.label}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="manuale">Manuale</SelectItem>
                {DRIVERS.map((d) => <SelectItem key={d} value={d}>{`Cresce con ${DRIVER_LABELS[d]}`}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </div>
        {row.code !== null && row.driver === null && (
          <div className="mt-3 rounded-md bg-muted/30 p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">Valore a fine anno (€) · incidenza sul totale attivo</div>
            <div className="overflow-x-auto pb-1">
              <div
                className="grid gap-2"
                style={{
                  gridTemplateColumns: `repeat(${anniStorici.length + p.forecastYears.length}, minmax(0, 1fr))`,
                  minWidth: `${(anniStorici.length + p.forecastYears.length) * 9}rem`,
                }}
              >
              {anniStorici.map((year) => {
                const balance = p.historical[year]?.balance as unknown as Record<string, unknown> | undefined;
                const amount = numOrNull(balance?.[row.balanceField]);
                const incidence = pct1(pctOf(amount, numOrNull(balance?.total_assets)));
                return (
                  <div key={year} className="rounded-md border border-border bg-muted/50 px-3 py-2">
                    <div className="text-xs font-medium text-muted-foreground">{year} · storico</div>
                    <div className="mt-1 text-right text-sm tabular-nums">{amount === null ? "—" : formatCurrencyDetailed(amount)}</div>
                    <div className="text-right text-xs tabular-nums text-muted-foreground">{incidence}</div>
                  </div>
                );
              })}
              {p.forecastYears.map((year, index) => {
                const value = manualSpValue(p.assumptions, year, row.balanceField, projected[year]);
                const totalAssets = previewTotalAssets(previewByYear.get(year)?.balance_sheet);
                const incidence = p.preview.loading ? "…" : pct1(pctOf(value, totalAssets));
                return (
                  <div key={year} className={`rounded-md border border-border bg-background px-3 py-2 ${index === 0 ? "border-l-2 border-l-primary/40" : ""}`}>
                    <Label className="text-xs text-muted-foreground">{year} · piano</Label>
                    <div className="relative mt-1">
                      <NumericDraftInput
                        value={value == null ? "" : value.toFixed(2).replace(".", ",")}
                        displayValue={value == null ? "" : formatNumber(value, 2)}
                        onRawChange={(raw) => {
                          if (raw === "") return;
                          const amount = Math.round(Number(raw.replace(",", ".")) * 100) / 100;
                          if (Number.isFinite(amount) && amount >= 0) {
                            p.updateManualSpAmount(year, row.code as string, row.balanceField, row.field, amount, projected);
                          }
                        }}
                        ariaLabel={`${row.label} ${year} in euro`}
                        className="w-full rounded border border-input bg-background py-1.5 pl-2 pr-7 text-right text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                        placeholder="0,00"
                      />
                      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">€</span>
                    </div>
                    <div className="mt-1 text-right text-xs tabular-nums text-muted-foreground">{incidence}</div>
                  </div>
                );
              })}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── Fondo TFR ──
  const tfrSuspended = boolAssumption(p.assumptions, p.forecastYears, "tfr_accrual_suspended");
  const righeTfr = useMemo(
    () => tfrRighe(p.assumptions, p.forecastYears, p.preview.data),
    [p.assumptions, p.forecastYears, p.preview.data],
  );
  const sp15Base = baseBs ? numOrNull(baseBs.sp15_tfr) : null;

  // ── Nuovi finanziamenti ──
  const nuovi = useMemo(() => nuoviFinanziamenti(p.assumptions, p.forecastYears), [p.assumptions, p.forecastYears]);
  const cambiaAnno = (n: (typeof nuovi)[number], nuovoAnno: number) => {
    if (nuovoAnno === n.year) return;
    const loansVecchio = ((p.assumptions[n.year]?.financing_loans ?? []) as typeof nuovi[number]["loan"][])
      .filter((_, i) => i !== n.index);
    const loansNuovo = [...((p.assumptions[nuovoAnno]?.financing_loans ?? []) as typeof nuovi[number]["loan"][]), n.loan];
    p.updateFinancingLoans(n.year, loansVecchio);
    p.updateFinancingLoans(nuovoAnno, loansNuovo);
  };
  const modificaCampo = (n: (typeof nuovi)[number], field: keyof typeof n.loan, value: string | number | null) => {
    const loans = (p.assumptions[n.year]?.financing_loans ?? []) as typeof n.loan[];
    p.updateFinancingLoans(n.year, withNuovoCampo(loans, n.index, field, value));
  };
  const rimuovi = (n: (typeof nuovi)[number]) => {
    const loans = (p.assumptions[n.year]?.financing_loans ?? []) as typeof n.loan[];
    p.updateFinancingLoans(n.year, loans.filter((_, i) => i !== n.index));
  };
  const aggiungiFinanziamento = () => {
    const anno = annoLibero(p.forecastYears, nuovi);
    const loans = (p.assumptions[anno]?.financing_loans ?? []) as typeof nuovi[number]["loan"][];
    p.updateFinancingLoans(anno, [...loans, nuovoPrestito(anno)]);
  };

  // ── Cassa e scoperto ──
  const esplicito = firstYear !== undefined && regimeEsplicito(p.assumptions, firstYear);
  const cashSweepEnabled = boolAssumption(p.assumptions, p.forecastYears, "cash_sweep_enabled");
  const overdraftAllowed = boolAssumption(p.assumptions, p.forecastYears, "overdraft_allowed");
  const avvisi = useMemo(() => scopertoAvvisi(previewYears), [previewYears]);
  const avvisiDeiFidi = useMemo(() => avvisiFidi(previewYears), [previewYears]);

  // ── Anteprima: debito, cassa, PFN ──
  const fidiBase = firstYear !== undefined ? numOrNull(p.assumptions[firstYear]?.bank_lines_amount) : null;
  const previewRows = useMemo(
    () => (baseBs ? rowsDebitoCassaPfn(baseBs, fidiBase, previewYears, baseInc) : []),
    [baseBs, fidiBase, previewYears, baseInc],
  );

  // ── Anteprima: altri crediti e debiti del piano ──
  const regole = useMemo(() => regoleVociMinori(p.assumptions, p.forecastYears), [p.assumptions, p.forecastYears]);
  const rowsAltri = useMemo(
    () => (baseBs ? rowsAltriCreditiDebiti(baseBs, previewYears, regole) : []),
    [baseBs, previewYears, regole],
  );

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Altri saldi patrimoniali nel piano</CardTitle>
          <p className="text-sm text-muted-foreground">
            Scegli come evolvono i saldi del {p.baseYear}. In Manuale inserisci l&apos;importo previsto per ogni anno.
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 border-b border-border pb-2 text-xs font-semibold text-muted-foreground sm:grid-cols-[minmax(0,1fr)_7rem] lg:grid-cols-[minmax(0,1fr)_7rem_15rem] lg:gap-4">
            <span>Voce</span><span className="text-right">Saldo {p.baseYear}</span><span className="hidden lg:block">Regola nel piano</span>
          </div>
          {regoleAttive.length > 0 && (
            <section className="mt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-foreground">Regole modificabili</h3>
              <div className="mt-1">{regoleAttive.map(renderMinorRow)}</div>
            </section>
          )}
          {saldiZero.length > 0 && (
            <Accordion type="single" collapsible className="mt-3 border-t border-border">
              <AccordionItem value="saldi-zero" className="border-b-0">
                <AccordionTrigger className="py-3 text-sm font-medium">Saldi a zero nel {p.baseYear} ({saldiZero.length})</AccordionTrigger>
                <AccordionContent>{saldiZero.map(renderMinorRow)}</AccordionContent>
              </AccordionItem>
            </Accordion>
          )}
          <div className="flex items-center space-x-2 border-t border-border pt-3">
            <Checkbox id="previdenza-scales" checked={previdenzaChecked} onCheckedChange={(checked) => p.updateAll("previdenza_scales_with_personnel", checked === true)} />
            <Label htmlFor="previdenza-scales" className="text-sm font-normal">Debiti previdenziali scalano col costo del personale</Label>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2 items-start">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fondo TFR</CardTitle>
            <p className="text-xs text-muted-foreground">
              {euro(sp15Base)} al 31/12/{p.baseYear}
            </p>
          </CardHeader>
          <CardContent>
            <div className="mb-3 flex items-center space-x-2">
              <Checkbox
                id="tfr-suspended"
                checked={tfrSuspended}
                onCheckedChange={(checked) => p.updateAll("tfr_accrual_suspended", checked === true)}
              />
              <Label htmlFor="tfr-suspended" className="text-sm font-normal">
                Sospendi l&apos;accantonamento al fondo TFR aziendale (TFR versato a fondi esterni o INPS)
              </Label>
            </div>
            <p className="mb-3 text-xs text-muted-foreground">
              Senza spunta il fondo cresce con l&apos;accantonamento annuo (retribuzioni / 13,5). Con la spunta l&apos;accantonamento al fondo è 0 €.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs font-semibold text-muted-foreground">
                    <th className="px-2 py-1.5">Anno</th>
                    <th className="px-2 py-1.5 text-right">Accantonamento</th>
                    <th className="px-2 py-1.5 text-right">Liquidazioni</th>
                    <th className="px-2 py-1.5 text-right">Fondo a fine anno</th>
                  </tr>
                </thead>
                <tbody>
                  {righeTfr.map((r) => (
                    <tr key={r.year} className="border-b border-border/50">
                      <td className="px-2 py-1.5 font-medium">{r.year}</td>
                      <td className="px-2 py-1.5 text-right text-muted-foreground">
                        {r.sospeso ? "0 € · sospeso" : euro(r.accantonamento)}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <Input
                          type="number"
                          min={0}
                          step={1000}
                          className="w-32 text-right"
                          aria-label={`Liquidazioni TFR ${r.year}`}
                          value={r.liquidazione || ""}
                          onChange={(e) => p.update(r.year, "tfr_payments", e.target.value === "" ? 0 : Number(e.target.value))}
                        />
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        {r.oltre
                          ? <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive">oltre il fondo</span>
                          : euro(r.chiusura)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Liquidazioni: pensionamenti, dimissioni, licenziamenti. Escono di cassa nell&apos;anno e riducono il
              fondo.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nuovi investimenti</CardTitle>
          </CardHeader>
          <CardContent>
            <YearInputTable
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
              rows={INVESTMENT_ROWS}
            />
            <Accordion type="single" collapsible className="mt-3 border-t border-border/50">
              <AccordionItem value="investimenti-dettaglio" className="border-b-0">
                <AccordionTrigger className="text-sm font-medium">Ammortamenti e cessioni</AccordionTrigger>
                <AccordionContent>
                  <YearInputTable
                    forecastYears={p.forecastYears}
                    baseYear={p.baseYear}
                    assumptions={p.assumptions}
                    update={p.update}
                    rows={INVESTMENT_DETAIL_ROWS}
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Finanziamenti e cassa</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <section className="space-y-3" aria-label="Nuovi finanziamenti">
              <h3 className="text-sm font-semibold">Nuovi finanziamenti</h3>
            {nuovi.map((n) => (
              <div key={`${n.year}-${n.index}`} className="rounded-md border-l-2 border-l-primary bg-muted/20 p-3">
                <div className="mb-1 flex items-center gap-2">
                  <Input
                    value={n.loan.name ?? ""}
                    placeholder="Nome del finanziamento"
                    aria-label={`Nome finanziamento ${n.year}`}
                    onChange={(e) => modificaCampo(n, "name", e.target.value)}
                    className="h-8"
                  />
                  <Button
                    type="button" variant="ghost" size="icon"
                    aria-label={`Rimuovi finanziamento ${n.loan.name ?? n.year}`}
                    onClick={() => rimuovi(n)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <p className="mb-2 text-xs text-muted-foreground">{riepilogoNuovo(n.loan, n.year)}</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Importo €</Label>
                    <Input
                      type="number" min={0} step={1000} value={n.loan.amount}
                      aria-label={`Importo finanziamento ${n.year}`}
                      onChange={(e) => modificaCampo(n, "amount", Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Erogato nel</Label>
                    <Select value={String(n.year)} onValueChange={(v) => cambiaAnno(n, Number(v))}>
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {p.forecastYears.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Durata (anni)</Label>
                    <Input
                      type="number" min={1} max={30} step={1} value={n.loan.duration_years ?? ""}
                      aria-label={`Durata finanziamento ${n.year}`}
                      onChange={(e) => modificaCampo(n, "duration_years", Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Preamm. (anni)</Label>
                    <Input
                      type="number" min={0} max={Math.max(0, Number(n.loan.duration_years ?? 0) - 1)} step={1}
                      value={n.loan.grace_years}
                      aria-label={`Preammortamento finanziamento ${n.year}`}
                      onChange={(e) => modificaCampo(n, "grace_years", Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Tasso %</Label>
                    <Input
                      type="number" min={0} max={100} step={0.1} value={n.loan.interest_rate}
                      aria-label={`Tasso finanziamento ${n.year}`}
                      onChange={(e) => modificaCampo(n, "interest_rate", Number(e.target.value))}
                    />
                  </div>
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={aggiungiFinanziamento}>
              <Plus className="mr-1 h-4 w-4" /> Aggiungi finanziamento
            </Button>
            </section>
            <section className="space-y-3 border-t border-border pt-4" aria-label="Cassa e scoperto">
              <h3 className="text-sm font-semibold">Cassa e scoperto</h3>
            {esplicito ? (
              <p className="text-xs text-muted-foreground">
                Se la cassa va in negativo il piano riutilizza i fidi; oltre l&apos;importo di partenza compare un
                avviso.
              </p>
            ) : (
              <div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="overdraft-allowed"
                    checked={overdraftAllowed}
                    onCheckedChange={(checked) => p.updateAll("overdraft_allowed", checked === true)}
                  />
                  <Label htmlFor="overdraft-allowed" className="text-sm font-normal">
                    Concedi lo scoperto: il fabbisogno scoperto diventa debito bancario a breve
                  </Label>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Spento, il previsionale si ferma sul primo anno che non si finanzia. Acceso, misura quanta finanza
                  richiedono le ipotesi: oneri al tasso del nuovo finanziamento, sullo scoperto di inizio anno.
                </p>
                {overdraftAllowed && (
                  <div className="mt-2">
                    <YearInputTable
                      forecastYears={p.forecastYears}
                      baseYear={p.baseYear}
                      assumptions={p.assumptions}
                      update={p.update}
                      rows={OVERDRAFT_ROWS}
                    />
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center space-x-2 border-t border-border/50 pt-3">
              <Checkbox
                id="cash-sweep-enabled"
                checked={cashSweepEnabled}
                onCheckedChange={(checked) => p.updateAll("cash_sweep_enabled", checked === true)}
              />
              <Label htmlFor="cash-sweep-enabled" className="text-sm font-normal">
                Usa la cassa in eccesso per ridurre fidi, anticipi e scoperti di conto corrente
              </Label>
            </div>
            {cashSweepEnabled && (
              <YearInputTable
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                assumptions={p.assumptions}
                update={p.update}
                rows={CASH_SWEEP_ROWS}
              />
            )}
            </section>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4 lg:sticky lg:top-4">
        <PreviewPanel
          title="Debito, cassa e PFN"
          baseYear={p.baseYear}
          years={previewYears.map((y) => y.year)}
          rows={previewRows}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        >
          {avvisi.scoperto && (
            <div className="mt-3 flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{avvisi.scoperto}</span>
            </div>
          )}
          {avvisi.cassa && (
            <div className="mt-3 flex gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <TrendingDown className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{avvisi.cassa}</span>
            </div>
          )}
          {avvisi.sottoMinimo && (
            <div className="mt-3 flex gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <TrendingDown className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{avvisi.sottoMinimo}</span>
            </div>
          )}
          {/* I fidi tirati oltre l'affidamento di partenza (§5.2-bis, motore
              futuro Task 3b): un avviso per anno, letto da cio' che il
              motore dichiara, mai ricalcolato qui. */}
          {avvisiDeiFidi.map((m) => (
            <div key={m} className="mt-3 flex gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{m}</span>
            </div>
          ))}
          {confermaCassaPositiva(p.preview.data, avvisi) && (
            <div className="mt-3 flex gap-2 rounded-md bg-muted p-3 text-sm">
              <Check className="h-4 w-4 shrink-0 mt-0.5" /> La cassa resta positiva in tutti gli anni: nessun
              fabbisogno da coprire.
            </div>
          )}
        </PreviewPanel>

        <PreviewPanel
          title="Altri crediti e debiti del piano · dalle voci minori"
          baseYear={p.baseYear}
          years={previewYears.map((y) => y.year)}
          rows={rowsAltri}
          loading={p.preview.loading}
          error={null}
        />
      </div>
      </div>
      </div>
  );
}
