import { describe, it, expect } from "vitest";
import { badgeScheda, type StatoScheda } from "./pratica-rettifiche-stato";

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
