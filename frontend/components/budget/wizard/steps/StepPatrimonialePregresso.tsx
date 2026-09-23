"use client";

// Passo 5 del wizard ipotesi (spec 2026-09-15 §4.5), PRIMA parte: come si
// chiude cio' che era gia' in bilancio al 31/12 dell'anno base. Le voci OLTRE
// 12 mesi si scadenziano a mano qui — i tributari rateizzati compresi, da
// decisione del proprietario del 2026-09-15 (§3, §9.1, Task 13b): saldo,
// rateizzato e acconto restano al passo 7, solo le rate si scrivono qui. Le
// due card dei finanziamenti (banche, altri finanziatori) arrivano col Task
// 14 e il loro posto in questa griglia e' gia' deciso: sotto, a tutta
// larghezza.
//
// Presentazionale: le masse, il piano di base, gli stati della colonna
// «resta» e i flussi del pannello stanno in `lib/budget-pregresso-oltre.ts` e
// `lib/budget-pregresso-flussi.ts`, provati in `environment: node`. Nessun
// numero e' ricalcolato qui: l'anteprima legge i `details` della POST
// /preview, e il previsionale lo fa il motore in Python (un solo motore).
//
// L'unica scrittura che l'utente NON ha innescato e' il piano di base dei
// saldi a breve (i tributari compresi, quando c'e' massa da rateizzare), in
// un effetto una tantum: `pianoBase` restituisce l'oggetto ricevuto quando il
// piano c'e' gia', quindi l'effetto si posa da solo invece di ri-innescarsi
// (CLAUDE.md, «un effetto non dipende mai da cio' che lui stesso scrive»). La
// card lo dice: «nessun piano da impostare».
import type { JSX, ReactNode } from "react";
import { useEffect, useMemo } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NumericDraftInput } from "@/components/budget/PercentInput";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { euro, numOrNull } from "@/lib/budget-format";
import { parseFieldValue } from "@/lib/budget-field-rules";
import { openingMasses, validatePregresso } from "@/lib/budget-pregresso-circolante";
import {
  FORNITORI_AVVISO_RIGA, OLTRE_KEYS, OLTRE_NOTA, OLTRE_STATI, PREGRESSO_VUOTO,
  breveRows, massaBreve, oltreRows, pianoBase, tributariOltreRow, withNonIncassato, withOltreAmount,
  withTributariAmount, type OltreKey, type OltreRow,
} from "@/lib/budget-pregresso-oltre";
import { flussiPregresso } from "@/lib/budget-pregresso-flussi";
import { fornitoriZeroAvviso } from "@/lib/budget-fornitori-zero";
import { previewNotice } from "@/lib/budget-preview-notice";
import { cn } from "@/lib/utils";
import type { StepProps } from "../types";
import { PreviewPanel } from "../PreviewPanel";
import { PregressoBancheCard } from "./PregressoBancheCard";
import { PregressoAltriFinanziatoriCard } from "./PregressoAltriFinanziatoriCard";

/** Il colore del chip e' stile, la PAROLA e' decisione: arriva da
 *  `OLTRE_STATI` insieme allo stato che `oltreRows` ha scelto. Il vocabolario
 *  `Tono`/`CHIP_CLS` e' lo stesso di `PregressoBancheCard.tsx` (Task 14, le
 *  due card si affiancano nella stessa schermata): se un domani si estrae un
 *  `Chip` condiviso, qui si sostituisce un componente con l'altro. */
type Tono = "ok" | "avviso" | "errore" | "neutro";

const CHIP_CLS: Record<Tono, string> = {
  ok: "bg-green-500/15 text-green-700 dark:text-green-400",
  avviso: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  errore: "bg-red-500/15 text-red-700 dark:text-red-400",
  neutro: "bg-muted text-muted-foreground",
};

