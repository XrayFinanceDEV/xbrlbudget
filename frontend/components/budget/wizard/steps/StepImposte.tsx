"use client";

// Passo 7 del wizard ipotesi: imposte (spec 2026-09-08 §4.7, task-14-brief.md).
// È l'ULTIMO passo — non c'è un ottavo passo di riepilogo: il wizard si
// chiude qui e il previsionale completo si legge e si ritocca nelle tab CE
// Prev. e SP Prev. esistenti.
//
// Presentazionale: ogni decisione — che cosa mostrare/scrivere per
// l'aliquota forzata, quali anni ha davvero prodotto il motore — sta in
// lib/budget-imposte-step.ts, provata in environment: node. Le imposte NON
// si ricalcolano qui: le produce il motore, rowsImposte le legge dal CE che
// il motore ha già scritto.
import type { JSX } from "react";
import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TaxTemporaryDifferencesGrid } from "@/components/budget/TaxTemporaryDifferencesGrid";
import { computeEffectiveTaxRate } from "@/components/budget/assumption-rows";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { euro, numOrNull, pct1 } from "@/lib/budget-format";
import { validatePregresso } from "@/lib/budget-pregresso-circolante";
import { massesOf } from "@/lib/budget-pregresso-tabella";
import {
  ACCONTO_CHIOSA,
  DEFAULT_ACCONTO_PCT,
  DEFAULT_TAX_RATE,
  MANUAL_TAX_AVVISO,
  PREGRESSO_IGNORED_AVVISO,
  SP17E_NOTA_AUTOMATICA,
  TAX_RATE_PLACEHOLDER,
  TRIBUTARI_KEYS,
  TRIBUTARI_TABELLA_NOTA,
  accontoPctValue,
  draftDisplay,
  impostePreview,
  manualTaxYears,
  rateOptions,
  rateSelectValue,
  spTributariRows,
  taxRateInputDisplay,
  taxRateValue,
  tributariMasses,
  tributariOpening,
  tributariPlan,
  tributariTabella,
  withAccontoPct,
  withRate,
  withRateUguali,
  withSaldo,
} from "@/lib/budget-imposte-step";
import { planTaxRate } from "@/lib/budget-tax-rate";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { Pregresso } from "@/types/api";
import type { StepProps } from "../types";
import { PregressoTable } from "../PregressoTable";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";

const ADVANCES_ROWS: YearInputRow[] = [{ field: "tax_advances_paid", label: "Acconti versati nell'anno", baseLabel: "—" }];

/** Riga «etichetta / nota piccola» a sinistra, controllo a destra — lo stesso
 *  schema del passo 6 (`ScheduleRow` in StepPregressoNuovo). */
