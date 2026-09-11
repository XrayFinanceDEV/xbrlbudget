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
 * (fabbisogno scoperto) in importo e anno invece del messaggio grezzo del
 * motore. Un `data.error` che la regex non riconosce non sparisce mai in
 * silenzio: torna il messaggio grezzo del motore (gia' italiano alla fonte,
 * lotto 3A task 8).
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
    "rimborso più lungo del debito pregresso.";
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
 * Il prefisso di `assumptions_service.bulk_upsert_assumptions` nasce gia'
 * in italiano («Ipotesi salvate, ma il previsionale non è stato calcolato:
 * ...», Task 8 lotto 3A), e cosi' il messaggio del motore che segue i due
 * punti (`Fabbisogno finanziario scoperto di ...`, stesso task, parte B) —
 * non c'e' piu' nulla da tradurre qui. Il client riconosce solo il caso del
 * fabbisogno scoperto (`unfundedAmountFromMessage`): se scatta, vince e
 * sostituisce l'intera frase, prefisso compreso, con l'importo e il rimedio
 * in una sola frase italiana. Altrimenti il messaggio torna **grezzo**: e'
 * gia' italiano alla fonte, quindi mostrarlo cosi' com'e' non e' mai un
 * testo inventato che non descrive quel guasto.
 */
export function saveNotice(message: string): string {
  const amount = unfundedAmountFromMessage(message);
  if (amount !== null) return `Ipotesi salvate. ${unfundedText(amount, null)}`;
  return message;
}
