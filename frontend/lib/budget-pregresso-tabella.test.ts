import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewYear, Pregresso, PregressoKey } from "@/types/api";
import { euro } from "./budget-format";
import { openingMasses } from "./budget-pregresso-circolante";
import {
  TABELLA_KEYS,
  cellPlaceholder,
  cellValue,
  destinoOf,
  legacyNoteFor,
  pregressoRighe,
  residualCell,
  withCell,
  writeoffIgnoredAvvisi,
  writeoffIgnoredByYear,
} from "./budget-pregresso-tabella";

const bs = {
  sp06_crediti_breve: "500", sp06e_crediti_tributari_breve: "20", sp06f_imposte_anticipate_breve: "10",
  sp07_crediti_lungo: "40", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "300", sp17d_debiti_fornitori_lungo: "0", sp16e_debiti_tributari_breve: "61",
  sp17e_debiti_tributari_lungo: "35", sp16f_debiti_previdenza_breve: "41", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "58", sp17g_altri_debiti_lungo: "0",
} as unknown as BalanceSheet;

const masses = openingMasses(bs);

const previewYear = (year: number, ignored: unknown[]): ForecastPreviewYear =>
  ({ year, income_statement: {}, balance_sheet: {},
    details: { pregresso_writeoff_ignored: ignored } } as unknown as ForecastPreviewYear);

