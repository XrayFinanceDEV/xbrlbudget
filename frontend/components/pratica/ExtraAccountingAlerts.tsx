"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { EXTRA_ALERT_DEFS } from "@/lib/pratica-codes";
import type {
  ExtraAccountingAlertKey,
  ExtraAccountingAlerts as ExtraAccountingAlertsState,
} from "@/lib/pratica-extra-alerts";
import { Button } from "@/components/ui/button";

export function ExtraAccountingAlerts({
  alerts,
  onChange,
  dirty,
  loading,
  saving,
  error,
  onSave,
}: {
  alerts: ExtraAccountingAlertsState;
  onChange: (alerts: ExtraAccountingAlertsState) => void;
  dirty: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onSave: () => void;
}) {
  const activeCount = Object.values(alerts).filter(Boolean).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Segnali Extracontabili</CardTitle>
        <CardDescription>
          Indicatori di allerta ai sensi del D.Lgs. 14/2019 (Codice della Crisi).
          Selezionare le condizioni riscontrate.
          {activeCount > 0 && (
            <span className="ml-2 text-red-600 dark:text-red-400 font-medium">
              {activeCount} segnale{activeCount > 1 ? "i" : ""} attivo{activeCount > 1 ? "i" : ""}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {EXTRA_ALERT_DEFS.map((def, idx) => {
            const key = def.key as ExtraAccountingAlertKey;
            return (
            <div key={def.key} className="flex items-start gap-3">
              <Checkbox
                id={`alert-${def.key}`}
                checked={alerts[key]}
                onCheckedChange={(checked) =>
                  onChange({ ...alerts, [key]: !!checked })
                }
                className="mt-0.5"
              />
              <label
                htmlFor={`alert-${def.key}`}
                className="text-sm leading-relaxed cursor-pointer"
              >
                <span className="font-medium text-muted-foreground">{idx + 1}.</span>{" "}
                {def.label}
              </label>
            </div>
            );
          })}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={onSave} disabled={!dirty || saving || loading} size="sm">
            {saving ? "Salvataggio…" : "Salva segnali"}
          </Button>
          {dirty && !saving && (
            <span className="text-sm text-amber-700 dark:text-amber-400">
              Modifiche non salvate
            </span>
          )}
          {loading && !saving && (
            <span className="text-sm text-muted-foreground">Caricamento segnali…</span>
          )}
          {!dirty && !loading && !saving && !error && (
            <span className="text-sm text-muted-foreground">Salvato</span>
          )}
          {error && (
            <span role="alert" className="text-sm text-destructive">
              {error} Riprova il salvataggio.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

