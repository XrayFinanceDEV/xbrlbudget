import { describe, expect, it } from "vitest";
import { VOCI, labelOf, voce } from "./ivcee-catalog";
import { ATTIVO_CODES, PASSIVO_CODES } from "./pratica-codes";

describe("catalogo IV-CEE", () => {
  it("ogni codice compare una volta sola", () => {
    const codes = VOCI.map((v) => v.code);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it("nessun padre punta a un codice inesistente", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const orfani = VOCI.filter((v) => v.parent !== null && !known.has(v.parent));
    expect(orfani.map((v) => v.code)).toEqual([]);
  });

  it("nessuna voce è padre di sé stessa", () => {
    expect(VOCI.filter((v) => v.parent === v.code).map((v) => v.code)).toEqual([]);
  });

  it("l'ordine è totale: nessun pari condivide indice sotto lo stesso padre", () => {
    const visti = new Set<string>();
    const collisioni: string[] = [];
    for (const v of VOCI) {
      const k = `${v.section}|${v.parent ?? "-"}|${v.order}`;
      if (visti.has(k)) collisioni.push(v.code);
      visti.add(k);
    }
    expect(collisioni).toEqual([]);
  });

  it("ogni voce ha un'etichetta autonoma non vuota e senza rientri", () => {
    const cattive = VOCI.filter((v) => v.label.trim() === "" || v.label !== v.label.trim());
    expect(cattive.map((v) => v.code)).toEqual([]);
  });

  it("l'etichetta contestuale, quando c'è, è diversa dall'autonoma", () => {
    const inutili = VOCI.filter((v) => v.shortLabel !== undefined && v.shortLabel === v.label);
    expect(inutili.map((v) => v.code)).toEqual([]);
  });

  it("copre ogni aggregato di primo livello dello stato patrimoniale", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const mancanti = [...ATTIVO_CODES, ...PASSIVO_CODES].filter((c) => !known.has(c));
    expect(mancanti).toEqual([]);
  });

  it("labelOf sceglie il ruolo giusto e non restituisce mai vuoto", () => {
    expect(labelOf("sp16d_debiti_fornitori_breve")).toBe("Debiti vs fornitori (entro)");
    expect(labelOf("sp16d_debiti_fornitori_breve", "contestuale")).toBe("entro 12 mesi");
    expect(labelOf("sp02_immob_immateriali")).toBe("I - Immobilizzazioni immateriali");
    expect(labelOf("codice_inventato")).toBe("codice_inventato");
  });

  it("voce() trova per codice", () => {
    expect(voce("sp09_disponibilita_liquide")?.section).toBe("attivo");
    expect(voce("codice_inventato")).toBeUndefined();
  });
});
