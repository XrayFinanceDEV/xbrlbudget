/**
 * Un import PDF rifiutato, come lo mostra la pagina Import: il motivo e, quando il server lo riconosce, che cosa
 * caricare al suo posto (`importers/rifiuti_import.py`). Resta a schermo finche' l'utente non sceglie un altro file o
 * riprova: in un toast spariva dopo pochi secondi, e l'utente non si accorgeva di dover caricare un file diverso.
 */
export interface RifiutoImport {
  motivo: string;
  suggerimento: string | null;
  categoria: string | null;
}

/** Il rifiuto dentro un errore Axios di un import PDF (422, `error_type: "PDFImportError"`), altrimenti null. */
export function rifiutoDaErrore(error: unknown): RifiutoImport | null {
  const risposta = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
  const detail = risposta?.data?.detail;
  if (risposta?.status !== 422 || !detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const d = detail as { error?: unknown; error_type?: unknown; suggerimento?: unknown; categoria?: unknown };
  if (d.error_type !== "PDFImportError" || typeof d.error !== "string" || !d.error) return null;
  return {
    motivo: d.error,
    suggerimento: typeof d.suggerimento === "string" && d.suggerimento ? d.suggerimento : null,
    categoria: typeof d.categoria === "string" && d.categoria ? d.categoria : null,
  };
}