function TribRow({ label, small, children }: { label: string; small: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 pb-2.5">
      <div>
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="text-xs text-muted-foreground">{small}</div>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function StepImposte(p: StepProps): JSX.Element {
  const baseInc = p.historical[p.baseYear]?.income;
  const baseBs = p.historical[p.baseYear]?.balance;
  const effectiveRate = baseInc ? computeEffectiveTaxRate(baseInc) : null;

  const taxRate = taxRateValue(p.assumptions, p.forecastYears);
  const taxRateDisplay = taxRateInputDisplay(taxRate);
  // Quale aliquota il piano usera' davvero, e perche': una sola funzione, la
  // stessa che rende il passo 4 (lib/budget-tax-rate.ts). Prima i due passi
  // rispondevano in modo diverso sullo stesso caso.
  const plan = useMemo(
    () => planTaxRate(effectiveRate, p.assumptions, p.forecastYears),
    [effectiveRate, p.assumptions, p.forecastYears],
  );

  const preview = useMemo(() => impostePreview(baseInc, p.preview.data), [baseInc, p.preview.data]);

  // La via manuale (percentuale di crescita su sp06e/sp16e) e' un'alternativa
  // al piano, non un suo complemento: e' lei a decidere se «Debiti tributari
  // oltre %» sia a schermo, perche' fuori di li' non governa nulla. Il motore
  // decide PER ANNO (`manualTaxYears`): su un piano misto la riga resta a
  // schermo (governa da qualche parte) ma le celle degli anni NON manuali
  // restano inerti — `automaticYears` e' il complemento passato a
  // `spTributariRows` (fix1 R2).
  const yearsManuali = useMemo(
    () => manualTaxYears(p.assumptions, p.forecastYears),
    [p.assumptions, p.forecastYears],
  );
  const manual = yearsManuali.length > 0;
  const automaticYears = useMemo(
    () => p.forecastYears.filter((y) => !yearsManuali.includes(y)),
    [p.forecastYears, yearsManuali],
  );
  const tributariRows = useMemo(
    () => spTributariRows(baseBs, manual, automaticYears),
    [baseBs, manual, automaticYears],
  );

  // Il piano e' UNO per scenario e vive nelle ipotesi del PRIMO anno di piano,
  // come quello del passo 6: il motore lo legge da li', e scriverlo su ogni
  // anno lo farebbe applicare piu' volte.
  const firstYear = p.forecastYears[0];
  const opening = useMemo(() => tributariOpening(baseBs), [baseBs]);
  const pregressoSalvato = p.assumptions[firstYear]?.pregresso;
  const pregresso = useMemo(() => (pregressoSalvato ?? {}) as Pregresso, [pregressoSalvato]);
  const tribPlan = tributariPlan(pregresso);
  const setPregresso = (next: Pregresso) => {
    p.updatePregresso(next);
  };
  const masses = useMemo(() => massesOf(baseBs), [baseBs]);
  // Diagnostica, non correzione: si valida il SOLO piano tributario, cosi' gli
  // errori delle altre quattro voci restano al passo che le scadenzia.
  const errors = useMemo(
    () => validatePregresso(tribPlan ? { debiti_tributari: tribPlan } : {}, masses, p.forecastYears.length),
    [tribPlan, masses, p.forecastYears.length],
  );
  const opzioniRate = rateOptions(p.forecastYears.length);

  // Bozze locali delle due caselle controllate (saldo, acconto): senza
  // questo stato, svuotare la casella col backspace la fa ricadere subito sul
  // valore di ripiego del piano SALVATO (0 per il saldo, 100 per l'acconto) e
  // la digitazione successiva riparte da li' invece che da vuoto (fix1 R6).
  // `draftDisplay` (lib, con test) decide che cosa mostrare; qui c'e' solo lo
  // stato grezzo del testo digitato.
  const [saldoDraft, setSaldoDraft] = useState<string | null>(null);
  const [accontoDraft, setAccontoDraft] = useState<string | null>(null);
  // Lo stato del `Select` «N rate uguali»: l'opzione che il piano ATTUALE
  // rispecchia davvero, o "" (stato neutro) dopo un ritocco a mano di una
  // singola rata (fix1 R6).
  const rateSelected = rateSelectValue(tribPlan?.amounts ?? [], tribPlan?.rateizzato ?? 0, opzioniRate);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Aliquota</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota effettiva {p.baseYear}</div>
                <div className="text-xs text-muted-foreground">imposte / utile ante imposte</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm tabular-nums text-foreground">{pct1(effectiveRate)}</span>
                {plan.source === "effettiva" && <Badge variant="secondary">usata dal piano</Badge>}
              </div>
            </div>

            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota forzata</div>
                <div className="text-xs text-muted-foreground">
                  vuota = usa l&apos;effettiva, o {pct1(DEFAULT_TAX_RATE)} se non derivabile
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  // 80 px non bastavano nemmeno al segnaposto: a schermo si
                  // leggeva «auto :». Qui ci sta il segnaposto e ci sta un
                  // valore digitato di quattro cifre e una virgola.
                  className="w-28 text-right"
                  aria-label="Aliquota forzata"
                  placeholder={TAX_RATE_PLACEHOLDER}
                  value={taxRateDisplay}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    const v = raw === "" ? DEFAULT_TAX_RATE : (parseFieldValue("tax_rate", raw) ?? DEFAULT_TAX_RATE);
                    p.updateAll("tax_rate", v);
                  }}
                />
                <span className="text-xs text-muted-foreground">%</span>
              </div>
            </div>

            {/* Nel caso comune questa riga ripeterebbe numero e badge di
                quella dell'aliquota effettiva: `addsInformation` (deciso in
                lib/budget-tax-rate.ts, col suo test) dice quando serve. */}
            {plan.addsInformation && (
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
                <div>
                  <div className="text-sm font-medium text-foreground">Aliquota usata dal piano</div>
                  {plan.nota && <div className="text-xs text-muted-foreground">{plan.nota}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm tabular-nums text-foreground">{plan.value}</span>
                  <Badge variant={plan.source === "effettiva" ? "secondary" : "outline"}>
                    {plan.sourceLabel}
                  </Badge>
                </div>
              </div>
            )}

            <div>
              <YearInputTable
                forecastYears={p.forecastYears}
                baseYear={p.baseYear}
                assumptions={p.assumptions}
                update={p.update}
                rows={ADVANCES_ROWS}
              />
            </div>
          </CardContent>
        </Card>

        <TaxTemporaryDifferencesGrid
          forecastYears={p.forecastYears}
          assumptions={p.assumptions}
          onUpdate={p.updateTemporaryDifferences}
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pagamento dei debiti tributari</CardTitle>
            <CardDescription>
              debito tributario al 31/12/{p.baseYear}: {euro(opening)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {baseBs && firstYear !== undefined ? (
              <>
                <TribRow
                  label="Saldo dell'anno precedente"
                  small="si versa per intero nel primo anno di piano"
                >
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      step={100}
                      className="w-36 text-right"
                      aria-label="Saldo dell'anno precedente"
                      placeholder="0"
                      value={draftDisplay(saldoDraft, tribPlan ? tribPlan.saldo : opening)}
                      onChange={(e) => {
                        setSaldoDraft(e.target.value);
                        setPregresso(withSaldo(pregresso, opening, numOrNull(e.target.value)));
                      }}
                      onBlur={() => setSaldoDraft(null)}
                    />
                    <span className="text-xs text-muted-foreground">€</span>
                  </div>
                </TribRow>

                <TribRow
                  label="Rateizzato"
                  small="ciò che il saldo non copre: si scadenzia nel piano qui sotto"
                >
                  {/* In sola lettura per costruzione: saldo e rateizzato devono
                      sommare l'apertura, e due caselle indipendenti farebbero
                      salvare piani che il server rifiuta. */}
                  <span className="text-sm tabular-nums text-foreground">
                    {euro(tribPlan ? tribPlan.rateizzato : 0)}
                  </span>
                </TribRow>

                <div className="flex items-center justify-between gap-3 pt-1">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Piano delle rate
                  </p>
                  {opzioniRate.length > 0 && (
                    <Select
                      // Controllato: dopo un ritocco a mano su una singola
                      // rata (`PregressoTable` -> `withRate`) `rateSelected`
                      // torna "" e il Select mostra di nuovo il segnaposto
                      // neutro invece dell'ultima scelta, che non e' piu'
                      // quella vera (fix1 R6).
                      value={rateSelected}
                      onValueChange={(v) => setPregresso(withRateUguali(pregresso, opening, Number(v)))}
                    >
                      <SelectTrigger className="h-8 w-36 text-xs" aria-label="Rate uguali">
                        <SelectValue placeholder="Rate uguali" />
                      </SelectTrigger>
                      <SelectContent>
                        {opzioniRate.map((n) => (
                          <SelectItem key={n} value={String(n)}>{n} rate uguali</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                {/* La stessa tabella del passo 6, su una riga sola: la massa
                    che scadenzia e' il RATEIZZATO, non l'apertura — il saldo
                    non entra nel runoff nemmeno nel motore. */}
                <PregressoTable
                  keys={TRIBUTARI_KEYS}
                  masses={tributariMasses(pregresso, opening)}
                  pregresso={tributariTabella(pregresso, opening)}
                  forecastYears={p.forecastYears}
                  baseYear={p.baseYear}
                  mode="eur"
                  massLabel="Rateizzato"
                  nota={TRIBUTARI_TABELLA_NOTA}
                  errors={errors}
                  onChange={(next) =>
                    setPregresso(withRate(pregresso, opening, next.debiti_tributari?.amounts ?? []))}
                />

                <TribRow label="Acconto sull'imposta dell'anno prima" small={ACCONTO_CHIOSA}>
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      max={200}
                      step={5}
                      className="w-24 text-right"
                      aria-label="Acconto sull'imposta dell'anno prima"
                      placeholder={String(DEFAULT_ACCONTO_PCT)}
                      value={draftDisplay(accontoDraft, accontoPctValue(pregresso))}
                      onChange={(e) => {
                        setAccontoDraft(e.target.value);
                        setPregresso(withAccontoPct(pregresso, opening, numOrNull(e.target.value)));
                      }}
                      onBlur={() => setAccontoDraft(null)}
                    />
                    <span className="text-xs text-muted-foreground">%</span>
                  </div>
                </TribRow>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                Il bilancio dell&apos;anno base non è ancora disponibile: senza quel saldo non c&apos;è nulla da
                scadenziare.
              </p>
            )}

            {preview.pregressoIgnored && (
              <div className="flex gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{PREGRESSO_IGNORED_AVVISO}</span>
              </div>
            )}

            <Accordion type="single" collapsible>
              <AccordionItem value="manuale" className="border-b-0">
                <AccordionTrigger className="text-sm font-medium">Posizione tributaria manuale</AccordionTrigger>
                <AccordionContent className="space-y-2">
                  <p className="text-xs text-muted-foreground">{MANUAL_TAX_AVVISO}</p>
                  <YearInputTable
                    forecastYears={p.forecastYears}
                    baseYear={p.baseYear}
                    assumptions={p.assumptions}
                    update={p.update}
                    rows={tributariRows}
                  />
                  {/* Il controllo che sulla via automatica non governa nulla non
                      si mostra inerte: sparisce, e questa riga dice perche'. */}
                  {!manual && (
                    <p className="text-[11px] text-muted-foreground">{SP17E_NOTA_AUTOMATICA}</p>
                  )}
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3 lg:sticky lg:top-4">
        <PreviewPanel
          title="Imposte e risultato netto"
          baseYear={p.baseYear}
          years={preview.years}
          rows={preview.rows}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        />
        <p className="text-xs text-muted-foreground">
          È l&apos;ultimo passo: il previsionale completo si legge e si ritocca nelle tab CE Prev. e SP Prev.
        </p>
      </div>
    </div>
  );
}
