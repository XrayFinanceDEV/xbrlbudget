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

  // `topLevelOrder`/`childOrder` terminano in Array.indexOf: una voce assente
  // dal rispettivo elenco d'ordine riceve -1 invece di fallire. Il test
  // sull'"ordine totale" qui sopra non lo vede, perché un solo -1 per padre non
  // collide con nessuno. Questo lo vede.
  it("nessuna voce resta senza ordine (-1)", () => {
    expect(VOCI.filter((v) => v.order < 0).map((v) => v.code)).toEqual([]);
  });

  // labelFor() degrada al codice stesso quando nessuna fonte etichetta una
  // voce, per non far esplodere il caricamento del modulo. La degradazione non
  // deve però restare inosservata: qui è un errore.
  it("nessuna etichetta è il codice stesso (fonte dell'etichetta mancante)", () => {
    expect(VOCI.filter((v) => v.label === v.code).map((v) => v.code)).toEqual([]);
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

import { aggregate, childrenOf, sectionRows, subtree } from "./ivcee-catalog";

describe("proiezioni", () => {
  it("childrenOf restituisce i figli diretti in ordine", () => {
    const figli = childrenOf("sp16_debiti_breve").map((v) => v.code);
    expect(figli).toEqual([
      "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
      "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
      "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
      "sp16g_altri_debiti_breve",
    ]);
  });

  it("childrenOf su una foglia restituisce l'elenco vuoto", () => {
    expect(childrenOf("sp09_disponibilita_liquide")).toEqual([]);
  });

  it("subtree include il codice stesso e la discendenza", () => {
    const t = subtree("sp16_debiti_breve").map((v) => v.code);
    expect(t[0]).toBe("sp16_debiti_breve");
    expect(t).toHaveLength(8);
  });

  it("aggregate somma le foglie, non il padre", () => {
    const values = {
      sp16_debiti_breve: 999,          // ignorato: il padre ha figli
      sp16a_debiti_banche_breve: 100,
      sp16d_debiti_fornitori_breve: 250,
    };
    expect(aggregate(values, "sp16_debiti_breve")).toBe(350);
  });

  it("aggregate su una foglia restituisce il suo valore", () => {
    expect(aggregate({ sp09_disponibilita_liquide: 42 }, "sp09_disponibilita_liquide")).toBe(42);
  });

  it("aggregate su valori assenti vale zero, non NaN", () => {
    expect(aggregate({}, "sp16_debiti_breve")).toBe(0);
  });

  it("sectionRows limita la profondità", () => {
    const primoLivello = sectionRows("passivo", 0).map((v) => v.code);
    expect(primoLivello).toContain("sp16_debiti_breve");
    expect(primoLivello).not.toContain("sp16a_debiti_banche_breve");

    const tutto = sectionRows("passivo").map((v) => v.code);
    expect(tutto).toContain("sp16a_debiti_banche_breve");
  });
});
