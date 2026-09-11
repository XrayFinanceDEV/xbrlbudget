import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import {
  ANALYSIS_RETRY_COUNT,
  ANALYSIS_RETRY_DELAY_MS,
  forecastLoadErrorMessage,
  forecastPageStatus,
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

describe("i tentativi di useAnalysis restano espliciti e finiti", () => {
  it("pin dei valori: un cambiamento qui e' una scelta, non un incidente", () => {
    expect(ANALYSIS_RETRY_COUNT).toBe(1);
    expect(ANALYSIS_RETRY_DELAY_MS).toBe(1000);
  });
});
