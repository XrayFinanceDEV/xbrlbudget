/** Debounce + annullamento per l'anteprima, senza React: testabile in node. */
export class PreviewSequencer {
  private seq = 0;
  next(): number { return ++this.seq; }
  isCurrent(seq: number): boolean { return seq === this.seq; }
}

export function createDebouncedRunner<T>(
  run: (payload: T, signal: AbortSignal) => void,
  delayMs: number,
  timers: { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout } = { setTimeout, clearTimeout },
): { push(payload: T): void; cancel(): void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  const cancel = () => {
    if (timer !== null) { timers.clearTimeout(timer); timer = null; }
    if (controller) { controller.abort(); controller = null; }
  };
  return {
    push(payload: T) {
      cancel();
      timer = timers.setTimeout(() => {
        timer = null;
        controller = new AbortController();
        run(payload, controller.signal);
      }, delayMs);
    },
    cancel,
  };
}
