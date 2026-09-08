"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { previewForecast } from "@/lib/api";
import { PreviewSequencer, createDebouncedRunner } from "@/lib/budget-preview-queue";
import { getErrorMessage } from "@/lib/utils";
import type { ForecastPreviewResponse } from "@/types/api";

const DELAY_MS = 400;

/**
 * Stato dell'anteprima. Non vive ancora in `components/budget/wizard/types.ts`
 * (Task 8, non ancora integrato su questo commit): questo hook lo definisce
 * ed esporta qui, cosi' resta l'unica dichiarazione fino a quando il Task 8
 * non la sposta/riusa.
 *
 * `error` NON e' esclusivo di `data`: un 200 con `error` valorizzato significa
 * che il motore si e' fermato a un certo anno ma gli anni precedenti sono
 * validi (es. fabbisogno finanziario scoperto) — l'hook deve mostrare
 * entrambi, mai svuotare `data` quando arriva un `error`.
 */
export interface PreviewState {
  data: ForecastPreviewResponse | null;
  error: string | null;
  loading: boolean;
}

/**
 * Client dell'anteprima del previsionale: debounce sulle modifiche di `rows`,
 * annullamento della chiamata precedente, e nessuna sovrascrittura dello
 * stato da parte di una risposta arrivata in ritardo (`PreviewSequencer`).
 * Un solo motore di proiezione, e sta in Python: questo hook non ricalcola
 * nulla, chiama `previewForecast` e mostra quello che torna.
 */
export function useForecastPreview({
  companyId,
  scenarioId,
  rows,
  enabled,
}: {
  companyId: number;
  scenarioId: number | null;
  rows: Record<string, unknown>[] | null;
  enabled: boolean;
}): PreviewState {
  const [state, setState] = useState<PreviewState>({ data: null, error: null, loading: false });
  const seq = useRef(new PreviewSequencer());

  const runner = useMemo(
    () =>
      createDebouncedRunner<Record<string, unknown>[]>((payload, signal) => {
        if (scenarioId === null) return;
        const mine = seq.current.next();
        setState((s) => ({ ...s, loading: true }));
        previewForecast(companyId, scenarioId, payload, signal)
          .then((data) => {
            if (seq.current.isCurrent(mine)) setState({ data, error: null, loading: false });
          })
          .catch((err) => {
            if (axios.isCancel(err) || !seq.current.isCurrent(mine)) return;
            setState((s) => ({ ...s, error: getErrorMessage(err, "Anteprima non disponibile"), loading: false }));
          });
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, DELAY_MS),
    [companyId, scenarioId]
  );

  // `rows` cambia identita' a ogni modifica: e' il segnale voluto. Serializzato
  // per non ripartire quando la mappa e' identica ma l'oggetto e' nuovo.
  const key = rows ? JSON.stringify(rows) : null;
  useEffect(() => {
    if (!enabled || !rows || scenarioId === null) return;
    runner.push(rows);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, scenarioId, runner]);

  useEffect(() => () => runner.cancel(), [runner]);

  return state;
}
