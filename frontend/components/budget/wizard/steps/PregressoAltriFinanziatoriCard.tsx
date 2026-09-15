"use client";

// Passo 5 (II) del wizard ipotesi — card «Altri finanziatori» (spec
// 2026-09-15 §4.5, §5.3; Task 14). Stessa idea della card «Debiti verso
// banche», ma su `other_lenders` (sp16b/sp17b): un finanziatore per riga,
// capitale rimborsato anno per anno, «resta», e un solo controllo (somma dei
// residui contro `sp16b + sp17b` dell'anno base) — nessun fido da separare,
// quindi nessuna sezione «1».
//
// Presentazionale: le decisioni stanno in lib/budget-finanziamenti-pregresso.ts
// (stesso modulo della card banche), provate in environment: node.
//
// Resa da StepPatrimonialePregresso.tsx
// (Task 13): riceve le stesse props di ogni altro passo (StepProps), che
// gia' porta updateOtherLenders.
import type { JSX } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { euro } from "@/lib/budget-format";
import {
  contrattoRows,
  controlloAltri,
  nuovoFinanziatore,
  type ContrattoRow,
} from "@/lib/budget-finanziamenti-pregresso";
import { cn } from "@/lib/utils";
import type { StepProps } from "../types";

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
 *  colonna «resta» sono neutre per costruzione (stessa regola della card
 *  «Debiti verso banche»). */
function statoTono(stato: ContrattoRow["stato"]): Tono {
  return stato === "oltre il residuo" ? "errore" : "neutro";
}

export function PregressoAltriFinanziatoriCard(p: StepProps): JSX.Element {
  const baseBs = p.historical[p.baseYear]?.balance;
  const firstYear = p.forecastYears[0];
  const horizon = p.forecastYears.length;

  if (!baseBs || firstYear === undefined) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Altri finanziatori</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Il bilancio dell&apos;anno base non è ancora disponibile: senza quei saldi non c&apos;è nulla da
            scadenziare.
          </p>
        </CardContent>
      </Card>
    );
  }

  const items = p.assumptions[firstYear]?.other_lenders ?? [];
  const rows = contrattoRows(items, horizon);
  const controllo = controlloAltri(baseBs, items);

  const scrivi = (prossimi: typeof items) => p.updateOtherLenders(prossimi.length > 0 ? prossimi : null);
  const onCampo = (k: number, field: "name" | "opening_residual" | "interest_rate", value: string | number | null) =>
    scrivi(items.map((it, idx) => (idx === k ? { ...it, [field]: value } : it)));
  const onRimborso = (k: number, i: number, value: number | null) =>
    scrivi(items.map((it, idx) => {
      if (idx !== k) return it;
      const repayments = [...(it.repayments ?? [])];
      while (repayments.length < horizon) repayments.push(0);
      repayments.length = horizon;
      repayments[i] = value ?? 0;
      return { ...it, repayments };
    }));
  const onAggiungi = () => scrivi([...items, nuovoFinanziatore(items.length + 1, horizon)]);
  const onElimina = (k: number) => scrivi(items.filter((_, idx) => idx !== k));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Altri finanziatori</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nessun altro finanziatore ancora scadenziato.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-1 py-1 text-left font-medium text-muted-foreground">Finanziatore</th>
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
                        aria-label={`Nome finanziatore ${row.index + 1}`}
                        value={row.name}
                        onChange={(e) => onCampo(row.index, "name", e.target.value)}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        type="number" min={0} step={1000} className="h-8 w-28 text-right"
                        aria-label={`Residuo finanziatore ${row.index + 1}`}
                        value={row.residuo}
                        onChange={(e) => onCampo(row.index, "opening_residual", e.target.value === "" ? 0 : Number(e.target.value))}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        type="number" min={0} max={100} step={0.1} className="h-8 w-20 text-right"
                        aria-label={`Tasso finanziatore ${row.index + 1}`}
                        value={row.tasso}
                        onChange={(e) => onCampo(row.index, "interest_rate", e.target.value === "" ? 0 : Number(e.target.value))}
                      />
                    </td>
                    {row.rimborsi.map((r, i) => (
                      <td key={i} className="px-1 py-1">
                        <Input
                          type="number" min={0} step={100} className="h-8 w-24 text-right"
                          aria-label={`Rimborso ${p.forecastYears[i]} finanziatore ${row.index + 1}`}
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
                      <Button
                        type="button" variant="ghost" size="icon"
                        aria-label={`Rimuovi finanziatore ${row.index + 1}`}
                        onClick={() => onElimina(row.index)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div>
          <Button type="button" variant="outline" size="sm" onClick={onAggiungi}>
            <Plus className="mr-1 h-4 w-4" /> Aggiungi finanziatore
          </Button>
          <p className="mt-1 text-xs text-muted-foreground">
            Anni vuoti = nessun rimborso nel piano: il debito resta in bilancio oltre la fine del piano.
          </p>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-md bg-muted p-2 text-xs">
          <span className="text-foreground">{controllo.testo}</span>
          <Chip tono={controllo.ok ? "ok" : "errore"}>{controllo.esito}</Chip>
        </div>
      </CardContent>
    </Card>
  );
}
