import { describe, it, expect } from "vitest";
import { projectedItemsFromForecast } from "@/lib/pratica-projected-bs";
import type { IntraYearComparisonItem } from "@/types/api";

/**
 * Lo SP proiettato arriva dal motore Python: qui si prova che la pagina lo
 * legge, non che lo ricalcoli. Il motore client che stava in questo modulo è
 * stato tolto (#22, #39, #40, #41).
 */
describe("projectedItemsFromForecast", () => {
  const item = (
    code: string,
    partial: number,
    reference = 0,
  ): IntraYearComparisonItem => ({
    code,
    label: code,
    partial_value: partial,
    reference_value: reference,
    prior_value: 0,
    pct_of_reference: 0,
    annualized_value: 0,
  });

  // Il valore mostrato deve venire dal motore, non dal periodo parziale: è
  // tutta la ragione per cui il calcolo lato client è stato tolto. Le quote
  // residue di ammortamento (#41) vivono solo dentro `forecastBS`.
  it("prende il valore proiettato dal forecast del server, non dal parziale", () => {
    const out = projectedItemsFromForecast(
      [item("sp03_immob_materiali", 500_000)],
      { sp03_immob_materiali: 470_000 },
    );
    expect(out).not.toBeNull();
    expect(out![0].annualized_value).toBe(470_000);
  });

  it("senza forecast non c'e' proiezione da mostrare", () => {
    const items = [item("sp03_immob_materiali", 500_000)];
    expect(projectedItemsFromForecast(items, undefined)).toBeNull();
    expect(projectedItemsFromForecast(items, null)).toBeNull();
    expect(projectedItemsFromForecast(items, {})).toBeNull();
  });

  // Il motore proietta anche i sotto-campi, ma se una voce non arriva la si
  // porta avanti dal parziale invece di lasciarla a zero: e' il ripiego che il
  // percorso di ripristino applica da sempre, qui dichiarato invece che
  // implicito.
  it("porta avanti dal parziale una voce che il forecast non contiene", () => {
    const out = projectedItemsFromForecast(
      [item("sp16c_debiti_fornitori_breve", 88_000)],
      { sp03_immob_materiali: 470_000 },
    );
    expect(out![0].annualized_value).toBe(88_000);
  });

  it("conserva tutte le voci e i loro altri valori", () => {
    const out = projectedItemsFromForecast(
      [item("sp03_immob_materiali", 500_000, 520_000), item("sp09_disponibilita_liquide", 10_000)],
      { sp03_immob_materiali: 470_000, sp09_disponibilita_liquide: 31_500 },
    );
    expect(out!.map((i) => i.code)).toEqual([
      "sp03_immob_materiali",
      "sp09_disponibilita_liquide",
    ]);
    expect(out![0].reference_value).toBe(520_000);
    expect(out![1].annualized_value).toBe(31_500);
  });
});