/** Decisone 7: nessuno stato di questa tabella blocca il piano, e solo
 *  «oltre il saldo» merita il rosso — perche' e' l'unico che dice «hai scritto
 *  piu' di quanto il bilancio base portava». Il salvataggio lo rifiuta con
 *  `validatePregresso`, che qui sotto scrive la ragione. */
const TONO: Record<OltreRow["stato"], Tono> = {
  chiuso: "ok",
  "resta aperto": "neutro",
  "nessun movimento nel piano": "neutro",
  "oltre il saldo": "errore",
  "oltre il piano": "neutro",
};

function Chip(props: { tono: Tono; children: string; className?: string }): JSX.Element {
  return (
    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", CHIP_CLS[props.tono], props.className)}>
      {props.children}
    </span>
  );
}

/** Etichetta / nota piccola a sinistra, valore o chip a destra: lo schema di
 *  `ScheduleRow` (StepPregressoNuovo), qui senza controllo perche' il breve
 *  non si imposta — si legge. */
function Riga(props: { label: string; small: string; alert?: string; children: ReactNode }): JSX.Element {
  const { label, small, alert, children } = props;
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 py-2.5 last:border-b-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{label}</div>
        {alert ? (
          <div className="flex gap-1.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{alert}</span>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">{small}</div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2 text-sm tabular-nums">{children}</div>
    </div>
  );
}

export function StepPatrimonialePregresso(p: StepProps): JSX.Element {
  const baseBs = p.historical[p.baseYear]?.balance;
  const baseInc = p.historical[p.baseYear]?.income;
  const firstYear = p.forecastYears[0];
  const annoSuccessivo = firstYear ?? p.baseYear + 1;
  const { updatePregresso } = p;

  // La stessa decisione del passo 4 (`StepCircolante`), qui nella forma breve
  // che sta nella riga: i giorni di pagamento non si calcolano, e il breve
  // dei fornitori che questo passo mostra viene da un'altra parte.
  const avviso = useMemo(
    () => fornitoriZeroAvviso(p.baseYear, baseBs, baseInc),
    [p.baseYear, baseBs, baseInc],
  );

  // Il piano e' UNO per scenario e vive nella riga del primo anno di piano
  // (spec §3.5): da qui in poi lo si legge e lo si scrive sempre li'. Il
  // ripiego e' una costante di modulo, non un `{}` letterale: dentro la
  // `useMemo` il letterale cambierebbe identita' a ogni ricomposizione.
  const pregressoSalvato = p.assumptions[firstYear]?.pregresso;
  const pregresso = useMemo(
    () => pianoBase(baseBs, p.forecastYears, pregressoSalvato ?? PREGRESSO_VUOTO),
    [baseBs, p.forecastYears, pregressoSalvato],
  );
  useEffect(() => {
    // Con l'identita' di `pianoBase` questo corpo si posa da solo: dopo la
    // prima scrittura `pregresso === pregressoSalvato`, e un'idratazione
    // arrivata piu' tardi (che sostituisce la mappa delle ipotesi) lo fa
    // ripartire una volta sola. Un ref messo qui sopra come cancello
    // fermerebbe la composizione al primo render, cioe' PRIMA che le ipotesi
    // salvate arrivino: il piano resterebbe senza i saldi a breve, tributari
    // rateizzati compresi.
    if (!baseBs || firstYear === undefined) return;
    if (pregresso !== pregressoSalvato) updatePregresso(pregresso);
  }, [baseBs, firstYear, pregresso, pregressoSalvato, updatePregresso]);

  // Il saldo tributario a breve mostrato qui e' quello del piano (Task 13b):
  // un piano salvato dal vecchio passo 7 puo' avere un saldo diverso da
  // `sp16e`, e questa riga deve mostrare cio' che il motore paga davvero, non
  // ricalcolarlo dal bilancio.
  const righeBreve = useMemo(
    () => breveRows(baseBs, p.baseYear, avviso ? FORNITORI_AVVISO_RIGA : null, pregresso),
    [baseBs, p.baseYear, avviso, pregresso],
  );

  const righeOltre = useMemo(
    () => oltreRows(baseBs, pregresso, p.forecastYears),
    [baseBs, pregresso, p.forecastYears],
  );
  // La quinta riga della tabella «oltre 12 mesi»: `null` quando non c'e' nulla
  // da rateizzare (nessun piano salvato e `sp17e = 0`), e in quel caso la riga
  // non compare affatto — niente scadenza dichiarata che nessuno ha
  // dichiarato.
  const rigaTributari = useMemo(
    () => tributariOltreRow(baseBs, pregresso, p.forecastYears),
    [baseBs, pregresso, p.forecastYears],
  );
  // Diagnostica, non correzione: il messaggio e' lo stesso che il salvataggio
  // opporrebbe, ma qui arriva mentre si digita. `pregresso` porta anche il
  // piano tributario quando c'e', quindi la validazione lo copre gia'.
  const errori = useMemo(
    () => (baseBs ? validatePregresso(pregresso, openingMasses(baseBs), p.forecastYears.length) : []),
    [pregresso, baseBs, p.forecastYears.length],
  );
  const breve = useMemo(
    () => Object.fromEntries(OLTRE_KEYS.map((k) => [k, massaBreve(baseBs, k)])) as Record<OltreKey, number>,
    [baseBs],
  );

  // Il pannello legge gli anni CHE IL MOTORE HA PRODOTTO, non l'orizzonte
  // chiesto: un piano che si ferma al secondo anno non mostra una colonna
  // fantasma (CLAUDE.md, «leggere `forecast_generated`, non l'HTTP 200»).
  const anniMotore = p.preview.data?.forecast_years ?? [];
  const righeFlussi = useMemo(
    () => flussiPregresso(anniMotore, breve),
    // `anniMotore` e' un letterale `[]` quando la risposta non c'e': si depende
    // dalla risposta, non dall'array derivato.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [p.preview.data, breve],
  );

  // `items-start`: senza, la colonna si stira a tutta l'altezza della riga e
  // il `lg:sticky` dell'anteprima non ha effetto.
  return (
    <>
      <div className="grid items-start gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">A breve · si chiudono nel {annoSuccessivo}</CardTitle>
              <CardDescription>nessun piano da impostare</CardDescription>
            </CardHeader>
            <CardContent>
              {righeBreve.map((r) => (
                <Riga key={r.label} label={r.label} small={r.small} alert={r.alert}>
                  {r.dir && (
                    <Chip tono={r.dir === "in" ? "ok" : "errore"}>
                      {r.dir === "in" ? "incasso" : "pagamento"}
                    </Chip>
                  )}
                  <span>{euro(r.importo)}</span>
                </Riga>
              ))}
              {!baseBs && (
                <p className="text-xs text-muted-foreground">
                  Il bilancio dell&apos;anno base non è ancora disponibile: senza quei saldi non c&apos;è nulla da
                  scadenziare.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="flex gap-2 rounded-md bg-muted p-3 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Un credito poco esigibile o un debito rateizzato non va lasciato a breve: spostalo{" "}
              <b className="text-foreground">oltre 12 mesi in Rettifiche</b> (o nell&apos;infrannuale) e scadenzialo
              qui sotto.
            </span>
          </div>
        </div>

        <PreviewPanel
          title="Scadenziamento pregresso · flussi di cassa"
          baseYear={p.baseYear}
          years={anniMotore.map((y) => y.year)}
          rows={righeFlussi}
          loading={p.preview.loading}
          error={previewNotice(p.preview)}
        />
      </div>

      <div className="mt-4 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Altre voci pregresse · scadenziamento a mano</CardTitle>
            <CardDescription>
              Importi incassati o pagati per le voci oltre 12 mesi; variazione del saldo storico per i crediti tributari a breve.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-2 py-1.5 text-left text-xs font-semibold text-foreground">Voce</th>
                    <th className="px-2 py-1.5 text-right text-xs font-semibold text-muted-foreground">
                      al 31/12/{p.baseYear}
                    </th>
                    {p.forecastYears.map((y) => (
                      <th key={y} className="px-2 py-1.5 text-right text-xs font-semibold text-primary">{y}</th>
                    ))}
                    <th className="px-2 py-1.5 text-right text-xs font-semibold text-muted-foreground">resta</th>
                  </tr>
                </thead>
                <tbody>
                  {righeOltre.map((r) => (
                    <tr key={r.key} className="border-b border-border/50">
                      <td className="px-2 py-1.5 align-top">
                        <div className="font-medium text-foreground">{r.label}</div>
                        <div className="text-[11px] text-muted-foreground">{OLTRE_NOTA[r.key]}</div>
                        {r.key === "crediti_commerciali" && (
                          <div className="mt-1.5 flex items-center gap-2">
                            <Checkbox
                              id="oltre-crediti-non-incassati"
                              checked={r.nonIncassato}
                              onCheckedChange={(c) =>
                                updatePregresso(withNonIncassato(baseBs, pregresso, p.forecastYears, c === true))
                              }
                            />
                            <Label
                              htmlFor="oltre-crediti-non-incassati"
                              className="text-[11px] font-normal text-muted-foreground"
                            >
                              non incassati nel piano (es. infragruppo)
                            </Label>
                          </div>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(r.opening)}
                      </td>
                      {p.forecastYears.map((y, i) => (
                        <td key={y} className="px-2 py-1.5 align-top" title={r.disabled ? "caselle spente: i crediti sono dichiarati non incassati nel piano" : undefined}>
                          <input
                            type="number"
                            inputMode="decimal"
                            step="1000"
                            min={0}
                            disabled={r.disabled}
                            aria-label={`${r.label} — ${y}`}
                            placeholder={r.disabled ? "—" : "0"}
                            value={r.amounts[i] ? String(r.amounts[i]) : ""}
                            onChange={(e) =>
                              updatePregresso(
                                withOltreAmount(baseBs, pregresso, p.forecastYears, r.key, i, numOrNull(e.target.value)),
                              )
                            }
                            className="w-24 rounded border border-input bg-transparent px-2 py-1 text-right text-xs tabular-nums text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:border-dashed disabled:bg-muted/50 disabled:text-muted-foreground"
                          />
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(r.resta)}
                        <Chip tono={TONO[r.stato]} className="ml-1.5">{OLTRE_STATI[r.stato]}</Chip>
                      </td>
                    </tr>
                  ))}
                  {baseBs && (numOrNull(baseBs.sp06e_crediti_tributari_breve) ?? 0) > 0 && (
                    <tr className="border-b border-border/50">
                      <td className="px-2 py-1.5 align-top">
                        <div className="font-medium text-foreground">Crediti tributari pregressi · entro 12 mesi</div>
                        <div className="text-[11px] text-muted-foreground">
                          Variazione % del credito storico; gli eventuali crediti da acconti restano separati.
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(numOrNull(baseBs.sp06e_crediti_tributari_breve))}
                      </td>
                      {p.forecastYears.map((year) => {
                        const storico = p.preview.data?.forecast_years.find((item) => item.year === year)
                          ?.details?.imposte?.crediti_tributari_consuntivo;
                        return (
                          <td key={year} className="px-2 py-1.5 align-top">
                            <div className="flex items-center justify-end gap-1">
                              <NumericDraftInput
                                value={p.assumptions[year]?.sp06e_growth_pct ?? 0}
                                allowNegative
                                ariaLabel={`Variazione crediti tributari storici ${year}`}
                                className="w-20 rounded border border-input bg-background px-2 py-1 text-right text-xs tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
                                onRawChange={(raw) => p.update(year, "sp06e_growth_pct", parseFieldValue("sp06e_growth_pct", raw))}
                              />
                              <span className="text-xs text-muted-foreground">%</span>
                            </div>
                            <div className="mt-1 text-right text-[11px] tabular-nums text-muted-foreground">
                              {euro(numOrNull(storico))}
                            </div>
                          </td>
                        );
                      })}
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(numOrNull(p.preview.data?.forecast_years.find(
                          (item) => item.year === p.forecastYears.at(-1),
                        )?.details?.imposte?.crediti_tributari_consuntivo))}
                      </td>
                    </tr>
                  )}
                  {baseBs && (numOrNull(baseBs.sp07e_crediti_tributari_lungo) ?? 0) > 0 && (
                    <tr className="border-b border-border/50">
                      <td className="px-2 py-1.5 align-top">
                        <div className="font-medium text-foreground">Crediti tributari pregressi · oltre 12 mesi</div>
                        <div className="text-[11px] text-muted-foreground">
                          Oggi seguono la variazione complessiva dei crediti oltre 12 mesi; non hanno rate dedicate.
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(numOrNull(baseBs.sp07e_crediti_tributari_lungo))}
                      </td>
                      {p.forecastYears.map((year) => (
                        <td key={year} className="px-2 py-1.5 text-right align-top text-xs tabular-nums text-muted-foreground">
                          {euro(numOrNull(p.preview.data?.forecast_years.find(
                            (item) => item.year === year,
                          )?.balance_sheet.sp07e_crediti_tributari_lungo))}
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(numOrNull(p.preview.data?.forecast_years.find(
                          (item) => item.year === p.forecastYears.at(-1),
                        )?.balance_sheet.sp07e_crediti_tributari_lungo))}
                      </td>
                    </tr>
                  )}
                  {/* I tributari rateizzati (Task 13b, decisione del
                      proprietario del 2026-09-15, §3/§9.1): saldo, rateizzato
                      e acconto restano al passo 7 (`tributariPlanOrDefault`,
                      `withRate`, invariati), qui si scrive solo la rata
                      dell'anno. Niente riga se non c'e' nulla da rateizzare:
                      `rigaTributari` e' `null` senza piano salvato e con
                      `sp17e = 0`. */}
                  {rigaTributari && (
                    <tr key={rigaTributari.key} className="border-b border-border/50">
                      <td className="px-2 py-1.5 align-top">
                        <div className="font-medium text-foreground">{rigaTributari.label}</div>
                        <div className="text-[11px] text-muted-foreground">
                          Rate della rateizzazione: escono di cassa nell&apos;anno. Il saldo a breve si paga nel{" "}
                          {annoSuccessivo}.
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(rigaTributari.opening)}
                      </td>
                      {p.forecastYears.map((y, i) => (
                        <td key={y} className="px-2 py-1.5 align-top">
                          <input
                            type="number"
                            inputMode="decimal"
                            step="1000"
                            min={0}
                            aria-label={`${rigaTributari.label} — ${y}`}
                            placeholder="0"
                            value={rigaTributari.amounts[i] ? String(rigaTributari.amounts[i]) : ""}
                            onChange={(e) =>
                              updatePregresso(
                                withTributariAmount(baseBs, pregresso, p.forecastYears, i, numOrNull(e.target.value)),
                              )
                            }
                            className="w-24 rounded border border-input bg-transparent px-2 py-1 text-right text-xs tabular-nums text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          />
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-2 py-1.5 text-right align-top text-xs tabular-nums">
                        {euro(rigaTributari.resta)}
                        <Chip tono={TONO[rigaTributari.stato]} className="ml-1.5">{OLTRE_STATI[rigaTributari.stato]}</Chip>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Per le voci scadenziabili, ciò che non incassi o paghi resta aperto in bilancio.
              Per i crediti tributari la colonna «resta» mostra il saldo storico previsto dal motore.
            </p>
            {errori.length > 0 && (
              <div className="mt-3 space-y-1 rounded-md bg-destructive/10 p-3 text-xs text-destructive">
                {errori.map((m) => (
                  <div key={m} className="flex gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{m}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <PregressoBancheCard {...p} />
        <PregressoAltriFinanziatoriCard {...p} />
      </div>
    </>
  );
}
