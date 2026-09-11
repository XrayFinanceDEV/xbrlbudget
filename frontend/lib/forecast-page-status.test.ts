import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import {
  ANALYSIS_RETRY_COUNT,
  ANALYSIS_RETRY_DELAY_MS,
  forecastLoadErrorMessage,
  forecastPageState,
  forecastPageStatus,
  forecastScenariosEmpty,
} from "./forecast-page-status";

describe("forecastPageStatus", () => {
  it("in caricamento, sempre caricamento", () => {
    expect(forecastPageStatus(true, new Error("x"))).toBe("caricamento");
    expect(forecastPageStatus(true, null)).toBe("caricamento");
  });

  it("non in caricamento, con errore: errore", () => {
    expect(forecastPageStatus(false, new Error("x"))).toBe("errore");
  });

  it("non in caricamento, senza errore: pronto", () => {
    expect(forecastPageStatus(false, null)).toBe("pronto");
    expect(forecastPageStatus(false, undefined)).toBe("pronto");
  });
});

describe("forecastLoadErrorMessage", () => {
  it("usa il detail del backend quando la risposta c'e'", () => {
    const err = { response: { data: { detail: "Scoperto oltre il tetto concesso" } } };
    expect(forecastLoadErrorMessage(err)).toBe("Scoperto oltre il tetto concesso");
  });

  it("un errore di rete senza corpo ha un testo italiano fisso, mai il messaggio inglese di axios", () => {
    const networkError = new Error("Network Error");
    expect(forecastLoadErrorMessage(networkError)).toBe(
      "Il server non ha risposto. Controlla la connessione e riprova.",
    );
  });

  it("una risposta senza detail leggibile ricade sul messaggio generico italiano", () => {
    const err = { response: { data: {} } };
    expect(forecastLoadErrorMessage(err)).toBe("Impossibile caricare i dati previsionali.");
  });

  it("un vero AxiosError senza detail leggibile ricade sul messaggio generico italiano, mai sul testo inglese di axios", () => {
    const err = new AxiosError(
      "Request failed with status code 502",
      "ERR_BAD_RESPONSE",
      undefined,
      undefined,
      {
        status: 502,
        statusText: "Bad Gateway",
        headers: {},
        config: {} as never,
        data: "<html>Bad Gateway</html>",
      },
    );
    expect(forecastLoadErrorMessage(err)).toBe("Impossibile caricare i dati previsionali.");
  });

  it("un vero AxiosError con detail restituisce il detail", () => {
    const err = new AxiosError(
      "Request failed with status code 400",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        status: 400,
        statusText: "Bad Request",
        headers: {},
        config: {} as never,
        data: { detail: "Scoperto oltre il tetto concesso" },
      },
    );
    expect(forecastLoadErrorMessage(err)).toBe("Scoperto oltre il tetto concesso");
  });

  it("un vero AxiosError senza response e' un errore di rete: testo italiano fisso", () => {
    const err = new AxiosError("Network Error", "ERR_NETWORK");
    expect(forecastLoadErrorMessage(err)).toBe(
      "Il server non ha risposto. Controlla la connessione e riprova.",
    );
  });
});

describe("forecastPageState", () => {
  it("scenari in caricamento: caricamento, nessuna sorgente d'errore", () => {
    const result = forecastPageState(
      { loading: true, error: null },
      { loading: false, error: null },
    );
    expect(result).toEqual({ status: "caricamento", errorSource: null });
  });

  it("analisi in caricamento (scenari pronti): caricamento", () => {
    const result = forecastPageState(
      { loading: false, error: null },
      { loading: true, error: null },
    );
    expect(result).toEqual({ status: "caricamento", errorSource: null });
  });

  it("la lista scenari fallita e' un errore con sorgente \"scenarios\", anche se l'analisi non ha mai girato", () => {
    const scenariosError = new Error("500");
    const result = forecastPageState(
      { loading: false, error: scenariosError },
      { loading: false, error: null },
    );
    expect(result).toEqual({ status: "errore", errorSource: "scenarios" });
  });

  it("solo /analysis fallita (scenari caricati) e' un errore con sorgente \"analysis\"", () => {
    const analysisError = new Error("500");
    const result = forecastPageState(
      { loading: false, error: null },
      { loading: false, error: analysisError },
    );
    expect(result).toEqual({ status: "errore", errorSource: "analysis" });
  });

  it("un errore sulla lista scenari vince su un errore di /analysis: la lista viene prima nella sequenza", () => {
    const scenariosError = new Error("scenari");
    const analysisError = new Error("analisi");
    const result = forecastPageState(
      { loading: false, error: scenariosError },
      { loading: false, error: analysisError },
    );
    expect(result.errorSource).toBe("scenarios");
  });

  it("nessun errore, nessun caricamento: pronto", () => {
    const result = forecastPageState(
      { loading: false, error: null },
      { loading: false, error: null },
    );
    expect(result).toEqual({ status: "pronto", errorSource: null });
  });
});

describe("forecastScenariosEmpty", () => {
  it("vero solo quando la lista si e' caricata davvero ed e' vuota", () => {
    expect(forecastScenariosEmpty({ loading: false, error: null }, 0)).toBe(true);
  });

  it("falso mentre la lista sta ancora caricando, anche a zero elementi", () => {
    expect(forecastScenariosEmpty({ loading: true, error: null }, 0)).toBe(false);
  });

  it("falso quando la lista e' fallita, anche a zero elementi (rilievo 1 del collaudo finale)", () => {
    expect(forecastScenariosEmpty({ loading: false, error: new Error("500") }, 0)).toBe(false);
  });

  it("falso quando la lista contiene elementi", () => {
    expect(forecastScenariosEmpty({ loading: false, error: null }, 2)).toBe(false);
  });
});

describe("i tentativi di useAnalysis restano espliciti e finiti", () => {
  it("pin dei valori: un cambiamento qui e' una scelta, non un incidente", () => {
    expect(ANALYSIS_RETRY_COUNT).toBe(1);
    expect(ANALYSIS_RETRY_DELAY_MS).toBe(1000);
  });
});
