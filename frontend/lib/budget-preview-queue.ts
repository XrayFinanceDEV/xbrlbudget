/** Debounce + annullamento per l'anteprima, senza React: testabile in node. */
export class PreviewSequencer {
  private seq = 0;
  next(): number { return ++this.seq; }
  isCurrent(seq: number): boolean { return seq === this.seq; }
}

/** La cucitura per i test: due funzioni, non i globali dentro un oggetto.
 *  Vedi il commento su `createDebouncedRunner` per il perche'. */
export interface Timers {
  setTimeout(handler: () => void, ms: number): ReturnType<typeof setTimeout>;
  clearTimeout(id: ReturnType<typeof setTimeout>): void;
}

/**
 * I timer si invocano sempre come funzioni NUDE, mai come metodi di un oggetto
 * che tiene i globali: nel browser `window.setTimeout` chiamato con un
 * ricevitore diverso da `window` lancia `TypeError: Illegal invocation`, e
 * l'anteprima crollava all'ingresso di ogni passo che la usa. Nessun test in
 * `environment: node` lo vedeva, perche' i timer di node non controllano il
 * ricevitore: il difetto e' stato trovato col browser, e la rete che lo tiene
 * ora e' in `budget-preview-queue.test.ts`, che riproduce quel controllo.
 * Quindi: `timers` iniettabile per i test, e per il resto una chiamata nuda.
 */
export function createDebouncedRunner<T>(
  run: (payload: T, signal: AbortSignal) => void,
  delayMs: number,
  timers?: Timers,
): { push(payload: T): void; cancel(): void } {
  const schedule = timers
    ? timers.setTimeout
    : (handler: () => void, ms: number) => setTimeout(handler, ms);
  const unschedule = timers
    ? timers.clearTimeout
    : (id: ReturnType<typeof setTimeout>) => clearTimeout(id);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  const cancel = () => {
    if (timer !== null) { unschedule(timer); timer = null; }
    if (controller) { controller.abort(); controller = null; }
  };
  return {
    push(payload: T) {
      cancel();
      timer = schedule(() => {
        timer = null;
        controller = new AbortController();
        run(payload, controller.signal);
      }, delayMs);
    },
    cancel,
  };
}
