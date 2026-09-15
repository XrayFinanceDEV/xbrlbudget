/**
 * Fondamento puro dei sette "segnali extracontabili" (M1-03).
 *
 * Il contratto accettato lato server è l'oggetto stretto
 * `ExtraAccountingAlerts` di `backend/app/schemas/budget.py`:
 * `extra="forbid"` + sette campi `StrictBool` con default `False`,
 * persistito nella colonna JSON `BudgetScenario.extra_accounting_alerts`
 * (nullable). Ciò che la GET può riportare è quindi `null` (mai salvato),
 * un oggetto parziale (colonna scritta come JSON "sparse"), o un oggetto
 * con chiavi/valori che il modello non riconosce. Questo modulo normalizza,
 * serializza e confronta; non tocca React né la rete.
 *
 * Le chiavi sono tenute in parità con `EXTRA_ALERT_DEFS` di
 * `./pratica-codes` dal test `pratica-extra-alerts.test.ts`: qui stanno
 * come unione letterale perché `EXTRA_ALERT_DEFS` è tipata
 * `Array<{ key: string; ... }>` e non può dare il tipo letterale a runtime.
 */

/** Le sette chiavi consentite, nell'ordine di `EXTRA_ALERT_DEFS`. */
export const EXTRA_ALERT_KEYS = [
  "retribuzioni",
  "fornitori",
  "banche",
  "inps",
  "inail",
  "riscossione",
  "iva",
] as const;

export type ExtraAccountingAlertKey = (typeof EXTRA_ALERT_KEYS)[number];

/** Stato normalizzato: sempre sette chiavi, sempre booleani. */
export type ExtraAccountingAlerts = {
  [K in ExtraAccountingAlertKey]: boolean;
};

/** Payload della PUT: oggetto pieno, esplicitamente solo le sette chiavi. */
export type ExtraAccountingAlertsPayload = ExtraAccountingAlerts;

function allFalse(): ExtraAccountingAlerts {
  const state = {} as Record<string, boolean>;
  for (const key of EXTRA_ALERT_KEYS) state[key] = false;
  return state as ExtraAccountingAlerts;
}

/** Stato iniziale tutto `false` (nessun segnale). Nuova istanza a ogni chiamata. */
export function createEmptyExtraAlerts(): ExtraAccountingAlerts {
  return allFalse();
}

/**
 * Da input server (`null`, `unknown`, oggetto parziale, chiavi sconosciute,
 * valori non booleani) a stato completo e sicuro.
 *
 * Solo i sette booleani veri sono riconosciuti: `true`/`false` espliciti si
 * preservano, tutto il resto (assente, extra, `"true"`, `1`, `null`) ricade
 * su `false`, che è il default del modello Pydantic. Non solleva mai.
 */
export function normalizeExtraAlerts(input: unknown): ExtraAccountingAlerts {
  const state = allFalse();
  if (typeof input !== "object" || input === null) return state;
  const source = input as Record<string, unknown>;
  for (const key of EXTRA_ALERT_KEYS) {
    // Chiave prototipale estranea non conta: solo proprietà propria booleana.
    if (
      Object.prototype.hasOwnProperty.call(source, key) &&
      typeof source[key] === "boolean"
    ) {
      state[key] = source[key] as boolean;
    }
  }
  return state;
}

/**
 * Payload pieno a sette chiavi per `PUT`/save: ogni chiave è presente e ogni
 * valore è un booleano vero, così un `false` esplicito resta `false` (non
 * sparisce lasciando parlare il default) e nessuna chiave sconosciuta esce
 * mai — `extra="forbid"` sul server risponderebbe 422.
 */
export function serializeExtraAlerts(
  state: ExtraAccountingAlerts | unknown,
): ExtraAccountingAlertsPayload {
  return normalizeExtraAlerts(state);
}

/**
 * Stato "sporco" rispetto al caricato: `true` se almeno una delle sette
 * chiavi differisce dopo la normalizzazione di entrambi. Il snapshot arriva
 * grezzo dalla GET (può essere `null`), e va confrontato da normalizzato,
 * non dall'oggetto nudo. Una flip e il suo ripristino danno `false`.
 */
export function extraAlertsDirty(
  current: ExtraAccountingAlerts | unknown,
  loaded: unknown,
): boolean {
  const a = normalizeExtraAlerts(current);
  const b = normalizeExtraAlerts(loaded);
  return EXTRA_ALERT_KEYS.some((key) => a[key] !== b[key]);
}

/**
 * Il salvataggio è consentito solo dopo una GET riuscita per lo scenario
 * corrente. Un errore di PUT non entra qui: conserva il dirty state e rende
 * possibile un nuovo tentativo.
 */
export function canSaveExtraAlerts({
  dirty,
  loaded,
  loading,
  saving,
}: {
  dirty: boolean;
  loaded: boolean;
  loading: boolean;
  saving: boolean;
}): boolean {
  return dirty && loaded && !loading && !saving;
}
