"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { VoceIndiceGuida } from "@/lib/guida";

/**
 * Indice fisso a sinistra della guida. Evidenzia la sezione in lettura: l'ultima
 * il cui titolo è già salito sopra un quarto dello schermo.
 */
export function IndiceLaterale({ voci }: { voci: VoceIndiceGuida[] }) {
  const [attiva, setAttiva] = useState<string | null>(null);

  useEffect(() => {
    const titoli = voci
      .map((v) => document.getElementById(v.id))
      .filter((el): el is HTMLElement => el !== null);
    const aggiorna = () => {
      const soglia = window.innerHeight / 4;
      let corrente: string | null = null;
      for (const el of titoli) {
        if (el.getBoundingClientRect().top <= soglia) corrente = el.id;
        else break;
      }
      setAttiva(corrente);
    };
    aggiorna();
    window.addEventListener("scroll", aggiorna, { passive: true });
    return () => window.removeEventListener("scroll", aggiorna);
  }, [voci]);

  return (
    <nav aria-label="Indice della guida" className="text-sm">
      <p className="mb-3 font-semibold text-foreground">Indice</p>
      <ul className="space-y-0.5 border-l border-border">
        {voci.map((v) => (
          <li key={v.id}>
            <a
              href={`#${v.id}`}
              className={cn(
                "-ml-px block border-l-2 py-1 pr-2 leading-snug transition-colors",
                v.livello === 1 ? "pl-3 font-medium" : "pl-6",
                attiva === v.id
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {v.testo}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
