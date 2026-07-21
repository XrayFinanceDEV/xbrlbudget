"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Save, WandSparkles } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getAdjustableFinancialYear, saveAdjustments } from "@/lib/api";
import { formatCurrency } from "@/lib/formatters";
import { BALANCE_HIERARCHY_GROUPS } from "@/lib/ivcee-balance-catalog";
import { getErrorMessage } from "@/lib/utils";
import type { AdjustableFinancialYear } from "@/types/api";

const ALLOCATION_TARGETS: Record<string, string> = {
  sp04_immob_finanziarie: "sp04d_altri_titoli",
  sp05_rimanenze: "sp05d_prodotti_finiti",
  sp06_crediti_breve: "sp06g_crediti_altri_breve",
  sp07_crediti_lungo: "sp07g_crediti_altri_lungo",
  sp12_riserve: "sp12e_altre_riserve",
  sp14_fondi_rischi: "sp14d_altri_fondi",
  sp16_debiti_breve: "sp16g_altri_debiti_breve",
  sp17_debiti_lungo: "sp17g_altri_debiti_lungo",
};

export function HistoricalBalanceDetailEditor({
  companyId,
  year,
}: {
  companyId: number;
  year: number;
}) {
  const [record, setRecord] = useState<AdjustableFinancialYear | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getAdjustableFinancialYear(companyId, year)
      .then((value) => {
        if (!active) return;
        setRecord(value);
        setDraft(value.balance_sheet);
      })
      .catch((error) => {
        if (active) toast.error(`Dettaglio SP non disponibile: ${getErrorMessage(error)}`);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [companyId, year]);

  const checks = useMemo(() => BALANCE_HIERARCHY_GROUPS.map((group) => {
    const aggregate = Number(draft[group.aggregate] || 0);
    const details = group.details.reduce(
      (total, [field]) => total + Number(draft[field] || 0),
      0,
    );
    return { group, aggregate, details, delta: aggregate - details };
  }), [draft]);
  const hasMismatch = checks.some(({ delta }) => Math.abs(delta) > 0.01);

  const allocateGap = (aggregate: string, delta: number) => {
    const target = ALLOCATION_TARGETS[aggregate];
    if (!target) return;
    setDraft((current) => ({
      ...current,
      [target]: Number(current[target] || 0) + delta,
    }));
  };

  const save = async () => {
    if (!record || hasMismatch) {
      toast.error("Completa la ripartizione di ogni aggregato prima di salvare.");
      return;
    }
    setSaving(true);
    try {
      const saved = await saveAdjustments(
        companyId,
        year,
        draft,
        record.income_statement,
        undefined,
        record.rettifiche_log,
      );
      setRecord(saved);
      setDraft(saved.balance_sheet);
      toast.success("Dettaglio storico dello stato patrimoniale salvato e validato.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Caricamento dettaglio SP {year}…</div>;
  }
  if (!record) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Maschera dettaglio SP storico · {year}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Per i bilanci abbreviati ripartisci gli aggregati nelle voci IV-CEE. Il totale
              storico resta invariato e il motore usa solo dettagli riconciliati.
            </p>
          </div>
          <span className={`rounded-full px-2 py-1 text-xs font-medium ${record.forecastable ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
            {record.forecastable ? "Fonte forecastable" : "Revisione richiesta"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasMismatch && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Aggregati da ripartire</AlertTitle>
            <AlertDescription>
              I pulsanti “Completa differenza” assegnano il residuo alla voce residuale esplicita;
              puoi poi sostituirlo con la classificazione corretta.
            </AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          {checks.map(({ group, aggregate, details, delta }) => (
            <div key={group.aggregate} className="rounded-md border border-border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h5 className="text-sm font-semibold">{group.title}</h5>
                  <p className="text-[11px] text-muted-foreground">
                    Aggregato {formatCurrency(aggregate)} · dettaglio {formatCurrency(details)}
                  </p>
                </div>
                {Math.abs(delta) <= 0.01 ? (
                  <span className="flex items-center gap-1 text-xs text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> Riconciliato</span>
                ) : (
                  <Button type="button" variant="outline" size="sm" onClick={() => allocateGap(group.aggregate, delta)}>
                    <WandSparkles className="mr-1 h-3.5 w-3.5" /> Completa differenza {formatCurrency(delta)}
                  </Button>
                )}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {group.details.map(([field, label]) => (
                  <label key={field} className="text-xs text-muted-foreground">
                    {label}
                    <Input
                      className="mt-1 text-right"
                      type="number"
                      step={100}
                      value={draft[field] ?? 0}
                      onChange={(event) => setDraft((current) => ({
                        ...current,
                        [field]: Number(event.target.value),
                      }))}
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <Button type="button" onClick={save} disabled={saving || hasMismatch}>
            {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
            Salva dettaglio storico
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
