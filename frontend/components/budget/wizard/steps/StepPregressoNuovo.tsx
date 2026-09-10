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
//
// La tabella dello scadenziamento del circolante e' PregressoTable, e le sue
// decisioni stanno in lib/budget-pregresso-tabella.ts: qui restano solo il
// piano da leggere/scrivere (primo anno di piano) e l'interruttore € / %.
import type { JSX, ReactNode } from "react";
import { useMemo, useState } from "react";
import { AlertTriangle, Check, TrendingDown } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { FinancingLoansGrid } from "@/components/budget/FinancingLoansGrid";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { euro } from "@/lib/budget-format";
import { PREGRESSO_LABELS, validatePregresso } from "@/lib/budget-pregresso-circolante";
import { boolAssumption, pregressoBase, pregressoPreview, singleYearValue } from "@/lib/budget-pregresso-step";
import { TABELLA_KEYS, massesLongOf, massesOf, type PregressoMode } from "@/lib/budget-pregresso-tabella";
import { previewNotice } from "@/lib/budget-preview-notice";
import { scopertoAvvisi } from "@/lib/budget-preview-rows";
import type { Pregresso } from "@/types/api";
import type { StepProps } from "../types";
import { PregressoTable } from "../PregressoTable";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";

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

const FINANCING_ROWS: YearInputRow[] = [
  { field: "financing_amount", label: "Importo €", baseLabel: "—" },
  { field: "financing_duration_years", label: "Durata (anni)", baseLabel: "—" },
  { field: "financing_interest_rate", label: "Tasso %", baseLabel: "—" },
];

const INVESTMENT_ROWS: YearInputRow[] = [
  { field: "tangible_investments", label: "Investimenti materiali €", baseLabel: "—" },
  { field: "intangible_investments", label: "Investimenti immateriali €", baseLabel: "—" },
];

