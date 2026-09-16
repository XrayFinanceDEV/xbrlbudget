// @vitest-environment node
import { describe, it, expect } from "vitest";
import { ceDerivatiDaForecast, valoreCeProiettato } from "@/lib/pratica-ce-proiettato";
import { DERIVED_CE_CODES, EDITABLE_CE_CODES } from "@/lib/pratica-codes";

const annualizzato = (code: string) => (code === "ce10_var_rimanenze_mat_prime" ? -2864 : 1000);

describe("le variazioni di magazzino non sono più modificabili", () => {
  it("non stanno fra le righe che il client manda come override", () => {
    for (const code of DERIVED_CE_CODES) {
      expect(EDITABLE_CE_CODES).not.toContain(code);
    }
    expect(DERIVED_CE_CODES).toEqual(["ce02_variazioni_rimanenze", "ce10_var_rimanenze_mat_prime"]);
  });
});

describe("valoreCeProiettato", () => {
  it("su una riga modificabile vale quel che ha scritto l'utente", () => {
    const v = valoreCeProiettato("ce01_ricavi_vendite", {
      overrides: { ce01_ricavi_vendite: "4109510" },
      annualizzato,
    });
    expect(v).toBe(4109510);
  });

  it("su una riga dedotta vale il numero del motore, non l'annualizzazione", () => {
    const v = valoreCeProiettato("ce10_var_rimanenze_mat_prime", {
      overrides: { ce10_var_rimanenze_mat_prime: "-2864" },
      derivati: { ce10_var_rimanenze_mat_prime: -31000 },
      annualizzato,
    });
    // L'override residuo di uno scenario vecchio non deve più vincere.
    expect(v).toBe(-31000);
  });

  it("prima del primo salvataggio ricade sull'annualizzazione", () => {
    expect(
      valoreCeProiettato("ce10_var_rimanenze_mat_prime", { overrides: {}, derivati: null, annualizzato }),
    ).toBe(-2864);
  });

  it("una riga assente dal previsionale non vale zero: vale l'annualizzazione", () => {
    expect(
      valoreCeProiettato("ce02_variazioni_rimanenze", {
        overrides: {},
        derivati: { ce10_var_rimanenze_mat_prime: -31000 },
        annualizzato,
      }),
    ).toBe(1000);
  });
});

describe("ceDerivatiDaForecast", () => {
  it("legge solo le righe dedotte dal previsionale persistito", () => {
    expect(
      ceDerivatiDaForecast({
        ce01_ricavi_vendite: 4109510,
        ce02_variazioni_rimanenze: -1000,
        ce10_var_rimanenze_mat_prime: -31000,
      }),
    ).toEqual({ ce02_variazioni_rimanenze: -1000, ce10_var_rimanenze_mat_prime: -31000 });
  });

  it("senza previsionale non inventa zeri", () => {
    expect(ceDerivatiDaForecast(null)).toBeNull();
    expect(ceDerivatiDaForecast(undefined)).toBeNull();
    expect(ceDerivatiDaForecast({ ce01_ricavi_vendite: 100 })).toBeNull();
  });
});
