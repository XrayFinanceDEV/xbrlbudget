/**
 * Che numero intende chi incolla un testo in un campo numerico.
 *
 * Un `<input type="number">` accetta solo il punto decimale: incollare «45.600,74» — la cifra di
 * una squadratura copiata dallo schermo, dove ogni importo è scritto all'italiana — dava 45,6,
 * perché il browser tiene il punto e scarta il resto (segnalato dal proprietario, 2026-09-17).
 * Nessun errore: un importo mille volte più piccolo finiva nel piano.
 *
 * Restituisce la forma che il campo capisce, oppure `null` per lasciare al browser l'incolla
 * normale. `null` in due casi, e sono la metà della regola:
 *   - il testo è già un numero col punto decimale («3.5», «45600.74», «6.000000»): viene da un
 *     foglio di calcolo o da un JSON, e reinterpretarlo all'italiana lo moltiplicherebbe;
 *   - il testo non è un numero: non se ne inventa uno.
 *
 * L'unica ambiguità vera è un punto seguito da esattamente tre cifre senza virgola («45.600»):
 * vale come migliaia, perché in quest'app è così che ogni importo compare a schermo. Un
 * decimale a tre cifre copiato da fuori comincia quasi sempre con «0.» e resta un decimale.
 *
 * Diverso da `parseItalianAmount` (`lib/formatters.ts`), che legge testo DIGITATO nei campi a
 * testo di CE e SP Prev.: lì il formato è sempre italiano, qui la sorgente è sconosciuta.
 */
export function numeroIncollato(testo: string): string | null {
  const pulito = testo.replace(/[\s  €]/g, "");
  if (pulito === "") return null;

  // Già nella forma del campo: il punto è il decimale. Se però c'erano spazi o «€» il browser
  // rifiuterebbe l'intero testo, quindi si incolla la forma ripulita.
  const migliaiaItaliane = /^-?[1-9]\d{0,2}(\.\d{3})+$/;
  if (/^-?\d+(\.\d+)?$/.test(pulito) && !migliaiaItaliane.test(pulito)) {
    return pulito === testo.trim() ? null : String(Number(pulito));
  }

  let canonico: string;
  if (/^-?\d{1,3}(\.\d{3})*,\d+$/.test(pulito) || /^-?\d+,\d+$/.test(pulito)) {
    canonico = pulito.replace(/\./g, "").replace(",", ".");
  } else if (migliaiaItaliane.test(pulito)) {
    canonico = pulito.replace(/\./g, "");
  } else {
    return null;
  }
  // Forma normale del numero: «-5.000,00» → «-5000», non «-5000.00».
  return String(Number(canonico));
}
