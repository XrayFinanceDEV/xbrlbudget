import { describe, expect, it } from "vitest";
import type { BalanceSheet, Pregresso } from "@/types/api";
import {
  SENZA_PIANO_BREVE, breveRows, massaBreve, massaOltre, oltreRows, pianoBase, tributariOltreRow, withNonIncassato, withOltreAmount,
  withTributariAmount,
} from "./budget-pregresso-oltre";
import { openingMasses, validatePregresso } from "./budget-pregresso-circolante";

const bs = {
  sp06_crediti_breve: "440000", sp06e_crediti_tributari_breve: "18000", sp06f_imposte_anticipate_breve: "0",
  sp07_crediti_lungo: "30000", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "322000", sp17d_debiti_fornitori_lungo: "0",
  sp16e_debiti_tributari_breve: "61000", sp17e_debiti_tributari_lungo: "35000",
  sp16f_debiti_previdenza_breve: "28000", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "45000", sp17g_altri_debiti_lungo: "40000",
} as unknown as BalanceSheet;
const anni = [2027, 2028, 2029];

describe("budget-pregresso-oltre", () => {
  it("massa a breve e oltre dei saldi commerciali", () => {
    expect(massaBreve(bs, "crediti_commerciali")).toBe(422000);
    expect(massaOltre(bs, "crediti_commerciali")).toBe(30000);
    expect(massaOltre(bs, "altri_debiti")).toBe(40000);
    expect(massaOltre(bs, "debiti_fornitori")).toBe(0);
  });
  it("pianoBase: crediti e fornitori chiudono il breve nel primo anno; previdenziali senza oltre non hanno piano", () => {
    const p = pianoBase(bs, anni, {});
    expect(p.crediti_commerciali).toEqual({ opening: 452000, amounts: [422000, 0, 0], writeoff: null, non_incassato: false });
    expect(p.debiti_fornitori).toEqual({ opening: 322000, amounts: [322000, 0, 0], writeoff: null });
    expect(p.altri_debiti).toEqual({ opening: 85000, amounts: [45000, 0, 0], writeoff: null });
    expect(p.debiti_previdenziali).toBeUndefined();
    expect(pianoBase(bs, anni, p)).toBe(p);   // identita' quando il piano c'e' gia'
  });
  it("oltreRows: righe con massa oltre, stati neutri", () => {
    const rows = oltreRows(bs, pianoBase(bs, anni, {}), anni);
    expect(rows.map((r) => r.key)).toEqual(["crediti_commerciali", "altri_debiti"]);
    expect(rows[0]).toMatchObject({ opening: 30000, amounts: [0, 0, 0], resta: 30000, stato: "nessun movimento nel piano", dir: "in" });
  });
  it("withOltreAmount scrive nell'anno la sola parte oltre e aggiorna resta e stato", () => {
    let p = pianoBase(bs, anni, {});
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 0, 10000);
    expect(p.crediti_commerciali?.amounts).toEqual([432000, 0, 0]);
    const [r] = oltreRows(bs, p, anni);
    expect(r).toMatchObject({ amounts: [10000, 0, 0], resta: 20000, stato: "resta aperto" });
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 1, 20000);
    expect(oltreRows(bs, p, anni)[0].stato).toBe("chiuso");
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 2, 5000);
    expect(oltreRows(bs, p, anni)[0].stato).toBe("oltre il saldo");
  });
  it("non incassati: caselle spente, importi a zero, stato «oltre il piano»", () => {
    const p = withNonIncassato(bs, withOltreAmount(bs, pianoBase(bs, anni, {}), anni, "crediti_commerciali", 0, 10000), anni, true);
    const [r] = oltreRows(bs, p, anni);
    expect(p.crediti_commerciali?.amounts).toEqual([422000, 0, 0]);
    expect(r).toMatchObject({ nonIncassato: true, disabled: true, stato: "oltre il piano" });
  });
  it("una riga oltre senza piano di base: il primo importo scrive anche l'apertura", () => {
    // `altri_debiti` senza parte oltre non ha un piano da `pianoBase` (con un
    // piano il motore li estingue), ma la riga in tabella C'E' perche' e' il
    // secchio di ripiego del passivo circolante. Se chi scrive il primo
    // importo si portasse dietro un'apertura a zero, `validatePregresso`
    // griderebbe «il saldo di apertura non coincide col bilancio base» su una
    // schermata dove l'apertura non si puo' toccare: l'utente non avrebbe via
    // d'uscita se non cancellare la cella.
    const bs2 = { ...bs, sp17g_altri_debiti_lungo: "0" } as unknown as BalanceSheet;
    const p = withOltreAmount(bs2, pianoBase(bs2, anni, {}), anni, "altri_debiti", 1, 10000);
    expect(p.altri_debiti?.opening).toBe(45000);
    expect(p.altri_debiti?.amounts).toEqual([45000, 10000, 0]);
    // E il giudizio e' LO STESSO nei due posti: qui la massa oltre e' zero,
    // quindi 10.000 € scritti in un anno successivo sono «oltre il saldo» per il
    // chip della riga e lo stesso rifiuto per il validatore.
    expect(oltreRows(bs2, p, anni).find((r) => r.key === "altri_debiti")!.stato).toBe("oltre il saldo");
    expect(validatePregresso(p, openingMasses(bs2), anni.length)).toEqual([
      "Altri debiti: gli importi superano il saldo di apertura",
    ]);
    // Con un importo dentro la massa, invece, da qui non arriva alcun errore:
    // perché l'apertura scritta è quella vera, non una a zero.
    const dentro = withOltreAmount(bs2, pianoBase(bs2, anni, {}), anni, "crediti_commerciali", 1, 10000);
    expect(validatePregresso(dentro, openingMasses(bs2), anni.length)).toEqual([]);
  });
  it("breveRows: cinque saldi piu' banche e finanziatori, con l'avviso sui fornitori", () => {
    const rows = breveRows(bs, 2026, "non risultano debiti verso fornitori");
    expect(rows.map((r) => r.label)).toEqual(["Crediti commerciali e altri a breve", "Debiti verso fornitori", "Debiti tributari a breve", "Debiti previdenziali", "Altri debiti a breve", "Debiti verso banche e altri finanziatori"]);
    expect(rows[0]).toMatchObject({ importo: 422000, dir: "in", small: "incassati nel 2027" });
    expect(rows[1].alert).toBe("non risultano debiti verso fornitori");
    expect(rows[2].small).toBe("saldo pagato nel 2027");
  });
});

