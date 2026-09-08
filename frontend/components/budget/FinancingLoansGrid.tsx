"use client";

// Spostato verbatim da app/budget/page.tsx:1477-1736, esportato perché il
// wizard a sette passi possa consumarlo senza duplicarlo.
import { AlertTriangle, Info, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import { statoResidui } from "@/lib/base-bank-debt";
import { cn } from "@/lib/utils";
import type { BalanceSheet, BudgetAssumptionsCreate, FinancingLoanInput } from "@/types/api";

export function FinancingLoansGrid({
  forecastYears,
  assumptions,
  onUpdate,
  baseYear,
  baseBalance,
}: {
  forecastYears: number[];
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
  onUpdate: (year: number, loans: FinancingLoanInput[]) => void;
  baseYear: number;
  baseBalance?: BalanceSheet;
}) {
  const updateLoan = (
    year: number,
    index: number,
    field: keyof FinancingLoanInput,
    value: string | number
  ) => {
    const loans = [...(assumptions[year]?.financing_loans ?? [])];
    loans[index] = { ...loans[index], [field]: value };
    onUpdate(year, loans);
  };

  // Il motore somma i residui di TUTTI gli anni di piano (`detailed_opening_total`)
  // prima di confrontarli col debito bancario; l'UI ne ammette solo sul primo,
  // ma il conteggio deve restare quello del motore.
  const tuttiIResidui = forecastYears.flatMap(
    (y) => assumptions[y]?.financing_loans ?? [],
  );
  const copertura = statoResidui(
    baseBalance as unknown as Record<string, unknown>,
    tuttiIResidui,
  );

  return (
    <Card>
      <CardHeader>
        {/*
          Si chiamava «Finanziamenti aggiuntivi», che si legge come «nuovi»: il
          tester ha chiesto come mancante il dettaglio del debito ESISTENTE, che
          esiste da mesi. Il titolo diceva il contrario di quello che la card fa.
        */}
        <CardTitle className="text-base">Finanziamenti — esistenti e nuovi</CardTitle>
        <p className="text-sm text-muted-foreground">
          Qui si dettaglia contratto per contratto <strong>sia</strong> il debito bancario
          già in essere <strong>sia</strong> i finanziamenti futuri.
        </p>
        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
          <li>
            <strong>Residuo iniziale</strong>: quota di debito bancario già in essere
            all&apos;anno base {baseYear}. Ammesso solo nel primo anno di piano.
          </li>
          <li>
            <strong>Nuova erogazione</strong>: finanziamento acceso in quell&apos;anno.
          </li>
        </ul>
        <p className="mt-1 text-xs text-muted-foreground">
          Ogni contratto mantiene durata, tasso, preammortamento e quota balloon autonomi.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/*
          Il debito da coprire, live. Il numero DEVE essere quello contro cui
          valida il motore (`base_bank_debt`, che include gli scarti fra
          aggregato e dettagli): la formula «ovvia» `sp16a + sp17a` darebbe un
          numero diverso, e su un bilancio abbreviato mostrerebbe come coperto
          un piano che il server rifiuta.
        */}
        {baseBalance && (
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">
                  Debito bancario {baseYear}
                </p>
                <p className="font-semibold">{formatCurrency(copertura.debitoBancario)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Residui inseriti</p>
                <p className="font-semibold">{formatCurrency(copertura.sommaResidui)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Ancora da coprire</p>
                <p
                  className={cn(
                    "font-semibold",
                    copertura.bloccante
                      ? "text-yellow-700 dark:text-yellow-400"
                      : copertura.attivo
                        ? "text-green-700 dark:text-green-400"
                        : "text-foreground",
                  )}
                >
                  {formatCurrency(copertura.differenza)}
                </p>
              </div>
            </div>

            {/*
              Avviso NON bloccante, e l'input resta compilabile: si compila una
              riga alla volta, e a metà compilazione lo scarto è normale. Ma il
              vincolo è tutto-o-niente e al centesimo, e finora non era
              dichiarato da nessuna parte — il previsionale veniva rifiutato dal
              server con un messaggio che l'utente non poteva prevedere.
            */}
            {copertura.bloccante && (
              <p className="mt-3 flex items-start gap-2 text-xs text-yellow-700 dark:text-yellow-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  I residui iniziali non coprono il debito bancario dell&apos;anno base:
                  finché la differenza non è zero al centesimo, il previsionale verrà
                  rifiutato.
                </span>
              </p>
            )}

            {/*
              Due comandi visibili per la stessa cosa, e uno dei due smette di
              fare qualcosa senza dirlo: `ESSENTIAL_ROWS` contiene ancora
              «Rimborso debiti bancari (anni)», che il motore IGNORA non appena
              esiste un residuo dettagliato.
            */}
            {copertura.attivo && (
              <p className="mt-2 flex items-start gap-2 text-xs text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Con almeno un residuo iniziale valorizzato, il motore usa questo
                  scadenzario e <strong>ignora</strong> la riga «Rimborso debiti bancari
                  (anni)» qui sopra.
                </span>
              </p>
            )}
          </div>
        )}
        {forecastYears.map((year) => {
          const loans = assumptions[year]?.financing_loans ?? [];
          return (
            <div key={year} className="rounded-md border border-border p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h4 className="text-sm font-semibold">{year}</h4>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onUpdate(year, [
                    ...loans,
                    {
                      name: `Finanziamento ${loans.length + 2}`,
                      amount: 1000,
                      opening_residual: 0,
                      duration_years: 5,
                      interest_rate: 3,
                      grace_years: 0,
                      balloon_pct: 0,
                    },
                  ])}
                >
                  <Plus className="mr-1 h-4 w-4" /> Aggiungi linea
                </Button>
              </div>
              {loans.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nessuna linea aggiuntiva.</p>
              ) : (
                <div className="space-y-3">
                  {loans.map((loan, index) => (
                    <div key={index} className="rounded-md bg-muted/30 p-2">
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-4 xl:grid-cols-[1.3fr_repeat(6,minmax(7rem,1fr))_auto]">
                      <Input
                        value={loan.name ?? ""}
                        placeholder="Descrizione"
                        onChange={(event) => updateLoan(year, index, "name", event.target.value)}
                      />
                      <Input
                        type="number"
                        min={0}
                        step={1000}
                        value={loan.opening_residual}
                        disabled={year !== forecastYears[0]}
                        aria-label={`Residuo iniziale finanziamento ${year}`}
                        placeholder="Residuo iniziale"
                        onChange={(event) => updateLoan(year, index, "opening_residual", Number(event.target.value))}
                      />
                      <Input
                        type="number"
                        min={0}
                        step={1000}
                        value={loan.amount}
                        aria-label={`Importo finanziamento ${year}`}
                        placeholder="Nuova erogazione"
                        onChange={(event) => updateLoan(year, index, "amount", Number(event.target.value))}
                      />
                      <Input
                        type="number"
                        min={1}
                        max={50}
                        step={1}
                        value={loan.duration_years}
                        aria-label={`Durata finanziamento ${year}`}
                        placeholder="Durata"
                        onChange={(event) => updateLoan(year, index, "duration_years", Number(event.target.value))}
                      />
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        step={0.1}
                        value={loan.interest_rate}
                        aria-label={`Tasso finanziamento ${year}`}
                        placeholder="Tasso %"
                        onChange={(event) => updateLoan(year, index, "interest_rate", Number(event.target.value))}
                      />
                      <Input
                        type="number"
                        min={0}
                        max={Math.max(0, Number(loan.duration_years) - 1)}
                        step={1}
                        value={loan.grace_years}
                        aria-label={`Preammortamento finanziamento ${year}`}
                        placeholder="Preamm. anni"
                        onChange={(event) => updateLoan(year, index, "grace_years", Number(event.target.value))}
                      />
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={loan.balloon_pct}
                        aria-label={`Balloon finanziamento ${year}`}
                        placeholder="Balloon %"
                        onChange={(event) => updateLoan(year, index, "balloon_pct", Number(event.target.value))}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Rimuovi finanziamento ${index + 1} del ${year}`}
                        onClick={() => onUpdate(year, loans.filter((_, loanIndex) => loanIndex !== index))}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Rata capitale ordinaria stimata: {formatCurrency((() => {
                        const principal = Number(loan.amount || 0) + Number(loan.opening_residual || 0);
                        const years = Math.max(1, Number(loan.duration_years || 1) - Number(loan.grace_years || 0));
                        return principal * (1 - Number(loan.balloon_pct || 0) / 100) / years;
                      })())}
                    </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
