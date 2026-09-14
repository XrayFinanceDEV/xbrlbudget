/**
 * Il banner di readiness del report finale (M1-08B).
 *
 * §8: `ready`, `draft`, `blocked` con una lista di motivi (codice, severità,
 * sezione, messaggio). §9: il banner di bozza/bloccato è persistente, e nessuna
 * informazione passa dal solo colore — qui ogni stato ha icona, parola e
 * spiegazione, in quest'ordine.
 *
 * Componente di sola presentazione: il verdetto lo decide l'assembler
 * (`backend/app/services/final_report_service.py`), non qui. Questo modulo non
 * aggiunge né toglie blocchi, e non ricalcola nulla.
 */
import * as React from "react";
import { CircleAlert, CircleCheck, CircleHelp, FileWarning, ShieldAlert } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Diagnostic, Readiness } from "@/types/final-report";
import { severityView } from "./DiagnosticsGrouping";

export interface ReadinessView {
  /** La parola del banner: BOZZA, BLOCCATO, PRONTO. */
  label: string;
  title: string;
  description: string;
  Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
  className: string;
  /** `alert` per ciò che blocca, `status` per il resto: §8 vuole la spiegazione,
   *  non un campanello su tutto. */
  role: "status" | "alert";
}

const VIEWS: Record<Readiness["status"], ReadinessView> = {
  ready: {
    label: "Pronto",
    title: "Documento pronto",
    description: "Nessun controllo bloccante: il report può essere finalizzato.",
    Icon: CircleCheck,
    className:
      "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200",
    role: "status",
  },
  draft: {
    label: "Bozza",
    title: "Documento in bozza",
    description: "Il report è rappresentabile, ma ci sono verifiche aperte prima della finalizzazione.",
    Icon: FileWarning,
    className:
      "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-200",
    role: "status",
  },
  blocked: {
    label: "Bloccato",
    title: "Documento bloccato",
    description: "Almeno un controllo bloccante impedisce la finalizzazione del documento.",
    Icon: ShieldAlert,
    className:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/40 dark:text-red-200",
    role: "alert",
  },
};

/**
 * La resa di uno stato. Un valore che non è uno dei tre (un payload di un'altra
 * versione) non ricade su `ready`: esce come «stato non riconosciuto» e dice il
 * valore che ha trovato, perché il fallback ottimista è il modo più silenzioso
 * di mostrare come finale un documento che finale non è.
 */
export function readinessView(status: string): ReadinessView {
  const view = (VIEWS as Record<string, ReadinessView | undefined>)[status];
  if (view) return view;
  return {
    label: "Stato non riconosciuto",
    title: "Stato di finalizzazione non riconosciuto",
    description: `Il modello porta lo stato "${String(status)}", che non è uno dei tre del contratto v1 ("ready", "draft", "blocked"). Nessuna sezione va letta come definitiva.`,
    Icon: CircleHelp,
    className:
      "border-dashed border-stone-400 bg-stone-50 text-stone-900 dark:border-stone-500 dark:bg-stone-950/40 dark:text-stone-200",
    role: "alert",
  };
}

/**
 * I motivi del verdetto, raggruppati per severità e ordinati per blocco.
 *
 * `reasons` assente e `reasons` vuota non sono la stessa cosa: la prima è
 * «il modello non li dichiara», la seconda è «nessun motivo». Il file di
 * progetto lo dice esplicitamente («una chiave assente vale zero»), e qui le
 * due cose si leggono diverse.
 */
export function readinessReasons(
  readiness: Pick<Readiness, "status" | "reasons">,
): { declared: boolean; items: Diagnostic[]; contradiction: boolean } {
  const items = readiness.reasons ?? [];
  return {
    declared: Array.isArray(readiness.reasons),
    items,
    contradiction: readiness.status === "ready" && items.some((reason) => reason.severity === "error"),
  };
}

export interface ReadinessBannerProps {
  readiness: Readiness;
  className?: string;
  /** Ancora per il sommario di §9. */
  id?: string;
  /** In stampa il banner non occupa una pagina sua. */
  compact?: boolean;
}

export function ReadinessBanner({ readiness, className, id = "readiness", compact = false }: ReadinessBannerProps) {
  const view = readinessView(readiness.status);
  const reasons = readinessReasons(readiness);

  return (
    <Card
      id={id}
      role={view.role}
      aria-labelledby={`${id}-title`}
      className={cn("print:break-inside-avoid border-2", view.className, className)}
    >
      <div className={cn("flex items-center gap-2 px-6 pt-6", compact ? "pb-1" : "pb-2")}>
        <view.Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
        <h3 id={`${id}-title`} className="text-base font-semibold">
          {view.title}
        </h3>
        <span
          className={cn(
            "rounded border border-current px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide",
          )}
        >
          {view.label}
        </span>
      </div>
      <CardContent className={cn("space-y-2", compact && "pt-0")}>
        <p className="text-sm">{view.description}</p>

        {!reasons.declared ? (
          <p className="text-sm font-medium">
            Il modello non dichiara i motivi del verdetto: lo stato va letto come informatione non
            verificata, non come «nessun rilievo».
          </p>
        ) : reasons.items.length === 0 ? (
          <p className="text-sm">Nessun motivo dichiarato: nessun controllo in sospeso.</p>
        ) : (
          <ul className="space-y-1" aria-label="Motivi del verdetto di finalizzazione">
            {reasons.items.map((reason, index) => {
              const severity = severityView(reason.severity);
              return (
                <li key={`${reason.code}-${index}`} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <severity.Icon className="h-4 w-4 shrink-0 self-center" aria-hidden="true" />
                  <span className="font-semibold">{severity.label}</span>
                  {!severity.known ? <span className="text-xs">gravità &quot;{reason.severity}&quot;</span> : null}
                  <span>{reason.message}</span>
                  <span className="text-xs text-muted-foreground">
                    {reason.section} · {reason.code}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        {reasons.contradiction ? (
          <p className="flex items-start gap-2 text-sm font-medium">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            Incongruenza: il verdetto dice «pronto» ma fra i motivi c&apos;è un errore. Il documento
            non va trattato come finale.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
