/**
 * Il badge d'origine di un'ipotesi (M1-08B).
 *
 * §6.4 del progetto di massima: ogni valore dichiara la propria provenienza, e
 * §8 impone che un'informazione non sia mai affidata al solo colore. Qui ci sono
 * dunque tre canali per lo stesso significato: l'icona, la parola, il colore.
 *
 * Modulo di sola presentazione: nessun hook, nessuna chiamata, nessun
 * ricalcolo. `legacy_unknown` non è «default»: un record nato prima del
 * tracciamento non distingue l'input utente dal valore proposto, e il badge deve
 * dirlo invece di scegliere lui.
 */
import * as React from "react";
import { Ban, CircleHelp, Layers, SlidersHorizontal, User, Wand2 } from "lucide-react";
import type { LucideProps } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Provenance } from "@/types/final-report";

export interface ProvenanceView {
  /** La parola che si legge nel badge. */
  label: string;
  /** La frase che il badge scioglie (visibile a schermo, non solo in `title`). */
  description: string;
  Icon: React.ComponentType<LucideProps>;
  /** Colore complementare a icona e testo: da solo non significa nulla. */
  className: string;
  /** `false` per un'origine che non è una delle sei del contratto v1. */
  known: boolean;
}

const VIEWS: Record<Provenance, ProvenanceView> = {
  user: {
    label: "Utente",
    description: "Valore inserito direttamente dall'utente.",
    Icon: User,
    className: "border-sky-300 bg-sky-100 text-sky-900 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-200",
    known: true,
  },
  automatic: {
    label: "Automatico",
    description: "Valore derivato da una regola documentata del motore.",
    Icon: Wand2,
    className: "border-violet-300 bg-violet-100 text-violet-900 dark:border-violet-700 dark:bg-violet-950/40 dark:text-violet-200",
    known: true,
  },
  default: {
    label: "Default",
    description: "Valore proposto dal sistema e non modificato.",
    Icon: Layers,
    className: "border-slate-300 bg-slate-100 text-slate-800 dark:border-slate-600 dark:bg-slate-900/50 dark:text-slate-300",
    known: true,
  },
  override: {
    label: "Override",
    description: "Sostituzione esplicita di un valore calcolato.",
    Icon: SlidersHorizontal,
    className: "border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-200",
    known: true,
  },
  ignored: {
    label: "Ignorato",
    description: "Presente nel payload, non usato nel percorso corrente.",
    Icon: Ban,
    className: "border-zinc-300 bg-zinc-100 text-zinc-700 line-through decoration-zinc-500 dark:border-zinc-600 dark:bg-zinc-900/50 dark:text-zinc-400",
    known: true,
  },
  legacy_unknown: {
    label: "Origine storica",
    description:
      "Record precedente al tracciamento dell'origine: input utente e valore predefinito non sono distinguibili.",
    Icon: CircleHelp,
    className: "border-dashed border-stone-400 bg-stone-100 text-stone-800 dark:border-stone-500 dark:bg-stone-900/50 dark:text-stone-300",
    known: true,
  },
};

/** Le sei origini del contratto v1, nell'ordine in cui compaiono nel modello. */
export const PROVENANCE_ORDER: readonly Provenance[] = [
  "user",
  "automatic",
  "default",
  "override",
  "ignored",
  "legacy_unknown",
];

/**
 * La resa di un'origine. Un valore che non è uno dei sei (un payload di una
 * versione diversa, una chiave scritta male) non diventa «default»: esce come
 * badge «Origine non dichiarata» che dice anche che cosa conteneva il campo.
 */
export function provenanceView(provenance: Provenance | string): ProvenanceView {
  const view = (VIEWS as Record<string, ProvenanceView | undefined>)[provenance];
  if (view) return view;
  return {
    label: "Origine non dichiarata",
    description: `Il valore "${String(provenance)}" non è una delle sei origini del contratto v1.`,
    Icon: CircleHelp,
    className: "border-dashed border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/40 dark:text-red-200",
    known: false,
  };
}

export interface ProvenanceBadgeProps {
  provenance: Provenance | string;
  /** Una riga `active: false` è un valore che non guida nulla: si dice, non si tace. */
  active?: boolean;
  className?: string;
}

export function ProvenanceBadge({ provenance, active = true, className }: ProvenanceBadgeProps) {
  const view = provenanceView(provenance);
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      <Badge
        variant="outline"
        className={cn("gap-1 font-medium", view.className)}
        title={view.description}
      >
        <view.Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{view.label}</span>
        <span className="sr-only"> — {view.description}</span>
      </Badge>
      {!active && (
        <span className="text-xs text-muted-foreground">non attivo nel percorso corrente</span>
      )}
    </span>
  );
}

/** La legenda del documento: sei badge, sei frasi. §6.4 esige che l'origine sia
 *  leggibile senza doverla indovinare dal colore. */
export function ProvenanceLegend({ className }: { className?: string }) {
  return (
    <ul
      className={cn("grid gap-1 text-xs text-muted-foreground sm:grid-cols-2", className)}
      aria-label="Legenda delle origini delle ipotesi"
    >
      {PROVENANCE_ORDER.map((provenance) => {
        const view = provenanceView(provenance);
        return (
          <li key={provenance} className="flex items-center gap-2">
            <Badge variant="outline" className={cn("gap-1 font-medium", view.className)}>
              <view.Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
              {view.label}
            </Badge>
            <span>{view.description}</span>
          </li>
        );
      })}
    </ul>
  );
}
