"use client";

import { useEffect, useState } from "react";
import {
  DURATA_ATTESA_IMPORT_SECONDI,
  messaggioImport,
  percentualeImport,
} from "@/lib/import-progress";

/**
 * Barra di avanzamento stimato mentre gira un import PDF. Si monta quando
 * l'import parte e si smonta quando finisce: il cronometro riparte da zero a
 * ogni montaggio. L'avanzamento è una stima sul tempo (lib/import-progress),
 * il server non ne manda.
 */
export function ImportProgressBar({
  durataAttesaSecondi = DURATA_ATTESA_IMPORT_SECONDI,
}: {
  durataAttesaSecondi?: number;
}) {
  const [secondi, setSecondi] = useState(0);

  useEffect(() => {
    const inizio = Date.now();
    const id = setInterval(() => {
      setSecondi((Date.now() - inizio) / 1000);
    }, 500);
    return () => clearInterval(id);
  }, []);

  const percentuale = percentualeImport(secondi, durataAttesaSecondi);

  return (
    <div className="w-full space-y-1.5">
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percentuale)}
        aria-label="Avanzamento stimato dell'importazione"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500 ease-linear"
          style={{ width: `${percentuale}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        {messaggioImport(secondi, durataAttesaSecondi)}
      </p>
    </div>
  );
}
