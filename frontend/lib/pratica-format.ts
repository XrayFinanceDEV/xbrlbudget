export const MONTH_LABELS: Record<number, string> = {
  1: "1 mese (31/01)",
  2: "2 mesi (28/02)",
  3: "3 mesi (31/03)",
  4: "4 mesi (30/04)",
  5: "5 mesi (31/05)",
  6: "6 mesi (30/06)",
  7: "7 mesi (31/07)",
  8: "8 mesi (31/08)",
  9: "9 mesi (30/09)",
  10: "10 mesi (31/10)",
  11: "11 mesi (30/11)",
  12: "12 mesi (31/12)",
};

export const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria",
  2: "Commercio",
  3: "Servizi",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

export function formatEuro(value: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPct(value: number): string {
  if (!Number.isFinite(value)) return "-";
  return `${value.toFixed(1)}%`;
}

/**
 * Percentuale di variazione fra un valore corrente e un riferimento, `null` quando il
 * riferimento è zero AL CENTESIMO (stessa tolleranza di quadratura di `config.py:235`,
 * `VALIDATION_RULES["balance_sheet_tolerance"] = 0.01`), non zero esatto.
 *
 * Perché: un riferimento che per identità contabile DOVREBBE annullarsi (es. la riga
 * "DIFFERENZA (Attivo - Passivo)" di Stampa/Confronto/Proiezione) arriva dal backend come somma
 * di ~10 `float` via Decimal→float (`DecimalJSONResponse`); la somma in virgola mobile non è
 * associativa e può lasciare un residuo dell'ordine di 1e-9..1e-13 invece di 0 letterale.
 * Dividere uno sbilancio vero anche piccolo per un residuo di quell'ordine dà una percentuale a
 * 12-15 cifre (osservato: +2366097483366300.0%, indagine-3 del 2026-09-11). Un confronto con
 * zero esatto non intercetta il residuo; arrotondare al centesimo prima del confronto sì, e non
 * sposta nessuna riga sana (il residuo è ~9 ordini di grandezza sotto un centesimo).
 */
export function deltaPct(current: number, reference: number): number | null {
  if (Math.round(reference * 100) === 0) return null;
  return ((current - reference) / Math.abs(reference)) * 100;
}

// Format number with Italian thousand separators (4.246.479) for input display
export function formatInputNumber(value: string): string {
  const raw = value.replace(/[^\d-]/g, "");
  if (!raw || raw === "-") return raw;
  const num = parseInt(raw, 10);
  if (isNaN(num)) return raw;
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(num);
}

// Parse Italian-formatted number back to plain digits
export function parseInputNumber(formatted: string): string {
  return formatted.replace(/\./g, "");
}

