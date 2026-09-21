import { describe, expect, it } from "vitest";
import { INDICATOR_DEFS, scoreDotColor } from "./pratica-indicators";

// Il calcolo degli indicatori della crisi (insieme, punteggio, rating) sta sul
// server dal 2026-09-21: i suoi casi, con gli stessi fixture che stavano qui,
// sono in `tests/test_crisi_impresa.py`. Qui resta la sola resa.

describe("scoreDotColor", () => {
  it("verde sopra 0,67, giallo in mezzo, rosso sotto 0,33", () => {
    // Valori esatti, non solo differenza a coppie: una mutazione che
    // scambiasse verde e rosso (buono↔cattivo su un rating di rischio
    // creditizio) sopravviverebbe a un semplice `not.toBe`.
    expect(scoreDotColor(0.9)).toBe("bg-green-500");
    expect(scoreDotColor(0.5)).toBe("bg-yellow-500");
    expect(scoreDotColor(0.1)).toBe("bg-red-500");
  });
});

describe("INDICATOR_DEFS", () => {
  it("of_revenue compare in tabella accanto a of_mol, in percentuale", () => {
    const riga = INDICATOR_DEFS.find((d) => d.key === "of_revenue");
    expect(riga).toBeDefined();
    expect(riga!.format).toBe("pct");
    expect(INDICATOR_DEFS.some((d) => d.key === "of_mol")).toBe(true);
  });

  it("le quindici righe nell'ordine del server (`INDICATORI` in crisi_impresa.py)", () => {
    expect(INDICATOR_DEFS.map((d) => d.key)).toEqual([
      "dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
      "copertura_immob", "indipendenza", "pfn", "pfn_ebitda",
      "roi", "roe", "ros", "of_mol", "of_revenue",
    ]);
  });
});
