import { describe, expect, it } from "vitest";
import type { ColonnaCrisi, RatingCrisi } from "@/types/api";
import { RATING_COLOR, vistaColonna } from "@/lib/pratica-crisi";

const rating = (codice: string, segnali: number): RatingCrisi => ({
  codice, etichetta: codice, livello: "verde", oltre: 1, segnali,
});

const colonna: ColonnaCrisi = {
  chiave: "infrannuale",
  anno: 2026,
  period_months: 6,
  indicatori: { dscr: 1.2, _ebitda_raw: 10 },
  punteggi: { dscr: 0.4 },
  rating: rating("A2", 0),
  rating_per_segnali: ["A2", "B2", "B1", "C3", "D", "D", "D", "D"].map(rating),
};

describe("vistaColonna", () => {
  it("sceglie il rating dal numero di segnali IN PAGINA, non da quelli salvati", () => {
    expect(vistaColonna(colonna, 2)!.rating.codice).toBe("B1");
    expect(vistaColonna(colonna, 0)!.rating.codice).toBe("A2");
  });

  it("un conteggio fuori scala resta dentro l'elenco", () => {
    expect(vistaColonna(colonna, 99)!.rating.codice).toBe("D");
    expect(vistaColonna(colonna, -1)!.rating.codice).toBe("A2");
  });

  it("una colonna assente resta assente", () => {
    expect(vistaColonna(null, 0)).toBeNull();
  });

  it("gli indicatori e i punteggi passano come il server li ha calcolati", () => {
    const vista = vistaColonna(colonna, 0)!;
    expect(vista.indicatori.dscr).toBe(1.2);
    expect(vista.indicatori._ebitda_raw).toBe(10);
    expect(vista.punteggi.dscr).toBe(0.4);
  });
});

describe("RATING_COLOR", () => {
  it("ha una classe con la variante dark per ogni livello", () => {
    for (const livello of ["verde", "giallo", "arancio", "rosso"] as const) {
      expect(RATING_COLOR[livello]).toMatch(/^text-\w+-600 dark:text-\w+-400$/);
    }
  });
});
