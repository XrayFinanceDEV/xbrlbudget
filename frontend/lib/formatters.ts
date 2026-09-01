/**
 * Formatting utilities for Italian locale
 */

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Legge un importo scritto a mano nel formato italiano: punti (e spazi) come
 * separatore delle migliaia, virgola decimale.
 *
 * Tre esiti, perché i chiamanti ne distinguono tre:
 *   - `null`      campo vuoto → RIMUOVERE l'override. Non è «forza a zero»,
 *                 ed è la differenza fra «torna al valore calcolato» e uno
 *                 zero secco: `sp_overrides` clampa i negativi a zero e
 *                 ignora in silenzio le chiavi sconosciute, quindi un errore
 *                 qui non dà errore, dà uno zero.
 *   - `undefined` non è un numero → non registrare nulla.
 *   - un numero   il valore.
 *
 * Una sola implementazione per CE e SP Previsionale di proposito: due parser
 * di numeri italiani che divergono sono un modo silenzioso di scrivere un
 * importo diverso da quello digitato.
 */
export function parseItalianAmount(raw: string): number | null | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const parsed = parseFloat(trimmed.replace(/[.\s]/g, "").replace(",", "."));
  return Number.isNaN(parsed) ? undefined : parsed;
}

export function formatCurrencyDetailed(value: number): string {
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercentage(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('it-IT', {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatNumber(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatDecimal(value: number, decimals: number = 4): string {
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

// Sector names in Italian
export const sectorNames: Record<number, string> = {
  1: 'Industria',
  2: 'Commercio',
  3: 'Servizi',
  4: 'Autotrasporti',
  5: 'Immobiliare',
  6: 'Edilizia',
};

export function getSectorName(sector: number): string {
  return sectorNames[sector] || 'Sconosciuto';
}

// Altman classification colors
export function getAltmanColor(classification: string): string {
  switch (classification) {
    case 'safe':
      return 'text-green-600';
    case 'gray_zone':
      return 'text-yellow-600';
    case 'distress':
      return 'text-red-600';
    default:
      return 'text-gray-600';
  }
}

// FGPMI rating colors
export function getFGPMIColor(ratingCode: string): string {
  if (ratingCode.startsWith('AAA') || ratingCode.startsWith('AA')) {
    return 'text-green-600';
  } else if (ratingCode.startsWith('A') || ratingCode.startsWith('BBB')) {
    return 'text-blue-600';
  } else if (ratingCode.startsWith('BB')) {
    return 'text-yellow-600';
  } else {
    return 'text-red-600';
  }
}
