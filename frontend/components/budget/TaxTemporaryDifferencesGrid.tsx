"use client";

// Spostato verbatim da app/budget/page.tsx:1738-1831, esportato perché il
// wizard a sette passi possa consumarlo senza duplicarlo.
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import type { BudgetAssumptionsCreate, TemporaryDifferenceInput } from "@/types/api";

export function TaxTemporaryDifferencesGrid({
  forecastYears,
  assumptions,
  onUpdate,
}: {
  forecastYears: number[];
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
  onUpdate: (year: number, lines: TemporaryDifferenceInput[]) => void;
}) {
  const updateLine = (
    year: number,
    index: number,
    field: keyof TemporaryDifferenceInput,
    value: string | number | null,
  ) => {
    const lines = [...(assumptions[year]?.tax_temporary_differences ?? [])];
    lines[index] = { ...lines[index], [field]: value };
    onUpdate(year, lines);
  };

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="text-sm">Mastrino imposte anticipate e differite</CardTitle>
        <p className="text-xs text-muted-foreground">
          Saldo imponibile = apertura + incrementi − riversamenti. Le differenze deducibili
          alimentano i crediti per imposte anticipate; le imponibili il fondo imposte differite.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {forecastYears.map((year) => {
          const lines = assumptions[year]?.tax_temporary_differences ?? [];
          const defaultRate = Number(assumptions[year]?.tax_rate ?? 0);
          const totals = lines.reduce((acc, line) => {
            const base = Math.max(0, Number(line.opening_amount) + Number(line.additions) - Number(line.reversals));
            const tax = base * Number(line.tax_rate ?? defaultRate) / 100;
            if (line.kind === "taxable") acc.liability += tax;
            else if (line.maturity === "long") acc.longAsset += tax;
            else acc.shortAsset += tax;
            return acc;
          }, { shortAsset: 0, longAsset: 0, liability: 0 });
          return (
            <div key={year} className="rounded-md border border-border p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h5 className="text-sm font-semibold">{year}</h5>
                  <p className="text-[11px] text-muted-foreground">
                    DTA breve {formatCurrency(totals.shortAsset)} · DTA lungo {formatCurrency(totals.longAsset)} · DTL {formatCurrency(totals.liability)}
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => onUpdate(year, [
                  ...lines,
                  {
                    name: `Differenza temporanea ${lines.length + 1}`,
                    kind: "deductible",
                    maturity: "short",
                    opening_amount: 0,
                    additions: 0,
                    reversals: 0,
                    tax_rate: null,
                  },
                ])}>
                  <Plus className="mr-1 h-4 w-4" /> Aggiungi differenza
                </Button>
              </div>
              {lines.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nessuna differenza temporanea.</p>
              ) : lines.map((line, index) => (
                <div key={index} className="mb-2 grid grid-cols-1 gap-2 rounded-md bg-muted/30 p-2 md:grid-cols-4 xl:grid-cols-[1.4fr_repeat(6,minmax(7rem,1fr))_auto]">
                  <Input value={line.name} placeholder="Descrizione" onChange={(e) => updateLine(year, index, "name", e.target.value)} />
                  <select className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={line.kind} onChange={(e) => updateLine(year, index, "kind", e.target.value)}>
                    <option value="deductible">Deducibile (DTA)</option>
                    <option value="taxable">Imponibile (DTL)</option>
                  </select>
                  <select className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={line.maturity} onChange={(e) => updateLine(year, index, "maturity", e.target.value)} disabled={line.kind === "taxable"}>
                    <option value="short">Entro 12 mesi</option>
                    <option value="long">Oltre 12 mesi</option>
                  </select>
                  <Input type="number" min={0} step={1000} value={line.opening_amount} placeholder="Apertura" onChange={(e) => updateLine(year, index, "opening_amount", Number(e.target.value))} />
                  <Input type="number" min={0} step={1000} value={line.additions} placeholder="Incrementi" onChange={(e) => updateLine(year, index, "additions", Number(e.target.value))} />
                  <Input type="number" min={0} step={1000} value={line.reversals} placeholder="Riversamenti" onChange={(e) => updateLine(year, index, "reversals", Number(e.target.value))} />
                  <Input type="number" min={0} max={100} step={0.1} value={line.tax_rate ?? ""} placeholder={`Aliquota ${defaultRate}%`} onChange={(e) => updateLine(year, index, "tax_rate", e.target.value === "" ? null : Number(e.target.value))} />
                  <Button type="button" variant="ghost" size="icon" aria-label={`Rimuovi differenza ${index + 1} del ${year}`} onClick={() => onUpdate(year, lines.filter((_, lineIndex) => lineIndex !== index))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
