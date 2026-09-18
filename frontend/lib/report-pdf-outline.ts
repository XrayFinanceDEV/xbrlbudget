/**
 * Indice delle pagine del PDF, accanto all'anteprima in `/report` (come la
 * colonna di navigazione dell'anteprima v4).
 *
 * Il numero di pagina NON si indovina: il catalogo del dossier garantisce una
 * pagina fisica per voce, e il piano editoriale è la misura di quel documento
 * compilato — quindi la posizione nella lista `plan.pages` È il numero di
 * pagina. Se quell'invariante saltasse, il piano stesso fallirebbe prima
 * (`_validate_inventory`, lato server).
 *
 * L'etichetta invece è solo una comodità di navigazione: la fonte dei titoli
 * è il catalogo Python, che qui non arriva. Un id senza etichetta nota si
 * mostra com'è, mai una pagina senza voce: meglio un nome tecnico che un buco
 * nell'indice.
 */

export interface OutlineEntry {
  /** 1-based, come lo intende il visualizzatore PDF. */
  page: number;
  label: string;
  sectionId: string;
}

/** I titoli neutri delle pagine del catalogo v4 (`dossier_catalog`). */
export const PDF_PAGE_LABELS: Record<string, string> = {
  cover: "Copertina",
  sintesi: "Sintesi esecutiva",
  fonti: "Bilancio infrannuale e fonti",
  rettifiche: "Rettifiche apportate",
  chiusura: "Dall'infrannuale alla chiusura",
  "indicatori-infrannuali": "Indicatori dell'infrannuale",
  ipotesi: "Ipotesi del piano",
  ce: "Conto economico previsionale",
  sp: "Stato patrimoniale previsionale",
  flussi: "Flussi di cassa e sostenibilità",
  indicatori: "Indicatori e rischi",
  liquidita: "Liquidità e margini strutturali",
  redditivita: "Redditività e costo del debito",
  solidita: "Solidità e copertura del debito",
  circolante: "Circolante e ciclo monetario",
  composizione: "Composizione economica e patrimoniale",
  "break-even": "Break-even e margine di sicurezza",
  diagnostica: "Diagnostica e punti da verificare",
  allegati: "Allegati · indice dei prospetti",
  metodologia: "Metodologia e note",
};

/** Le parti di un allegato (`allegato-A-1`) prendono il nome della lettera. */
const ATTACHMENT_NAMES: Record<string, string> = {
  A: "Conto economico completo",
  B: "Stato patrimoniale completo",
  C: "Rendiconto finanziario completo",
  D: "Registro delle rettifiche",
  E: "Matrice ipotesi e finanziamenti",
  F: "Indicatori della pratica",
  G: "Indicatori analitici",
};

export function pdfPageLabel(sectionId: string): string {
  const known = PDF_PAGE_LABELS[sectionId];
  if (known) return known;
  const attachment = /^allegato-([A-G])(?:-(\d+))?$/.exec(sectionId);
  if (attachment) {
    const [, letter, part] = attachment;
    const name = ATTACHMENT_NAMES[letter] ?? "Prospetto";
    return part ? `${letter} · ${name} (${part})` : `${letter} · ${name}`;
  }
  return sectionId;
}

export function buildPdfOutline(pages: ReadonlyArray<{ section_id: string }>): OutlineEntry[] {
  return pages.map((page, index) => ({
    page: index + 1,
    label: pdfPageLabel(page.section_id),
    sectionId: page.section_id,
  }));
}

/**
 * L'URL da dare all'`<iframe>` per aprirlo su una pagina precisa. Il
 * frammento è quello dei visualizzatori PDF; `zoom=page-width` fa leggere il
 * foglio a tutta larghezza, che è il punto dolente dell'anteprima dentro una
 * colonna stretta.
 */
export function pdfPageUrl(url: string, page: number): string {
  const base = url.split("#")[0];
  return `${base}#page=${Math.max(1, Math.trunc(page))}&zoom=page-width`;
}