// Il tetto e' per anno come ogni ipotesi; vuoto = concesso senza tetto, cioe'
// la modalita' di MISURA: il piano stressato gira, e l'anteprima dice quanta
// finanza richiede.
const OVERDRAFT_ROWS: YearInputRow[] = [
  { field: "overdraft_limit", label: "Tetto dello scoperto €", sub: "vuoto = senza tetto", baseLabel: "—" },
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
  const preview = useMemo(
    () => pregressoPreview(baseBs, p.preview.data, TABELLA_KEYS),
    [baseBs, p.preview.data],
  );

  // Il piano di scadenziamento e' UNO per scenario, e vive nelle ipotesi del
  // PRIMO anno di piano (spec §3.5): il motore lo legge da li'. Scriverlo su
  // ogni anno lo farebbe applicare piu' volte.
  const firstYear = p.forecastYears[0];
  const masses = useMemo(() => massesOf(baseBs), [baseBs]);
  // La massa OLTRE l'esercizio di ciascun saldo: serve solo alla nota di
  // destino (rilievo 1 della revisione), mai alla validazione o al residuo.
  const massesLong = useMemo(() => massesLongOf(baseBs), [baseBs]);
  // `?? {}` costruirebbe un oggetto NUOVO a ogni render, e la `useMemo` degli
  // errori si rifarebbe ogni volta: si dipende dal campo salvato, non dal
  // ripiego.
  const pregressoSalvato = p.assumptions[firstYear]?.pregresso;
  const pregresso = useMemo(() => (pregressoSalvato ?? {}) as Pregresso, [pregressoSalvato]);
  // Il setter tipizzato (conflitto B): scrive sempre nel primo anno di
  // piano, la regola vive in `withPregresso` (`lib/budget-horizon.ts`), non
  // qui.
  const setPregresso = (next: Pregresso) => p.updatePregresso(next);
  const [mode, setMode] = useState<PregressoMode>("eur");
  // Diagnostica, non correzione: superare la massa di apertura e' un errore,
  // e chi lo produce lo vede scritto — il salvataggio lo rifiuterebbe comunque
  // con lo stesso messaggio, che pero' arriverebbe molto piu' tardi.
  const errors = useMemo(
    () => validatePregresso(pregresso, masses, p.forecastYears.length),
    [pregresso, masses, p.forecastYears.length],
  );

  const existingDebt = singleYearValue(p.assumptions, p.forecastYears, "existing_debt_repayment_years");
  const altriFinanz = singleYearValue(p.assumptions, p.forecastYears, "altri_finanz_repayment_years");
  const cashSweepEnabled = boolAssumption(p.assumptions, p.forecastYears, "cash_sweep_enabled");
  const overdraftAllowed = boolAssumption(p.assumptions, p.forecastYears, "overdraft_allowed");
  // Letti da cio' che il motore dichiara, mai ricalcolati qui.
  const avvisi = useMemo(() => scopertoAvvisi(p.preview.data?.forecast_years ?? []), [p.preview.data]);

  // `items-start` come negli altri passi: senza, la colonna si stira a tutta
  // l'altezza della riga e il `lg:sticky` della colonna destra non ha effetto.
  return (
    <div className="grid gap-5 lg:grid-cols-2 items-start">
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
            <p className="pt-3 text-xs text-muted-foreground">
              Con un piano dettagliato in Finanziamenti la durata generica del rimborso viene ignorata: vale il
              piano.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Pregresso del circolante</CardTitle>
              <CardDescription>
                quando rientrano — o si pagano — i saldi al 31/12/{p.baseYear}
              </CardDescription>
            </div>
            {/* Stesso interruttore a due pulsanti dell'orizzonte di piano
                (StepScenario): l'importo canonico e' l'euro, la percentuale e'
                una vista sulla stessa cella. */}
            <div className="flex shrink-0 items-center gap-1">
              <Button type="button" size="sm" variant={mode === "eur" ? "default" : "outline"}
                onClick={() => setMode("eur")}>
                €
              </Button>
              <Button type="button" size="sm" variant={mode === "pct" ? "default" : "outline"}
                onClick={() => setMode("pct")}>
                %
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {baseBs && firstYear !== undefined ? (
              <PregressoTable
                keys={TABELLA_KEYS}
                masses={masses}
                massesLong={massesLong}
                pregresso={pregresso}
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                mode={mode}
                onChange={setPregresso}
                errors={errors}
                writeoffIgnored={preview.writeoffIgnoredByYear}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                Il bilancio dell&apos;anno base non è ancora disponibile: senza quei saldi non c&apos;è nulla da
                scadenziare.
              </p>
            )}

            <div className="mt-3 flex items-start justify-between gap-3 border-t border-border/50 pt-3">
              <div>
                <div className="text-sm font-medium text-foreground">{PREGRESSO_LABELS.debiti_tributari}</div>
                <div className="text-xs text-muted-foreground">{euro(masses.debiti_tributari)}</div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                seguono la posizione fiscale: si regolano al passo Imposte
              </span>
            </div>
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

      {/* `lg:sticky lg:top-4` come negli altri quattro passi con anteprima:
          la colonna dell'anteprima resta a vista mentre si scorre la colonna
          degli input. Qui la colonna porta anche la card "Generato dal
          previsionale", quindi lo `space-y-4` resta. */}
      <div className="space-y-4 lg:sticky lg:top-4">
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

            <Separator />

            <div>
              <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Scoperto di conto corrente
              </p>
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
          error={previewNotice(p.preview)}
        >
          {/* L'inesigibile che un override del CE ha impedito di rilevare: il
              credito e' rimasto a bilancio, e l'utente lo credeva svalutato.
              Il motore lo dichiara, nessuna schermata lo diceva. */}
          {preview.writeoffIgnored.length > 0 && (
            <div className="mt-3 space-y-1 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              {preview.writeoffIgnored.map((m) => (
                <div key={m} className="flex gap-2">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{m}</span>
                </div>
              ))}
            </div>
          )}

          {/* Il fabbisogno scoperto lo dice gia' `previewNotice`, sopra, in UN
              solo posto (lib/budget-preview-notice.ts): qui resta la sola
              conferma opposta, che quel riquadro non da'. */}
          {/* Lo scoperto acceso: l'avviso forte, con gli importi e il picco. */}
          {avvisi.scoperto && (
            <div className="mt-3 flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{avvisi.scoperto}</span>
            </div>
          )}

          {/* La cassa che il piano consuma, anche dove resta positiva: l'avviso
              che arriva PRIMA dello scoperto, non dopo. */}
          {avvisi.cassa && (
            <div className="mt-3 flex gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <TrendingDown className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{avvisi.cassa}</span>
            </div>
          )}

          {!preview.unfunded && !avvisi.scoperto && p.preview.data && (
            <div className="mt-3 flex gap-2 rounded-md bg-muted p-3 text-sm">
              <Check className="h-4 w-4 shrink-0 mt-0.5" /> La cassa resta positiva in tutti gli anni: nessun
              fabbisogno da coprire.
            </div>
          )}
        </PreviewPanel>
      </div>
    </div>
  );
}
