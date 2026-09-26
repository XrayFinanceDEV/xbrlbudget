"use client";

// Passo 7 del wizard ipotesi: imposte (spec 2026-09-08 §4.7, ridotto il
// 2026-09-15 all'aliquota e al pagamento dell'anno in corso — decisione del
// proprietario, Task 13b/16: saldo, rateizzato e rate dei debiti tributari
// si scadenziano al passo 5 «Patrimoniale pregresso»). È l'ULTIMO passo —
// non c'è un ottavo passo di riepilogo: il wizard si chiude qui e il
// previsionale completo si legge e si ritocca nelle tab CE Prev. e SP Prev.
// esistenti.
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
import { Button } from "@/components/ui/button";
import { useAliquotaProposta } from "@/hooks/use-queries";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { formatNumber, parseItalianAmount } from "@/lib/formatters";
import { euro, numOrNull, pct1 } from "@/lib/budget-format";
import {
  ACCONTO_CHIOSA,
  DEFAULT_ACCONTO_PCT,
  DEFAULT_TAX_RATE,
  MANUAL_TAX_AVVISO,
  PREGRESSO_IGNORED_AVVISO,
  SP17E_NOTA_AUTOMATICA,
  accontiRow,
  accontoPctValue,
  draftDisplay,
  impostePreview,
  manualTaxYears,
  spTributariRows,
  taxRateValue,
  tributariOpening,
  withAccontoPct,
} from "@/lib/budget-imposte-step";
import { planTaxRate, propostaLabel } from "@/lib/budget-tax-rate";
import { pianoBase } from "@/lib/budget-pregresso-oltre";
import { previewNotice } from "@/lib/budget-preview-notice";
import type { Pregresso } from "@/types/api";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { YearInputTable, type YearInputRow } from "../YearInputTable";


