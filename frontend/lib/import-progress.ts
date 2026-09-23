/**
 * Avanzamento stimato di un import PDF, per la barra della pagina Import.
 *
 * Il server non manda avanzamento: la barra misura solo il tempo trascorso
 * contro una durata attesa (120 s di default, il tempo tipico di un import
 * con lettura LLM). Fino alla durata attesa sale in modo lineare fino al 90%;
 * oltre, rallenta verso il 99% senza mai arrivare a 100: il 100% lo decide
 * la risposta del server, non l'orologio.
 */

export const DURATA_ATTESA_IMPORT_SECONDI = 120;

const QUOTA_LINEARE = 90;
const TETTO = 99;

export function percentualeImport(
  secondiTrascorsi: number,
  durataAttesaSecondi: number = DURATA_ATTESA_IMPORT_SECONDI,
): number {
  if (!(secondiTrascorsi > 0) || !(durataAttesaSecondi > 0)) return 0;
  if (secondiTrascorsi <= durataAttesaSecondi) {
    return (QUOTA_LINEARE * secondiTrascorsi) / durataAttesaSecondi;
  }
  const oltre = (secondiTrascorsi - durataAttesaSecondi) / durataAttesaSecondi;
  return QUOTA_LINEARE + (TETTO - QUOTA_LINEARE) * (1 - Math.exp(-oltre));
}

export function messaggioImport(
  secondiTrascorsi: number,
  durataAttesaSecondi: number = DURATA_ATTESA_IMPORT_SECONDI,
): string {
  const s = Math.max(0, Math.floor(secondiTrascorsi));
  const minuti = Math.round(durataAttesaSecondi / 60);
  const attesa = minuti >= 1 ? `circa ${minuti} ${minuti === 1 ? "minuto" : "minuti"}` : `circa ${durataAttesaSecondi} secondi`;
  if (s <= durataAttesaSecondi) {
    return `Lettura del bilancio in corso · ${s} s (di solito ${attesa})`;
  }
  return `Lettura del bilancio in corso · ${s} s — sta impiegando più del solito, attendi ancora`;
}
