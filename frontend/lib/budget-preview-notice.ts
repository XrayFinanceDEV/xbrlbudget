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
import { unfundedFromError } from "@/lib/budget-preview-rows";
import type { PreviewState } from "@/lib/budget-preview-state";
import { formatCurrency } from "@/lib/formatters";

export function previewNotice(preview: PreviewState): string | null {
  if (preview.error) return preview.error;
  const bodyError = preview.data?.error ?? null;
  if (!bodyError) return null;

  const unfunded = unfundedFromError(bodyError);
  if (unfunded) {
    return `Fabbisogno finanziario scoperto nel ${unfunded.year}: ${formatCurrency(unfunded.amount)}. ` +
      "Il previsionale si ferma qui: copri lo scoperto con un finanziamento, meno investimenti, o un " +
      "rimborso piu' lungo del debito pregresso.";
  }
  return bodyError.message;
}
