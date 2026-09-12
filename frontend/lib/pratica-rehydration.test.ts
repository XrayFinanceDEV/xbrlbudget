import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import { praticaRehydrationFailure } from "./pratica-rehydration";

describe("praticaRehydrationFailure", () => {
  it("solo un 404 dimostra che la pratica non esiste piu'", () => {
    expect(praticaRehydrationFailure({ response: { status: 404 } })).toBe(
      "not_found",
    );
  });

  it.each([400, 401, 403, 408, 429, 500, 502, 503])(
    "un HTTP %s non autorizza a retrocedere lo step persistito",
    (status) => {
      expect(praticaRehydrationFailure({ response: { status } })).toBe(
        "transient",
      );
    },
  );

  it("un errore di rete resta ritentabile", () => {
    expect(
      praticaRehydrationFailure(new AxiosError("Network Error", "ERR_NETWORK")),
    ).toBe("transient");
  });
});