describe("budget-pregresso-tabella", () => {
  it("le quattro righe della tabella dichiarano il destino della voce, e i tributari non sono fra loro", () => {
    const righe = pregressoRighe(TABELLA_KEYS, masses, {});
    expect(righe.map((r) => r.key)).toEqual([
      "crediti_commerciali", "debiti_fornitori", "debiti_previdenziali", "altri_debiti",
    ]);
    expect(TABELLA_KEYS).not.toContain("debiti_tributari" as PregressoKey);
    expect(righe.map((r) => r.destino)).toEqual(["rigenera", "rigenera", "estingue", "estingue"]);
    expect(righe[0].mass).toBe(510);
    expect(righe[3].mass).toBe(58);
    // Solo i crediti hanno un inesigibile: il motore legge `writeoff` sul solo
    // piano dei crediti commerciali.
    expect(righe.map((r) => r.writeoff)).toEqual([true, false, false, false]);
  });

  // I tributari non stanno in TABELLA_KEYS: la loro riga la rende il passo 7,
  // dove la tabella scadenzia il rateizzato. Non si rigenerano dal circolante
  // — si rigenerano dalle IMPOSTE dell'anno, e non si estinguono: una nota che
  // dicesse «va a zero e ci resta» sarebbe falsa sul saldo che il piano genera
  // ogni anno.
  it("il destino dei tributari e' le imposte: si rigenera, ma non da un driver di volume", () => {
    expect(destinoOf("debiti_tributari")).toBe("imposte");
    const riga = pregressoRighe(["debiti_tributari"], masses, {})[0];
    expect(riga.destinoNota).toMatch(/rateizzato/);
    expect(riga.destinoNota).not.toMatch(/passo Imposte/);
  });

  it("cellValue: euro mostra l'importo, pct l'incidenza sulla massa, e un anno mai toccato resta vuoto", () => {
    const plan = { opening: 1000, amounts: [250, 0], writeoff: [50] };
    expect(cellValue(plan, 0, "eur", "amounts")).toBe(250);
    expect(cellValue(plan, 1, "eur", "amounts")).toBe(0);
    expect(cellValue(plan, 2, "eur", "amounts")).toBeNull();
    expect(cellValue(plan, 0, "pct", "amounts")).toBe(25);
    expect(cellValue(plan, 0, "eur", "writeoff")).toBe(50);
    expect(cellValue(plan, 0, "pct", "writeoff")).toBe(5);
    expect(cellValue(null, 0, "eur", "amounts")).toBeNull();
  });

  it("cellValue in pct arrotonda a due decimali, cosi' il campo resta digitabile", () => {
    // 1 su 3 = 33,333333…%: senza arrotondamento il campo mostra 16 cifre.
    expect(cellValue({ opening: 3, amounts: [1] }, 0, "pct", "amounts")).toBe(33.33);
  });

  it("cellValue in pct su una massa nulla non e' un'incidenza di zero", () => {
    expect(cellValue({ opening: 0, amounts: [0] }, 0, "pct", "amounts")).toBeNull();
  });

  it("withCell crea il piano al primo tocco con l'apertura del bilancio base", () => {
    const next = withCell({}, "altri_debiti", masses, 0, 20, "eur", "amounts");
    expect(next.altri_debiti).toEqual({ opening: 58, amounts: [20] });
  });

  it("withCell in pct scrive l'EURO, che e' l'importo canonico, non la percentuale", () => {
    const next = withCell({}, "debiti_fornitori", masses, 1, 50, "pct", "amounts");
    // 50% di 300 = 150, scritto nel secondo anno; il primo resta a zero.
    expect(next.debiti_fornitori).toEqual({ opening: 300, amounts: [0, 150] });
  });

  it("withCell scrive l'inesigibile senza toccare gli importi, e viceversa", () => {
    const uno = withCell({}, "crediti_commerciali", masses, 0, 100, "eur", "amounts");
    const due = withCell(uno, "crediti_commerciali", masses, 1, 30, "eur", "writeoff");
    expect(due.crediti_commerciali).toEqual({ opening: 510, amounts: [100], writeoff: [0, 30] });
    expect(uno.crediti_commerciali).toEqual({ opening: 510, amounts: [100] });
  });

  it("withCell con valore nullo azzera la cella e, se il piano e' tutto a zero, torna null (rilievo 2)", () => {
    // Prima del giro di correzione 1 svuotare l'unica cella toccata dava
    // {opening, amounts:[0]}: un piano fantasma da cui l'interfaccia non
    // aveva modo di tornare a "nessun piano".
    const uno = withCell({}, "altri_debiti", masses, 0, 20, "eur", "amounts");
    const due = withCell(uno, "altri_debiti", masses, 0, null, "eur", "amounts");
    expect(due.altri_debiti).toBeNull();
  });

  it("withCell: un piano con ALMENO un importo non nullo resta un piano, anche con altri anni a zero", () => {
    const uno = withCell({}, "altri_debiti", masses, 0, 20, "eur", "amounts");
    const due = withCell(uno, "altri_debiti", masses, 1, 0, "eur", "amounts");
    expect(due.altri_debiti).toEqual({ opening: 58, amounts: [20, 0] });
  });

  it("withCell: l'inesigibile a zero da solo non tiene vivo un piano di importi vuoto", () => {
    const uno = withCell({}, "crediti_commerciali", masses, 0, 0, "eur", "writeoff");
    expect(uno.crediti_commerciali).toBeNull();
  });

  it("residualCell: senza piano il residuo e' ZERO, coerente con l'anteprima (rilievo 4)", () => {
    // Prima del giro di correzione 1 la colonna Residuo mostrava la massa
    // intera anche senza piano, mentre l'anteprima diceva "tutto nel primo
    // anno" sulla stessa riga: due schermate, due verita' opposte.
    expect(residualCell(null, 2)).toBe(0);
    expect(residualCell({ opening: 58, amounts: [20, 20] }, 2)).toBe(18);
    expect(residualCell({ opening: 510, amounts: [400], writeoff: [10] }, 0)).toBe(100);
  });

  it("cellPlaceholder: riga senza piano, PRIMA colonna dice 'tutto nel primo anno'", () => {
    expect(cellPlaceholder(null, 0, "eur")).toBe("tutto nel primo anno");
    expect(cellPlaceholder(null, 0, "pct")).toBe("tutto nel primo anno");
  });

  it("cellPlaceholder: le altre colonne, e ogni cella con un piano, restano l'unita' di misura", () => {
    expect(cellPlaceholder(null, 1, "eur")).toBe("€");
    expect(cellPlaceholder(null, 2, "pct")).toBe("%");
    const plan = { opening: 100, amounts: [10] };
    expect(cellPlaceholder(plan, 0, "eur")).toBe("€");
    expect(cellPlaceholder(plan, 0, "pct")).toBe("%");
  });

  it("writeoffIgnoredAvvisi nomina l'anno, l'importo e l'override che ha vinto", () => {
    const avvisi = writeoffIgnoredAvvisi([
      previewYear(2026, []),
      previewYear(2027, [{ saldo: "crediti_commerciali", field: "ce09d_svalutazione_crediti", requested: 5000, reason: "ce09d_override" }]),
    ]);
    expect(avvisi).toHaveLength(1);
    expect(avvisi[0]).toContain("2027");
    expect(avvisi[0]).toContain(euro(5000));
    expect(avvisi[0]).toMatch(/Svalutazione crediti/);
    expect(avvisi[0]).toMatch(/resta a bilancio/);
  });

  it("writeoffIgnoredAvvisi: chiave assente vale zero, non un avviso", () => {
    const senzaChiave = { year: 2026, income_statement: {}, balance_sheet: {}, details: {} } as unknown as ForecastPreviewYear;
    expect(writeoffIgnoredAvvisi([senzaChiave])).toEqual([]);
    expect(writeoffIgnoredAvvisi([])).toEqual([]);
  });

  it("pregressoRighe porta il piano gia' dichiarato, e `null` dove non c'e'", () => {
    const p: Pregresso = { debiti_fornitori: { opening: 300, amounts: [300] } };
    const righe = pregressoRighe(TABELLA_KEYS, masses, p);
    expect(righe[1].plan).toEqual({ opening: 300, amounts: [300] });
    expect(righe[0].plan).toBeNull();
  });

  // ── La nota di destino, condizionata alla massa lunga (rilievo 1) ─────────
  // Ogni frase ha un test che la fissa alla lettera (rilievo 5): scambiare
  // "si rigenera" con "non si rigenera" — o rendere la nota indifferente alla
  // massa lunga — deve far fallire la suite.
  describe("destinoNota (rilievo 1 + rilievo 5)", () => {
    const zeroLong: Record<PregressoKey, number> = {
      crediti_commerciali: 0, debiti_fornitori: 0, debiti_tributari: 0, debiti_previdenziali: 0, altri_debiti: 0,
    };

    it("senza massesLong (default) fornitori e crediti restano 'Si rigenera', senza condizioni", () => {
      const righe = pregressoRighe(TABELLA_KEYS, masses, {});
      expect(righe[0].destinoNota).toBe(
        "Si rigenera: il previsionale ne crea di nuovi dal volume d'affari, quindi qui decidi solo quando rientra il pregresso.",
      );
      expect(righe[1].destinoNota).toBe(righe[0].destinoNota);
    });

    it("con massesLong tutta a zero il comportamento e' identico all'assenza del parametro", () => {
      const righe = pregressoRighe(TABELLA_KEYS, masses, {}, zeroLong);
      expect(righe[0].destinoNota).toMatch(/^Si rigenera:/);
      expect(righe[1].destinoNota).toMatch(/^Si rigenera:/);
    });

    it("con massa oltre l'esercizio > 0, debiti_fornitori dice che il lato lungo SI ESTINGUE, non che si rigenera", () => {
      const massesLong = { ...zeroLong, debiti_fornitori: 21110 };
      const riga = pregressoRighe(["debiti_fornitori"], masses, {}, massesLong)[0];
      expect(riga.destinoNota).toBe(
        "Il lato a breve si rigenera dai giorni medi; la parte oltre l'esercizio " +
        `(${euro(21110)}) si estingue con questo piano e smette di crescere alla sua percentuale.`,
      );
      expect(riga.destinoNota).not.toMatch(/^Si rigenera:/);
    });

    it("con massa oltre l'esercizio > 0, crediti_commerciali ha la stessa nota condizionata", () => {
      const massesLong = { ...zeroLong, crediti_commerciali: 10666.5 };
      const riga = pregressoRighe(["crediti_commerciali"], masses, {}, massesLong)[0];
      expect(riga.destinoNota).toContain(euro(10666.5));
      expect(riga.destinoNota).toContain("si estingue con questo piano");
    });

    it("'estingue' e 'imposte' non cambiano con la massa lunga: sono vere su tutta la massa per costruzione", () => {
      const massesLong = { ...zeroLong, debiti_previdenziali: 5000, altri_debiti: 5000, debiti_tributari: 5000 };
      const righe = pregressoRighe(
        ["debiti_previdenziali", "altri_debiti", "debiti_tributari"], masses, {}, massesLong,
      );
      expect(righe[0].destinoNota).toBe(
        "Non si rigenera: il previsionale non ne crea di nuovi, quindi ciò che scadenzi qui va a zero e ci resta per tutto il piano.",
      );
      expect(righe[1].destinoNota).toBe(righe[0].destinoNota);
      expect(righe[2].destinoNota).toMatch(/rateizzato/);
      expect(righe[2].destinoNota).not.toMatch(/€/);
    });
  });

  describe("legacyNoteFor (rilievo 4)", () => {
    it("fornitori e crediti: un driver li rigenera comunque, la chiusura nel primo anno resta vera", () => {
      expect(legacyNoteFor("debiti_fornitori")).toBe("nessun piano: tutto nel primo anno, poi si rigenera dal volume d'affari");
      expect(legacyNoteFor("crediti_commerciali")).toBe(legacyNoteFor("debiti_fornitori"));
    });

    it("previdenziali e altri debiti: nessun driver, NON si chiudono — crescono per percentuale", () => {
      expect(legacyNoteFor("debiti_previdenziali")).toBe(
        "nessun piano: non si chiude — cresce ogni anno della percentuale impostata",
      );
      expect(legacyNoteFor("altri_debiti")).toBe(legacyNoteFor("debiti_previdenziali"));
      expect(legacyNoteFor("altri_debiti")).not.toBe(legacyNoteFor("debiti_fornitori"));
    });

    it("i tributari si rigenerano dalle imposte, non dal volume: nota propria", () => {
      expect(legacyNoteFor("debiti_tributari")).toBe("nessun piano: tutto nel primo anno, poi si rigenera dalle imposte dell'anno");
    });
  });

  describe("writeoffIgnoredByYear (rilievo 6)", () => {
    it("indicizza l'avviso sull'anno, con lo stesso importo e la stessa etichetta di writeoffIgnoredAvvisi", () => {
      const m = writeoffIgnoredByYear([
        previewYear(2026, []),
        previewYear(2027, [
          { saldo: "crediti_commerciali", field: "ce09d_svalutazione_crediti", requested: 5000, reason: "ce09d_override" },
        ]),
      ]);
      expect(Object.keys(m)).toEqual(["2027"]);
      expect(m[2027]).toContain(euro(5000));
      expect(m[2027]).toMatch(/Svalutazione crediti/);
    });

    it("chiave assente vale zero, non un avviso", () => {
      expect(writeoffIgnoredByYear([previewYear(2026, [])])).toEqual({});
      expect(writeoffIgnoredByYear([])).toEqual({});
    });
  });
});
