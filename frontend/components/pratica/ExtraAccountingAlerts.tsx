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

export function ExtraAccountingAlerts({
  alerts,
  onChange,
}: {
  alerts: Record<string, boolean>;
  onChange: (alerts: Record<string, boolean>) => void;
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
          {EXTRA_ALERT_DEFS.map((def, idx) => (
            <div key={def.key} className="flex items-start gap-3">
              <Checkbox
                id={`alert-${def.key}`}
                checked={!!alerts[def.key]}
                onCheckedChange={(checked) =>
                  onChange({ ...alerts, [def.key]: !!checked })
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
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