/** Riga «etichetta / nota piccola» a sinistra, controllo a destra. */
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
  // L'aliquota proposta dall'ultimo consuntivo depositato (commercialista,
  // 2026-09-18): il motore applica quella del piano, cosi' com'e'.
  const proposta = useAliquotaProposta(p.companyId, p.baseYear);

  const taxRate = taxRateValue(p.assumptions, p.forecastYears);
  // Quale aliquota il piano usera' davvero, e perche' (lib/budget-tax-rate.ts).
  const plan = useMemo(
    () => planTaxRate(proposta.data ?? null, p.assumptions, p.forecastYears),
    [proposta.data, p.assumptions, p.forecastYears],
  );

  const preview = useMemo(() => impostePreview(baseInc, p.preview.data), [baseInc, p.preview.data]);

  // La via manuale (percentuale di crescita sul debito sp16e) e' un'alternativa
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
  const variazioniCreditiStorici = p.forecastYears.flatMap((year) => {
    const raw = p.assumptions[year]?.sp06e_growth_pct;
    const value = raw == null ? 0 : Number(raw);
    return Number.isFinite(value) && value !== 0 ? [{ year, value }] : [];
  });

  // Il piano e' UNO per scenario e vive nelle ipotesi del PRIMO anno di piano
  // (spec §4.5): il motore lo legge da li', e scriverlo su ogni anno lo
  // farebbe applicare piu' volte. Saldo, rateizzato e rate si scadenziano al
  // passo 5 «Patrimoniale pregresso» — qui resta solo l'acconto, che governa
  // l'anno in corso, non il pregresso.
  const firstYear = p.forecastYears[0];
  const opening = useMemo(() => tributariOpening(baseBs), [baseBs]);
  const pregressoSalvato = p.assumptions[firstYear]?.pregresso;
  const pregresso = useMemo(() => (pregressoSalvato ?? {}) as Pregresso, [pregressoSalvato]);
  // Lo zero salvato e' «non dichiarato»: la casella resta vuota e dice
  // l'acconto che il motore applica (lib/budget-imposte-step.ts:accontiRow).
  const advancesRows: YearInputRow[] = useMemo(
    () => [{
      ...accontiRow(p.preview.data, accontoPctValue(pregresso)),
      offYears: yearsManuali,
      offYearsNote: "La crescita manuale dei debiti tributari non calcola gli acconti. Svuota Debiti tributari entro % per riattivarli.",
    }],
    [p.preview.data, pregresso, yearsManuali],
  );
  const setPregresso = (next: Pregresso) => {
    p.updatePregresso(next);
  };

  // Bozza locale della casella controllata (acconto): senza questo stato,
  // svuotare la casella col backspace la fa ricadere subito sul valore di
  // ripiego del piano SALVATO (100 per l'acconto) e la digitazione
  // successiva riparte da li' invece che da vuoto (fix1 R6). `draftDisplay`
  // (lib, con test) decide che cosa mostrare; qui c'e' solo lo stato grezzo
  // del testo digitato.
  const [accontoDraft, setAccontoDraft] = useState<string | null>(null);
  const [accontiStoriciDraft, setAccontiStoriciDraft] = useState<string | null>(null);
  const [accontiStoriciErrore, setAccontiStoriciErrore] = useState(false);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Aliquota</CardTitle>
            <CardDescription>
              Proposta dall&apos;ultimo bilancio depositato, mai da un infrannuale: puoi tenerla,
              mettere {pct1(DEFAULT_TAX_RATE)} (IRES + IRAP) o un&apos;altra aliquota.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota proposta</div>
                <div className="text-xs text-muted-foreground">{propostaLabel(proposta.data ?? null)}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm tabular-nums text-foreground">
                  {proposta.data ? pct1(proposta.data.aliquota) : "—"}
                </span>
                {plan.diversaDallaProposta && proposta.data && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => p.updateAll("tax_rate", Math.round(proposta.data!.aliquota * 100) / 100)}
                  >
                    Usa la proposta
                  </Button>
                )}
              </div>
            </div>

            <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
              <div>
                <div className="text-sm font-medium text-foreground">Aliquota del piano</div>
                <div className="text-xs text-muted-foreground">imposte correnti = utile ante imposte × aliquota</div>
              </div>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  className="w-28 text-right"
                  aria-label="Aliquota del piano"
                  value={taxRate.value ?? DEFAULT_TAX_RATE}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    const v = raw === "" ? DEFAULT_TAX_RATE : (parseFieldValue("tax_rate", raw) ?? DEFAULT_TAX_RATE);
                    p.updateAll("tax_rate", v);
                  }}
                />
                <span className="text-xs text-muted-foreground">%</span>
              </div>
            </div>

            {(plan.source === "sostituita" || plan.nota) && (
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 pb-2.5">
                <div>
                  <div className="text-sm font-medium text-foreground">Aliquota usata dal piano</div>
                  {plan.nota && <div className="text-xs text-muted-foreground">{plan.nota}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm tabular-nums text-foreground">{plan.value}</span>
                  <Badge variant="outline">{plan.sourceLabel}</Badge>
                </div>
              </div>
            )}

          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pagamento dei debiti tributari</CardTitle>
            <CardDescription>
              debito tributario al 31/12/{p.baseYear}: {euro(opening)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {baseBs && (
              <div className="rounded-md border border-border/60 p-3">
                <div className="text-sm font-medium">Crediti tributari del bilancio base</div>
                <div className="mb-3 text-xs text-muted-foreground">
                  Dei {euro(Number(baseBs.sp06e_crediti_tributari_breve ?? 0))} entro 12 mesi,
                  indica gli acconti d&apos;imposta già versati. Il resto ({euro(Math.max(0, Number(baseBs.sp06e_crediti_tributari_breve ?? 0) - Number(pregresso.acconti_tributari_storici ?? 0)))})
                  si scadenzia come «Altri crediti tributari» nel Patrimoniale pregresso.
                </div>
                <TribRow label="Acconti d'imposta già versati" small={`Compresi nei crediti tributari al 31/12/${p.baseYear}`}>
                  <div className="flex flex-col items-end gap-1">
                  <div className="flex items-center gap-2">
                    <Input
                      type="text" inputMode="decimal"
                      className="w-32 text-right" aria-label="Acconti d'imposta già versati nel bilancio base"
                      value={accontiStoriciDraft ?? formatNumber(Number(pregresso.acconti_tributari_storici ?? 0), 2)}
                      onChange={(e) => { setAccontiStoriciDraft(e.target.value); setAccontiStoriciErrore(false); }}
                      onBlur={() => {
                        if (accontiStoriciDraft === null) return;
                        const raw = accontiStoriciDraft.trim();
                        const value = raw === "" ? 0 : parseItalianAmount(raw);
                        if (value === null || value === undefined || value < 0 || value > Number(baseBs.sp06e_crediti_tributari_breve ?? 0)) {
                          setAccontiStoriciErrore(true);
                          return;
                        }
                        setPregresso(pianoBase(baseBs, p.forecastYears, { ...pregresso, acconti_tributari_storici: value }));
                        setAccontiStoriciDraft(null);
                      }}
                    />
                    <span className="text-xs text-muted-foreground">€</span>
                  </div>
                  {accontiStoriciErrore && <span className="text-xs text-destructive" role="alert">Inserisci un importo fra 0 e {euro(Number(baseBs.sp06e_crediti_tributari_breve ?? 0))}.</span>}
                  </div>
                </TribRow>
              </div>
            )}
            {variazioniCreditiStorici.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300">
                <span>
                  Variazioni % precedenti dei crediti tributari: {variazioniCreditiStorici.map(({ year, value }) => `${year}: ${pct1(value)}`).join(" · ")}.
                  {pregresso.crediti_tributari_breve
                    ? " Il calendario degli altri crediti tributari le sostituisce: rimuovile per evitare confusione."
                    : " Se non hai impostato il calendario degli altri crediti tributari, queste variazioni cambiano anche la cassa."}
                </span>
                <Button
                  type="button" variant="outline" size="sm"
                  onClick={() => variazioniCreditiStorici.forEach(({ year }) => p.update(year, "sp06e_growth_pct", null))}
                >
                  Rimuovi variazioni %
                </Button>
              </div>
            )}
            {manual && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300">
                <span>La crescita manuale dei debiti tributari disattiva i pagamenti negli anni selezionati.</span>
                <Button
                  type="button" variant="outline" size="sm"
                  onClick={() => p.forecastYears.forEach((year) => {
                    p.update(year, "sp16e_growth_pct", null);
                    p.update(year, "sp17e_growth_pct", null);
                  })}
                >
                  Ripristina saldo e acconti
                </Button>
              </div>
            )}
            {baseBs && firstYear !== undefined ? (
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
            ) : (
              <p className="text-xs text-muted-foreground">
                Il bilancio dell&apos;anno base non è ancora disponibile: senza quel saldo non c&apos;è nulla da
                scadenziare.
              </p>
            )}

            <YearInputTable
              forecastYears={p.forecastYears}
              baseYear={p.baseYear}
              assumptions={p.assumptions}
              update={p.update}
              rows={advancesRows}
              yearsAsRows
            />

            {/* Saldo, rateizzato e rate si scadenziano al passo 5, non qui
                (decisione del proprietario, 2026-09-15, Task 13b/16): questo
                rimando sostituisce i tre controlli che c'erano prima. */}
            <p className="text-xs text-muted-foreground">
              Debiti tributari al 31/12/{p.baseYear}: saldo e rate si scadenziano al passo 5 · Patrimoniale
              pregresso.
            </p>

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
                    yearsAsRows
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
