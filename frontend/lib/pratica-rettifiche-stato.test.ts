import { describe, it, expect } from "vitest";
import {
  badgeScheda,
  contaDaConfermare,
  contaSchedeEsistenti,
  rigaRettifiche,
  type StatoScheda,
} from "./pratica-rettifiche-stato";

/** Scheda non ancora risolta: è lo stato al mount e dopo ogni cambio di identità. */
const inCaricamento: StatoScheda = { resolved: false, exists: true, confirmed: false };
const presente: StatoScheda = { resolved: true, exists: true, confirmed: false };
const presenteConfermata: StatoScheda = { resolved: true, exists: true, confirmed: true };
const assente: StatoScheda = { resolved: true, exists: false, confirmed: false };

describe("badgeScheda — #43", () => {
  it("non mostra alcun badge finché il server non ha risposto", () => {
    // `exists` parte da `true`: senza `resolved` la tab pubblicizzerebbe
    // «da confermare» prima ancora che la fetch sia partita.
    expect(badgeScheda(inCaricamento)).toBeNull();
  });

  it("non mostra alcun badge su una scheda che risponde 404", () => {
    expect(badgeScheda(assente)).toBeNull();
  });

  it("non mostra alcun badge dopo un cambio di identità (exists rialzato a true)", () => {
    expect(badgeScheda({ resolved: false, exists: true, confirmed: true })).toBeNull();
  });

  it("con la scheda presente il badge è quello di oggi", () => {
    expect(badgeScheda(presente)).toBe("da confermare");
    expect(badgeScheda(presenteConfermata)).toBe("confermata");
  });
});

describe("rigaRettifiche — #42", () => {
  it("con il bilancio di verifica mancante nomina la scheda che manca, non «restano 0 schede»", () => {
    // verifica 404, storico presente e confermato: il caso descritto in #42.
    const riga = rigaRettifiche(assente, presenteConfermata, false);
    expect(riga.kind).toBe("verifica-mancante");
  });

  it("con il bilancio di verifica mancante il messaggio non dipende dagli altri contatori", () => {
    for (const storico of [presente, presenteConfermata]) {
      expect(rigaRettifiche(assente, storico, false).kind).toBe("verifica-mancante");
    }
  });

  it("«restano N schede» non compare mai con N = 0", () => {
    const stati: StatoScheda[] = [inCaricamento, presente, presenteConfermata, assente];
    for (const verifica of stati) {
      for (const storico of stati) {
        const tutteConfermate = verifica.confirmed && (!storico.exists || storico.confirmed);
        const riga = rigaRettifiche(verifica, storico, tutteConfermate);
        if (riga.kind === "da-confermare") {
          expect(riga.daConfermare).toBeGreaterThanOrEqual(1);
        }
      }
    }
  });

  it("nessuna scheda: il messaggio generico resta quello di oggi", () => {
    expect(rigaRettifiche(assente, assente, false).kind).toBe("nessuna-scheda");
  });

  it("entrambe confermate", () => {
    const riga = rigaRettifiche(presenteConfermata, presenteConfermata, true);
    expect(riga).toEqual({ kind: "confermate", schedeEsistenti: 2 });
  });

  it("una sola scheda confermata (import senza anno di raffronto)", () => {
    const riga = rigaRettifiche(presenteConfermata, assente, true);
    expect(riga).toEqual({ kind: "confermate", schedeEsistenti: 1 });
  });

  it("due schede da confermare", () => {
    expect(rigaRettifiche(presente, presente, false)).toEqual({
      kind: "da-confermare",
      daConfermare: 2,
      schedeEsistenti: 2,
    });
  });

  it("una sola da confermare quando lo storico è già confermato", () => {
    expect(rigaRettifiche(presente, presenteConfermata, false)).toEqual({
      kind: "da-confermare",
      daConfermare: 1,
      schedeEsistenti: 2,
    });
  });
});

describe("contatori", () => {
  it("contano solo le schede esistenti", () => {
    expect(contaSchedeEsistenti(presente, assente)).toBe(1);
    expect(contaDaConfermare(presente, assente)).toBe(1);
    expect(contaDaConfermare(assente, presenteConfermata)).toBe(0);
  });
});