describe("tributari rateizzati al passo 5", () => {
  it("pianoBase: saldo = debito a breve, rateizzato = debito oltre, rate a zero", () => {
    const p = pianoBase(bs, anni, {});
    expect(p.debiti_tributari).toEqual({ opening: 96000, saldo: 61000, rateizzato: 35000, amounts: [0, 0, 0], acconto_pct: 100 });
  });
  it("senza debito oltre nessun piano tributario", () => {
    const bs0 = { ...bs, sp17e_debiti_tributari_lungo: "0" } as unknown as BalanceSheet;
    expect(pianoBase(bs0, anni, {}).debiti_tributari).toBeUndefined();
    expect(tributariOltreRow(bs0, pianoBase(bs0, anni, {}), anni)).toBeNull();
  });
  it("un piano salvato dal vecchio passo 7 si rispetta", () => {
    const salvato = { debiti_tributari: { opening: 96000, saldo: 50000, rateizzato: 46000, amounts: [23000, 23000], acconto_pct: 80 } } as Pregresso;
    const p = pianoBase(bs, anni, salvato);
    expect(p.debiti_tributari).toEqual(salvato.debiti_tributari);
    expect(tributariOltreRow(bs, p, anni)).toMatchObject({ opening: 46000, amounts: [23000, 23000, null], resta: 0, stato: "chiuso" });
    expect(breveRows(bs, 2026, null, p)[2]).toMatchObject({ importo: 50000, small: "saldo pagato nel 2027" });
  });
  it("un piano salvato su un bilancio base poi rettificato si riallinea al nuovo saldo (TM, 2026-09-18)", () => {
    // Salvato quando i crediti commerciali valevano 452.000 (breve 422.000), con 10.000
    // della parte oltre scadenziati nel primo anno; poi una rettifica toglie 4.619,06 al breve.
    const salvato = {
      crediti_commerciali: { opening: 452000, amounts: [432000, 20000, 0], writeoff: null, non_incassato: false },
      debiti_tributari: { opening: 96000, saldo: 50000, rateizzato: 46000, amounts: [23000, 23000, 0], acconto_pct: 80 },
    } as Pregresso;
    const rettificato = { ...bs, sp06_crediti_breve: "435380.94", sp16e_debiti_tributari_breve: "65000" } as unknown as BalanceSheet;
    const p = pianoBase(rettificato, anni, salvato);
    expect(p.crediti_commerciali).toEqual({ opening: 447380.94, amounts: [427380.94, 20000, 0], writeoff: null, non_incassato: false });
    expect(oltreRows(rettificato, p, anni)[0]).toMatchObject({ amounts: [10000, 20000, 0], resta: 0, stato: "chiuso" });
    // tributari: il rateizzato e le sue rate restano, il saldo assorbe la differenza
    expect(p.debiti_tributari).toEqual({ opening: 100000, saldo: 54000, rateizzato: 46000, amounts: [23000, 23000, 0], acconto_pct: 80 });
    expect(validatePregresso(p, openingMasses(rettificato), anni.length)).toEqual([]);
    expect(pianoBase(rettificato, anni, p)).toBe(p);   // riallineato una volta, poi identita'
  });
  it("withTributariAmount scrive la rata dell'anno e lascia saldo e acconto", () => {
    let p = pianoBase(bs, anni, {});
    p = withTributariAmount(bs, p, anni, 1, 20000);
    expect(p.debiti_tributari).toMatchObject({ saldo: 61000, rateizzato: 35000, amounts: [0, 20000, 0], acconto_pct: 100 });
    expect(tributariOltreRow(bs, p, anni)).toMatchObject({ resta: 15000, stato: "resta aperto" });
    p = withTributariAmount(bs, p, anni, 2, 20000);
    expect(tributariOltreRow(bs, p, anni)?.stato).toBe("oltre il saldo");
  });
});

describe("breveRows · previdenziali e altri debiti senza piano (collaudo R7)", () => {
  it("senza piano non si dicono pagati nel primo anno; col piano si'", () => {
    const senza = breveRows(bs, 2026, null, {});
    expect(senza[3].small).toBe(SENZA_PIANO_BREVE);
    expect(senza[4].small).toBe(SENZA_PIANO_BREVE);
    const con = breveRows(bs, 2026, null, pianoBase(bs, anni, {}));
    expect(con[4].small).toBe("pagati nel 2027");
  });
});
