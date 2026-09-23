/**
 * L'anteprima «Scadenziamento pregresso · flussi di cassa» del passo 5 (spec
 * 2026-09-15 §4.5): che cosa il piano, anno per anno, incassa e paga del
 * pregresso, e quanto ne resta aperto a fine anno.
 *
 * Lettura pura dei `details` che il motore ha gia' dichiarato
 * (`pregresso[*].closed`, `imposte.saldo_paid`/`rate_paid`,
 * `debito_bancario.fidi`/`contratti`, `altri_finanziatori`): qui non si deriva
 * nulla, se non la parte A BREVE di ogni saldo — e i `details` non la portano,
 * perche' `closed` e' un numero solo mentre il breve e' meta' dello stesso,
 * quella che arriva dal bilancio base. Per questo la firma chiede `breve`, che
 * il passo 5 compone con `massaBreve` (la STESSA funzione che genera il piano:
 * anteprima e caselle non possono divergere).
 *
 * Modulo puro: nessun import da `app/` o da `components/`. Le righe sono
 * `PreviewRow` di `budget-preview-rows.ts`, cosi' `PreviewPanel` le rende come
 * tutte le altre: nessun secondo motore di formattazione.
 */
import type { ForecastPreviewYear } from "@/types/api";
import type { OltreKey } from "@/lib/budget-pregresso-oltre";
import type { PreviewCell, PreviewRow } from "@/lib/budget-preview-rows";
import { num } from "@/lib/budget-format";

const cents = (v: number) => Math.round(v * 100) / 100;
const emptyCell = (): PreviewCell => ({ value: null });

/** Il `closed` dichiarato per un saldo in un anno. Una chiave assente vale
 *  zero (la lettura prudente di tutto il lotto: il motore le dichiara sempre,
 *  una risposta piu' vecchia no). */
const chiuso = (y: ForecastPreviewYear | undefined, key: OltreKey): number =>
  num(y?.details?.pregresso?.[key]?.closed);

/** I contratti PREGRESSI fra quelli dichiarati quest'anno: un residuo iniziale
 *  maggiore di zero e' debito che era gia' in bilancio, e solo quello passa da
 *  qui — il finanziamento nuovo si scadenzia al passo 6. E' la stessa chiave
 *  di `projection_common.e_contratto_pregresso`, letta sul `details`. */
const contrattiPregressi = (y: ForecastPreviewYear | undefined) =>
  (y?.details?.debito_bancario?.contratti ?? []).filter((c) => num(c.residuo_iniziale) > 0);

/**
 * Quanta massa A BREVE di un saldo si chiude in quest'anno: il `closed` fino a
 * concorrenza di quanta ne resta da vedere, anno dopo anno.
 *
 * Non «il primo anno, poi zero»: con un piano che salda il breve in due anni,
 * o con un anno in cui il motore ne ha chiuso meno, la parte rimandata e' un
 * flusso di cassa vero, e collocarla sulla riga «oltre» (o non collocarla
 * affatto) sposterebbe il netto senza che nessun totale se ne accorga.
 *
 * `rema` e' un contenitore mutabile apposta: la chiamata e' sequenziale sugli
 * anni, e la quota vista quest'anno non si rivede l'anno dopo.
 */
function quotaBreve(y: ForecastPreviewYear | undefined, key: OltreKey, rema: { euro: number }): number {
  const q = Math.min(chiuso(y, key), Math.max(0, rema.euro));
  rema.euro -= q;
  return q;
}

const intestazione = (key: string, label: string, n: number): PreviewRow =>
  ({ key, label, kind: "total", base: emptyCell(), years: Array.from({ length: n }, emptyCell) });

const riga = (key: string, label: string, values: number[]): PreviewRow =>
  ({ key, label, kind: "value", base: emptyCell(), years: values.map((v) => ({ value: cents(v) })) });

/**
 * Le quattordici righe del pannello: due intestazioni, i quattro flussi «a
 * breve», i sei «finanziamenti e oltre 12 mesi», il netto e il debito aperto.
 *
 * Il segno e' la direzione del flusso: positivo incassa, negativo paga.
 * `netto` e' la somma delle dieci righe di flusso; `aperto` non e' un flusso e
 * non entra nel netto — e' cio' che di pregresso resta a bilancio a fine anno
 * (la stessa somma che il passo 6 legge in `debito_bancario`, qui fermata al
 * pregresso: i finanziamenti nuovi hanno il loro spazio li').
 */
