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
  return `${value.toFixed(1)}%`;
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

