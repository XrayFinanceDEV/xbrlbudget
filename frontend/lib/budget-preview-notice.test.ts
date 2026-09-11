import { describe, expect, it } from "vitest";
import type { ForecastPreviewResponse } from "@/types/api";
import type { PreviewState } from "./budget-preview-state";
import { previewNotice, saveNotice } from "./budget-preview-notice";

const withData = (error: ForecastPreviewResponse["error"]): PreviewState => ({
  loading: false,
  error: null,
  data: { scenario_id: 1, base_year: 2024, forecast_years: [], error },
});

describe("previewNotice", () => {
  it("nessun errore -> null", () => {
    expect(previewNotice({ loading: false, error: null, data: null })).toBeNull();
    expect(previewNotice(withData(null))).toBeNull();
  });

  it("errore di trasporto vince sempre, anche con un data.error valorizzato", () => {
    const preview: PreviewState = {
      loading: false,
      error: "Rete non raggiungibile",
      data: { scenario_id: 1, base_year: 2024, forecast_years: [],
        error: { year: 2028, message: "Unfunded financing requirement 1,000.00: add a financing assumption" } },
    };
    expect(previewNotice(preview)).toBe("Rete non raggiungibile");
  });

  it("fabbisogno scoperto riconosciuto: importo e anno, non il messaggio inglese del motore", () => {
    const notice = previewNotice(withData({
      year: 2028, message: "Unfunded financing requirement 84,120.50: add a financing assumption",
    }));
    expect(notice).not.toBeNull();
    expect(notice).toContain("2028");
    expect(notice).toMatch(/84\.1|84120/); // formatCurrency arrotonda, ma l'importo resta leggibile
    expect(notice).not.toContain("Unfunded financing requirement");
  });

  it("data.error che la regex non riconosce -> il messaggio grezzo, mai null in silenzio", () => {
    const notice = previewNotice(withData({ year: 2028, message: "Errore generico del motore" }));
    expect(notice).toBe("Errore generico del motore");
  });

  it("data.error con year null (regex su unfundedFromError esce comunque null) -> messaggio grezzo", () => {
    const notice = previewNotice(withData({ year: null, message: "Errore senza anno" }));
    expect(notice).toBe("Errore senza anno");
  });
});

describe("saveNotice", () => {
  // Il messaggio esatto del backend (assumptions_service.py:326 attorno a
  // forecast_engine.py:1373), quello che il collaudo ha visto nel toast.
  const DAL_BACKEND =
    "Assumptions saved successfully, but forecast generation failed: Unfunded financing " +
    "requirement 195,418,034.86: add an explicit financing assumption; no bank debt was " +
    "created automatically";

  it("il fabbisogno scoperto arriva in italiano, con le migliaia all'europea", () => {
    const notice = saveNotice(DAL_BACKEND);
    expect(notice).toContain("Fabbisogno finanziario scoperto");
    expect(notice).toContain("195.418.035");
    expect(notice).not.toContain("Unfunded");
    expect(notice).not.toContain("financing assumption");
  });

  it("dice che le ipotesi SONO salvate: e' solo il previsionale a non essere stato generato", () => {
    expect(saveNotice(DAL_BACKEND)).toContain("Ipotesi salvate");
  });

  it("nessun anno da dichiarare: il messaggio del salvataggio non ne porta uno", () => {
    // `assumptions_service` incapsula il solo `str(e)`, senza l'anno che
    // l'anteprima invece riceve in `ForecastPreviewError.year`. Meglio tacerlo
    // che inventarne uno.
    expect(saveNotice(DAL_BACKEND)).not.toMatch(/scoperto nel \d{4}/);
  });

  it("la frase e' LA STESSA dell'anteprima: una sola traduzione, non due", () => {
    const daSalvataggio = saveNotice("Unfunded financing requirement 84,120.50: add a financing assumption");
    const daAnteprima = previewNotice(withData({
      year: 2028, message: "Unfunded financing requirement 84,120.50: add a financing assumption",
    }));
    const coda = "Il previsionale si ferma qui:";
    expect(daSalvataggio.slice(daSalvataggio.indexOf(coda)))
      .toBe(daAnteprima!.slice(daAnteprima!.indexOf(coda)));
  });

  it("un messaggio SENZA il prefisso noto del backend resta GREZZO: meglio l'inglese di un testo inventato", () => {
    expect(saveNotice("Previsionale non generato")).toBe("Previsionale non generato");
    expect(saveNotice("qualcosa che nessuna regex riconosce")).toBe("qualcosa che nessuna regex riconosce");
  });

  // Rilievo 6 (giro di correzione 1) diceva del prefisso ancora inglese; da
  // Task 8 parte A (lotto 3A) il prefisso di `assumptions_service.py` nasce
  // gia' in italiano alla fonte, quindi non c'e' piu' nulla da spogliare qui
  // — i due test di prima diventano uno solo: un messaggio che ha gia' il
  // prefisso italiano e nessun fabbisogno riconoscibile torna INVARIATO. Il
  // resto del testo (dopo i due punti) e' ancora il motore, in inglese finche'
  // non arriva la parte B: non e' questo test a doverlo tradurre.
  it("un messaggio col prefisso italiano del backend e senza fabbisogno riconoscibile torna invariato", () => {
    const dalBackend =
      "Ipotesi salvate, ma il previsionale non è stato calcolato: The sum of financing opening " +
      "residuals must equal base-year bank debt (300000 != 4465659.00)";
    expect(saveNotice(dalBackend)).toBe(dalBackend);
  });

  it("il fabbisogno scoperto riconosciuto vince comunque sul prefisso: una frase sola, non due incollate", () => {
    // Gia' provato sopra con `DAL_BACKEND`, ripetuto qui per dichiarare
    // l'ordine di precedenza esplicitamente: il ramo del fabbisogno scoperto
    // gira PRIMA dello spoglio del prefisso, quindi un messaggio riconosciuto
    // non passa mai per il ramo "prefisso + messaggio grezzo".
    const notice = saveNotice(DAL_BACKEND);
    expect(notice.startsWith("Ipotesi salvate.")).toBe(true);
    expect(notice).not.toContain("ma il previsionale non è stato calcolato");
  });
});