export function flussiPregresso(years: ForecastPreviewYear[], breve: Record<OltreKey, number>): PreviewRow[] {
  if (years.length === 0) return [];

  // Le due masse a breve che hanno anche una riga «oltre» (crediti e altri
  // debiti): si scorporano qui per non comparire due volte.
  const remaCred = { euro: num(breve.crediti_commerciali) };
  const remaAltri = { euro: num(breve.altri_debiti) };
  const cred = years.map((y) => quotaBreve(y, "crediti_commerciali", remaCred));
  const altri = years.map((y) => quotaBreve(y, "altri_debiti", remaAltri));

  const flussi: PreviewRow[] = [
    riga("crediti", "Incasso crediti verso clienti", cred),
    riga("fornitori", "Pagamento fornitori", years.map((y) => -chiuso(y, "debiti_fornitori"))),
    // Solo il primo anno: dal secondo `saldo_paid` e' il saldo delle imposte GENERATE dal piano,
    // non debito pregresso, e finiva nella «cassa netta del pregresso» (collaudo R4).
    riga("trib-saldo", "Saldo debiti tributari", years.map((y, i) => (i === 0 ? -num(y.details?.imposte?.saldo_paid) : 0))),
    riga(
      "previd-altri",
      "Debiti previdenziali e altri a breve",
      // I fornitori oltre 12 mesi non hanno una riga propria (sono una voce del
      // piano, non un saldo da scadenziare qui): tutto il loro `closed` passa
      // dalla riga breve, e il netto torna lo stesso.
      years.map((y, i) => -chiuso(y, "debiti_previdenziali") - altri[i]!),
    ),
    riga("banche", "Finanziamenti bancari esistenti", years.map((y) => -contrattiPregressi(y).reduce((a, c) => a + num(c.rimborso), 0))),
    riga("fidi", "Fidi, Anticipi Ft e Scoperti CC · variazione", years.map((y) => {
      const f = y.details?.debito_bancario?.fidi;
      return f ? num(f.residuo) - num(f.apertura) : 0;
    })),
    riga("altri-fin", "Altri finanziatori", years.map((y) => -num(y.details?.altri_finanziatori?.rimborso))),
    riga("trib-rate", "Tributari rateizzati", years.map((y) => -num(y.details?.imposte?.rate_paid))),
    riga("altri-oltre", "Altri debiti oltre 12 mesi", years.map((y, i) => altri[i]! - chiuso(y, "altri_debiti"))),
    riga("crediti-oltre", "Incasso crediti oltre 12 mesi", years.map((y, i) => chiuso(y, "crediti_commerciali") - cred[i]!)),
  ];

  const somma = (i: number) => flussi.reduce((a, r) => a + num(r.years[i]?.value), 0);
  const aperto = (y: ForecastPreviewYear) => cents(
    num(y.details?.debito_bancario?.fidi?.residuo)
    + contrattiPregressi(y).reduce((a, c) => a + num(c.breve) + num(c.lungo), 0)
    + num(y.details?.altri_finanziatori?.breve) + num(y.details?.altri_finanziatori?.lungo)
    + num(y.details?.pregresso?.debiti_tributari?.residual_long)
    + num(y.details?.pregresso?.altri_debiti?.residual_long)
    + num(y.details?.pregresso?.debiti_fornitori?.residual_long)
    + num(y.details?.pregresso?.debiti_previdenziali?.residual_long),
  );

  return [
    intestazione("h-breve", "A breve", years.length),
    ...flussi.slice(0, 4),
    intestazione("h-oltre", "Finanziamenti e oltre 12 mesi", years.length),
    ...flussi.slice(4),
    { key: "netto", label: "Cassa netta del pregresso", kind: "total", base: emptyCell(), years: years.map((_, i) => ({ value: cents(somma(i)) })) },
    { key: "aperto", label: "debito pregresso ancora aperto a fine anno", kind: "sub", base: emptyCell(), years: years.map((y) => ({ value: aperto(y) })) },
  ];
}
