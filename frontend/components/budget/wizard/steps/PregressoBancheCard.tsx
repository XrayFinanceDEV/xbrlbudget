"use client";

// Passo 5 (II) del wizard ipotesi — card «Debiti verso banche» (spec
// 2026-09-15 §4.5, §5.2, §5.2-bis; Task 14). Divide i debiti bancari a breve
// in fidi/anticipi (`bank_lines_*`) e mutui, e scadenzia il capitale
// rimborsato anno per anno sui contratti pregressi (`financing_loans` con
// `opening_residual > 0`); i prestiti NUOVI (`amount > 0`) restano intatti,
// li scrive la card «Generato dal previsionale» di StepPatrimonialePregresso.
//
// Presentazionale: ogni decisione — separare pregresso da nuovo, riempire i
// rimborsi all'orizzonte, i tre controlli — sta in
// lib/budget-finanziamenti-pregresso.ts, provata in environment: node. Qui
// solo la resa e la ricomposizione di `financing_loans` = [...contratti
// pregressi aggiornati, ...prestiti nuovi] a ogni scrittura.
//
// Il coordinatore inserisce questa card in StepPatrimonialePregresso.tsx
// (Task 13), sotto la card «oltre 12 mesi»: riceve le stesse props di ogni
// altro passo (StepProps), che gia' porta updateFinancingLoans.
import type { JSX } from "react";
import { useEffect, useRef } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { euro, num } from "@/lib/budget-format";
import {
  contrattiPregressi,
  contrattoRows,
  controlliBanche,
  nuovoContratto,
  prestitiNuovi,
  quotaMutui,
  unisciContratti,
  withCampo,
  withRimborso,
  type Controllo,
  type ContrattoRow,
} from "@/lib/budget-finanziamenti-pregresso";
import { cn } from "@/lib/utils";
import type { FinancingLoanInput } from "@/types/api";
import type { StepProps } from "../types";

/**
 * `p.update` e' tipizzato su `number | boolean | null` (ogni altra voce del
 * wizard e' scalare numerica o booleana): `bank_lines_rule` e' la prima
 * stringa. Il widening resta LOCALE a questo file — `hooks/use-scenario-
 * assumptions.ts` e `components/budget/wizard/types.ts` non sono fra i file
 * di questo task, e a runtime `updateAssumption` scrive `[field]: value`
 * senza controllare il tipo, quindi il valore arriva intatto. Il coordinatore
 * puo' spostare il widening nella firma condivisa quando integra questa card.
 */
function updateAny(p: StepProps, year: number, field: string, value: number | string | boolean | null): void {
  (p.update as unknown as (y: number, f: string, v: number | string | boolean | null) => void)(year, field, value);
}

type Tono = "ok" | "avviso" | "errore" | "neutro";

const CHIP_CLS: Record<Tono, string> = {
  ok: "bg-green-500/15 text-green-700 dark:text-green-400",
  avviso: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  errore: "bg-red-500/15 text-red-700 dark:text-red-400",
  neutro: "bg-muted text-muted-foreground",
};

function Chip({ tono, children }: { tono: Tono; children: string }): JSX.Element {
  return <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", CHIP_CLS[tono])}>{children}</span>;
}

/** Solo «oltre il residuo» e' un errore vero: le altre tre righe della
 *  colonna «resta» sono neutre per costruzione (decisione 7, stessa logica
 *  della tabella «Altre voci oltre 12 mesi»: nessun blocco, nessun avviso). */
function statoTono(stato: ContrattoRow["stato"]): Tono {
  return stato === "oltre il residuo" ? "errore" : "neutro";
}

function ControlRow({ c, tono }: { c: Controllo; tono: Tono }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-muted p-2 text-xs">
      <span className="text-foreground">{c.testo}</span>
      <Chip tono={tono}>{c.esito}</Chip>
    </div>
  );
}

