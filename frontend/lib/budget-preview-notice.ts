/**
 * Il messaggio da mostrare sotto l'anteprima di un passo del wizard, in un
 * solo posto (fix round 1, rilievo 3-b): prima di questo modulo
 * `unfundedFromError` esisteva dal Task 4 apposta ma non era chiamata da
 * nessun passo, e ogni `PreviewPanel` riceveva solo `p.preview.error` — il
 * canale di TRASPORTO (400, rete, annullamento). Quando il motore si ferma
 * per fabbisogno scoperto la risposta e' comunque un 200 e la diagnosi vive
 * in `p.preview.data.error` (`ForecastPreviewResponse.error`), che restava
 * cosi' non letta: l'utente vedeva colonne che finivano prima senza una
 * parola che spiegasse perche'.
 *
 * `previewNotice` unifica le due fonti con una sola precedenza — il
 * trasporto se c'e', altrimenti il corpo — e traduce il caso riconoscibile
 * (fabbisogno scoperto) in importo e anno invece del messaggio inglese del
 * motore. Un `data.error` che la regex non riconosce non sparisce mai in
 * silenzio: torna il messaggio grezzo del motore.
 */
import { unfundedAmountFromMessage, unfundedFromError } from "@/lib/budget-preview-rows";
import type { PreviewState } from "@/lib/budget-preview-state";
import { formatCurrency } from "@/lib/formatters";

/**
 * La frase italiana del fabbisogno scoperto, in UN solo posto.
 *
 * La usano l'anteprima (che l'anno lo conosce) e il toast del salvataggio in
 * blocco (che non lo conosce: `assumptions_service.py` incapsula il solo
 * `str(e)` del motore). Scriverne una seconda per il toast la farebbe
 * divergere dalla prima alla prima modifica — ed era esattamente lo squilibrio
 * osservato a schermo: il pannello in italiano con le migliaia all'europea, e
 * a pochi centimetri il toast con l'inglese grezzo del motore.
 */
function unfundedText(amount: number, year: number | null): string {
  const dove = year === null ? "" : ` nel ${year}`;
  return `Fabbisogno finanziario scoperto${dove}: ${formatCurrency(amount)}. ` +
    "Il previsionale si ferma qui: copri lo scoperto con un finanziamento, meno investimenti, o un " +
    "rimborso piu' lungo del debito pregresso.";
}

export function previewNotice(preview: PreviewState): string | null {
  if (preview.error) return preview.error;
  const bodyError = preview.data?.error ?? null;
  if (!bodyError) return null;

  const unfunded = unfundedFromError(bodyError);
  if (unfunded) return unfundedText(unfunded.amount, unfunded.year);
  return bodyError.message;
}

/**
 * Il messaggio del salvataggio in blocco quando il previsionale e' stato
 * rifiutato, tradotto quando e' riconoscibile.
 *
 * Il salvataggio e' andato a buon fine anche in questo caso — le ipotesi
 * restano persistite, e' solo il previsionale a non essere stato generato —
 * quindi la frase lo dice prima di spiegare il perche'.
 *
 * Un messaggio che la regex NON riconosce torna **grezzo**: meglio l'inglese
 * del motore di un testo inventato che non descrive quel guasto.
 */
export function saveNotice(message: string): string {
  const amount = unfundedAmountFromMessage(message);
  if (amount === null) return message;
  return `Ipotesi salvate. ${unfundedText(amount, null)}`;
}
