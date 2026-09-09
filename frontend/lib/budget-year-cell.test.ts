import { describe, expect, it } from "vitest";
import { yearCellState } from "./budget-year-cell";

describe("yearCellState", () => {
  it("una riga senza nulla di spento e' viva su ogni anno, e non porta tooltip", () => {
    for (const y of [2027, 2028, 2029]) {
      expect(yearCellState({}, y)).toEqual({ disabled: false });
    }
  });

  it("un anno forzato su tre spegne QUELL'anno: gli altri due restano modificabili", () => {
    const row = {
      offYears: [2027],
      offYearsNote: "Forzato in CE Prev.",
    };
    expect(yearCellState(row, 2027)).toEqual({ disabled: true, title: "Forzato in CE Prev." });
    expect(yearCellState(row, 2028).disabled).toBe(false);
    expect(yearCellState(row, 2029).disabled).toBe(false);
  });

  it("nessun anno forzato: nessuna cella si spegne", () => {
    const row = { offYears: [], offYearsNote: "Forzato in CE Prev." };
    for (const y of [2027, 2028, 2029]) {
      expect(yearCellState(row, y)).toEqual({ disabled: false });
    }
  });

  it("la riga intera spenta batte gli anni, e porta la SUA spiegazione", () => {
    const row = {
      off: true,
      offNote: "A quota fissa 100% non resta parte variabile",
      offYears: [2027],
      offYearsNote: "Forzato in CE Prev.",
    };
    expect(yearCellState(row, 2028)).toEqual({
      disabled: true, title: "A quota fissa 100% non resta parte variabile",
    });
    expect(yearCellState(row, 2027).title).toBe("A quota fissa 100% non resta parte variabile");
  });

  it("una cella spenta senza spiegazione resta spenta: il tooltip manca, il disabled no", () => {
    // Meglio nessun tooltip che un tooltip inventato — ma la casella non deve
    // MAI restare digitabile solo perche' nessuno ha scritto il perche'.
    expect(yearCellState({ off: true }, 2027)).toEqual({ disabled: true, title: undefined });
    expect(yearCellState({ offYears: [2027] }, 2027)).toEqual({ disabled: true, title: undefined });
  });
});