export function PregressoBancheCard(p: StepProps): JSX.Element {
  const baseBs = p.historical[p.baseYear]?.balance;
  const firstYear = p.forecastYears[0];
  const horizon = p.forecastYears.length;
  const riga = p.assumptions[firstYear];

  const bankLinesAmount = riga?.bank_lines_amount;
  const bankLinesRule = riga?.bank_lines_rule;

  // Scrittura una tantum alla prima visita di questo scenario (stessa
  // convenzione del piano base, Task 13): se lo scenario non ha ancora un
  // valore per i fidi, si scrivono `bank_lines_amount = 0` e la regola
  // «costante» UNA VOLTA sola per scenario — mai a ogni render, altrimenti un
  // valore salvato che arriva dopo l'idratazione verrebbe riscritto.
  const inizializzatoPer = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (p.scenarioId === null || firstYear === undefined) return;
    if (inizializzatoPer.current === p.scenarioId) return;
    inizializzatoPer.current = p.scenarioId;
    if (bankLinesAmount == null && bankLinesRule == null) {
      updateAny(p, firstYear, "bank_lines_amount", 0);
      updateAny(p, firstYear, "bank_lines_rule", "costante");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.scenarioId, firstYear, bankLinesAmount, bankLinesRule]);

  if (!baseBs || firstYear === undefined) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Debiti verso banche</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Il bilancio dell&apos;anno base non è ancora disponibile: senza quei saldi non c&apos;è nulla da
            dividere.
          </p>
        </CardContent>
      </Card>
    );
  }

  const debito = baseBankDebt(baseBs as unknown as Record<string, unknown>);
  const sp16a = num(baseBs.sp16a_debiti_banche_breve);
  const fidi = bankLinesAmount ?? 0;
  const regola = bankLinesRule ?? "costante";
  const tasso = riga?.bank_lines_rate ?? null;
  const quota = quotaMutui(baseBs, fidi);

  const loans = riga?.financing_loans ?? [];
  const pregressi = contrattiPregressi(loans);
  const nuovi = prestitiNuovi(loans);
  const rows = contrattoRows(pregressi, horizon);
  const controlli = controlliBanche(baseBs, fidi, pregressi, horizon, p.baseYear);

  const scriviContratti = (prossimi: FinancingLoanInput[]) => p.updateFinancingLoans(firstYear, [...prossimi, ...nuovi]);
  const onCampo = (k: number, field: "name" | "opening_residual" | "interest_rate", value: string | number | null) =>
    scriviContratti(withCampo(pregressi, k, field, value));
  const onRimborso = (k: number, i: number, value: number | null) =>
    scriviContratti(withRimborso(pregressi, k, i, value, horizon));
  const onAggiungi = () => scriviContratti([...pregressi, nuovoContratto(pregressi.length + 1, horizon)]);
  const onUnisci = () => scriviContratti(unisciContratti(pregressi, horizon));
  const onElimina = (k: number) => scriviContratti(pregressi.filter((_, idx) => idx !== k));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Debiti verso banche</CardTitle>
        <CardDescription>
          {euro(debito)} nel bilancio {p.baseYear} · di cui {euro(sp16a)} a breve
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-sm font-medium text-foreground">1 · Dividi i debiti a breve</p>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div>
              <label className="text-xs text-muted-foreground" htmlFor="bank-lines-rule">Regola</label>
              <Select value={regola} onValueChange={(v) => updateAny(p, firstYear, "bank_lines_rule", v)}>
                <SelectTrigger id="bank-lines-rule" className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="costante">Costanti</SelectItem>
                  <SelectItem value="ricavi">Seguono i ricavi</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground" htmlFor="bank-lines-amount">
                Fidi e anticipi su fatture €
              </label>
              <Input
                id="bank-lines-amount"
                type="number"
                min={0}
                step={1000}
                className="h-8"
                value={fidi}
                onChange={(e) => updateAny(p, firstYear, "bank_lines_amount", e.target.value === "" ? 0 : Number(e.target.value))}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground" htmlFor="bank-lines-rate">Tasso fidi e scoperto %</label>
              <Input
                id="bank-lines-rate"
                type="number"
                min={0}
                max={30}
                step={0.1}
                className="h-8"
                value={tasso ?? ""}
                onChange={(e) => updateAny(p, firstYear, "bank_lines_rate", e.target.value === "" ? null : Number(e.target.value))}
              />
            </div>
          </div>
          <div className="mt-2 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Quota dei mutui entro 12 mesi</span>
            <span className={cn("font-medium", quota < 0 && "text-red-600 dark:text-red-400")}>{euro(quota)}</span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Se la cassa va in negativo il piano riutilizza i fidi; oltre questo importo compare un avviso.
          </p>
        </div>

        <div>
          <p className="text-sm font-medium text-foreground">2 · Scadenzia i finanziamenti</p>
          {rows.length === 0 ? (
            <p className="mt-2 text-xs text-muted-foreground">Nessun finanziamento pregresso ancora scadenziato.</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-1 py-1 text-left font-medium text-muted-foreground">Finanziamento</th>
                    <th className="px-1 py-1 text-right font-medium text-muted-foreground">Residuo al 31/12</th>
                    <th className="px-1 py-1 text-right font-medium text-muted-foreground">Tasso %</th>
                    {p.forecastYears.map((y) => (
                      <th key={y} className="px-1 py-1 text-right font-medium text-muted-foreground">{y}</th>
                    ))}
                    <th className="px-1 py-1 text-right font-medium text-muted-foreground">Resta</th>
                    <th className="px-1 py-1" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.index} className="border-b border-border/50">
                      <td className="px-1 py-1">
                        <Input
                          className="h-8 min-w-[9rem]"
                          aria-label={`Nome finanziamento ${row.index + 1}`}
                          value={row.name}
                          onChange={(e) => onCampo(row.index, "name", e.target.value)}
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number" min={0} step={1000} className="h-8 w-28 text-right"
                          aria-label={`Residuo finanziamento ${row.index + 1}`}
                          value={row.residuo}
                          onChange={(e) => onCampo(row.index, "opening_residual", e.target.value === "" ? 0 : Number(e.target.value))}
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number" min={0} max={100} step={0.1} className="h-8 w-20 text-right"
                          aria-label={`Tasso finanziamento ${row.index + 1}`}
                          value={row.tasso}
                          onChange={(e) => onCampo(row.index, "interest_rate", e.target.value === "" ? 0 : Number(e.target.value))}
                        />
                      </td>
                      {row.rimborsi.map((r, i) => (
                        <td key={i} className="px-1 py-1">
                          <Input
                            type="number" min={0} step={100} className="h-8 w-24 text-right"
                            aria-label={`Rimborso ${p.forecastYears[i]} finanziamento ${row.index + 1}`}
                            value={r}
                            onChange={(e) => onRimborso(row.index, i, e.target.value === "" ? 0 : Number(e.target.value))}
                          />
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-1 py-1 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <span className={cn(row.resta < 0 && "text-red-600 dark:text-red-400")}>{euro(row.resta)}</span>
                          <Chip tono={statoTono(row.stato)}>{row.stato}</Chip>
                        </div>
                      </td>
                      <td className="px-1 py-1 text-right">
                        {pregressi.length > 1 && (
                          <Button
                            type="button" variant="ghost" size="icon"
                            aria-label={`Rimuovi finanziamento ${row.index + 1}`}
                            onClick={() => onElimina(row.index)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onAggiungi}>
              <Plus className="mr-1 h-4 w-4" /> Aggiungi finanziamento
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={pregressi.length < 2} onClick={onUnisci}>
              Unisci in un solo finanziamento
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Per fare in fretta: un unico finanziamento con il totale, e scadenzi quello.
          </p>
        </div>

        <div className="space-y-2">
          {controlli.fidiOltre && <ControlRow c={controlli.fidiOltre} tono="errore" />}
          <ControlRow c={controlli.quadra} tono={controlli.quadra.ok ? "ok" : "errore"} />
          <ControlRow c={controlli.rata} tono={controlli.rata.esito === "coerente" ? "ok" : "avviso"} />
        </div>
      </CardContent>
    </Card>
  );
}
