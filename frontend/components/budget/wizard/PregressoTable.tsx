"use client";

// La tabella dello scadenziamento del pregresso di circolante (passo 6 del
// wizard ipotesi, task-7-brief.md): una riga per saldo, una colonna per anno
// di piano, il residuo in coda.
//
// Presentazionale. Ogni decisione — che cosa mostra una cella nelle due
// modalita', che cosa scrive un tocco, quanto resta dopo l'ultimo anno, e che
// cosa il previsionale fara' della voce — sta in lib/budget-pregresso-tabella.ts
// (con lib/budget-pregresso-circolante.ts sotto), provata in environment: node.
// Qui non si valida e non si tronca nulla: superare la massa di apertura e' un
// errore, e gli errori arrivano gia' fatti da `validatePregresso`.
import type { JSX } from "react";
import { Fragment, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, CircleOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { euro, numOrNull } from "@/lib/budget-format";
import type { Pregresso, PregressoKey } from "@/types/api";
import {
  PREGRESSO_VIA_USCITA,
  cellPlaceholder,
  cellValue,
  pregressoRighe,
  residualCell,
  withCell,
  type PregressoMode,
  type PregressoRiga,
  type PregressoTarget,
} from "@/lib/budget-pregresso-tabella";

interface CellaProps {
  riga: PregressoRiga;
  yearIndex: number;
  year: number;
  mode: PregressoMode;
  target: PregressoTarget;
  onWrite: (value: number | null) => void;
  /** L'inesigibile scadenziato che un override del CE ha impedito di
   *  scaricare, per questo anno (rilievo 6): marca la cella dove l'utente ha
   *  scritto la svalutazione, non solo l'anteprima a destra. */
  warning?: string;
}

function Cella({ riga, yearIndex, year, mode, target, onWrite, warning }: CellaProps): JSX.Element {
  const v = cellValue(riga.plan, yearIndex, mode, target);
  return (
    <td className="px-1 py-1 text-right">
      <Input
        type="number"
        min={0}
        step={mode === "pct" ? 0.1 : 100}
        className={cn(
          "h-8 w-full min-w-[84px] text-right",
          warning && "border-amber-500 focus-visible:ring-amber-500",
        )}
        aria-label={`${riga.label}${target === "writeoff" ? " — inesigibile" : ""} ${year}`}
        title={warning}
        placeholder={cellPlaceholder(riga.plan, yearIndex, mode)}
        value={v === null ? "" : v}
        onChange={(e) => onWrite(numOrNull(e.target.value))}
      />
    </td>
  );
}

export function PregressoTable(props: {
  /** `readonly` invece di `PregressoKey[]`: la tabella non muta l'elenco, e
   *  cosi' `TABELLA_KEYS` si passa senza un cast che toglie il `readonly`. */
  keys: readonly PregressoKey[];
  masses: Record<PregressoKey, number>;
  /** La massa OLTRE l'esercizio di ciascun saldo (rilievo 1): condiziona la
   *  nota di destino di `debiti_fornitori`/`crediti_commerciali`. Facoltativa
   *  perche' il passo 7 (tributari) non ne ha una da passare. */
  massesLong?: Record<PregressoKey, number>;
  pregresso: Pregresso;
  forecastYears: number[];
  baseYear: number;
  mode: PregressoMode;
  onChange: (next: Pregresso) => void;
  errors: string[];
  /** La riga in coda alla tabella. Il default e' la via d'uscita del passo 6
   *  (rimettere a bilancio una voce che il piano non rigenera); il passo 7 ne
   *  passa una propria, perche' li' non c'e' nessuna voce che si estingue. */
  nota?: string;
  /** Il titolo della colonna delle masse. Al passo 7 la massa non e' il saldo
   *  dell'anno base ma il RATEIZZATO che se ne e' dichiarato. */
  massLabel?: string;
  /** L'inesigibile non scaricato, per anno (rilievo 6): marca la cella «di
   *  cui inesigibile» invece di lasciare l'avviso solo nell'anteprima. Il
   *  solo saldo con `writeoff` e' `crediti_commerciali`, quindi al passo 7
   *  questa mappa non serve mai. */
  writeoffIgnored?: Record<number, string>;
}): JSX.Element {
  const { keys, masses, pregresso, forecastYears, baseYear, mode, onChange, errors, writeoffIgnored } = props;
  const nota = props.nota ?? PREGRESSO_VIA_USCITA;
  const [aperti, setAperti] = useState<Record<string, boolean>>({});

  const righe = pregressoRighe(keys, masses, pregresso, props.massesLong);
  const last = forecastYears.length - 1;
  const hasWriteoffIgnored = Object.keys(writeoffIgnored ?? {}).length > 0;

  const write = (key: PregressoKey, yearIndex: number, target: PregressoTarget) => (value: number | null) =>
    onChange(withCell(pregresso, key, masses, yearIndex, value, mode, target));

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="px-2 py-1 text-left font-medium text-muted-foreground">Voce</th>
              <th className="px-2 py-1 text-right font-medium text-muted-foreground">
                {props.massLabel ?? `Saldo ${baseYear}`}
              </th>
              {forecastYears.map((y) => (
                <th key={y} className="px-1 py-1 text-right font-medium text-muted-foreground">{y}</th>
              ))}
              <th className="px-2 py-1 text-right font-medium text-muted-foreground">Residuo</th>
            </tr>
          </thead>
          <tbody>
            {righe.map((riga) => {
              const aperto = Boolean(aperti[riga.key]);
              const residuo = residualCell(riga.plan, last);
              return (
                <Fragment key={riga.key}>
                <tr className="border-b border-border/50 align-top">
                  <td className="px-2 py-1">
                    <div className="font-medium text-foreground">{riga.label}</div>
                    <div className="mt-0.5 flex items-start gap-1 text-[11px] text-muted-foreground">
                      {/* Il cerchio sbarrato e' la SOLA sorpresa da segnalare:
                          la voce che si dichiara come le altre e resta a zero.
                          Chi si rigenera — dal volume o dalle imposte — porta
                          la freccia. */}
                      {riga.destino === "estingue"
                        ? <CircleOff className="mt-0.5 h-3 w-3 shrink-0" />
                        : <RefreshCw className="mt-0.5 h-3 w-3 shrink-0" />}
                      <span>{riga.destinoNota}</span>
                    </div>
                    {/* Un accordion vero (components/ui/accordion) non puo'
                        stare dentro un <tbody> senza rompere la tabella: qui
                        l'apri/chiudi e' lo stesso gesto, e la riga
                        dell'inesigibile resta una <tr> valida. */}
                    {riga.writeoff && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-1 h-6 px-1 text-[11px] font-normal text-muted-foreground"
                        aria-expanded={aperto}
                        onClick={() => setAperti((prev) => ({ ...prev, [riga.key]: !prev[riga.key] }))}
                      >
                        {aperto ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                        di cui inesigibile
                        {/* Visibile anche a riga chiusa: l'inesigibile non
                            scaricato (rilievo 6) altrimenti resterebbe
                            invisibile finche' nessuno apre l'accordion. */}
                        {hasWriteoffIgnored && (
                          <AlertTriangle
                            className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400"
                            aria-label="inesigibile non scaricato in almeno un anno"
                          />
                        )}
                      </Button>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1 text-right text-muted-foreground">{euro(riga.mass)}</td>
                  {forecastYears.map((y, i) => (
                    <Cella
                      key={y}
                      riga={riga}
                      yearIndex={i}
                      year={y}
                      mode={mode}
                      target="amounts"
                      onWrite={write(riga.key, i, "amounts")}
                    />
                  ))}
                  <td className={cn("whitespace-nowrap px-2 py-1 text-right font-medium",
                    residuo === 0 && "text-muted-foreground")}>
                    {euro(residuo)}
                  </td>
                </tr>
                {/* La riga dell'inesigibile e' una <tr> SORELLA, subito sotto
                    la sua: annidarla dentro l'altra romperebbe la tabella. */}
                {riga.writeoff && aperto && (
                  <tr className="border-b border-border/50 bg-muted/40">
                    <td className="px-2 py-1 pl-6 text-[11px] text-muted-foreground">
                      {riga.label} · di cui inesigibile
                    </td>
                    <td className="px-2 py-1" />
                    {forecastYears.map((y, i) => (
                      <Cella
                        key={y}
                        riga={riga}
                        yearIndex={i}
                        year={y}
                        mode={mode}
                        target="writeoff"
                        onWrite={write(riga.key, i, "writeoff")}
                        warning={writeoffIgnored?.[y]}
                      />
                    ))}
                    <td className="px-2 py-1" />
                  </tr>
                )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {errors.length > 0 && (
        <ul className="space-y-0.5 text-xs text-destructive">
          {errors.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      )}

      <p className="text-[11px] text-muted-foreground">{nota}</p>
    </div>
  );
}
