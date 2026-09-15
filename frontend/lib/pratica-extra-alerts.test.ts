import { describe, expect, it } from "vitest";

import { EXTRA_ALERT_DEFS } from "./pratica-codes";
import {
  EXTRA_ALERT_KEYS,
  canSaveExtraAlerts,
  createEmptyExtraAlerts,
  extraAlertsDirty,
  normalizeExtraAlerts,
  serializeExtraAlerts,
} from "./pratica-extra-alerts";

// Sette chiavi esatte, nell'ordine del catalogo, senza duplicati.
const KEYS = [
  "retribuzioni",
  "fornitori",
  "banche",
  "inps",
  "inail",
  "riscossione",
  "iva",
] as const;

function withFlag(key: string, value: boolean) {
  const state = createEmptyExtraAlerts() as Record<string, boolean>;
  state[key] = value;
  return state;
}

describe("parità delle chiavi con pratica-codes", () => {
  it("EXTRA_ALERT_KEYS è esattamente la lista delle sette chiavi", () => {
    expect([...EXTRA_ALERT_KEYS]).toEqual(KEYS);
  });

  it("le chiavi coincidono con EXTRA_ALERT_DEFS, ordine compreso", () => {
    expect(EXTRA_ALERT_DEFS.map((def) => def.key)).toEqual([...EXTRA_ALERT_KEYS]);
  });

  it("normalizzazione e serializzazione producono sempre e sole sette chiavi", () => {
    for (const input of [null, undefined, {}, createEmptyExtraAlerts()]) {
      expect(Object.keys(normalizeExtraAlerts(input)).sort()).toEqual(
        [...KEYS].sort(),
      );
      expect(Object.keys(serializeExtraAlerts(input)).sort()).toEqual(
        [...KEYS].sort(),
      );
    }
  });
});

describe("normalizeExtraAlerts", () => {
  it("null, undefined e non-oggetti diventano tutto false", () => {
    for (const input of [null, undefined, "no", 42, true, [], {}, NaN]) {
      expect(normalizeExtraAlerts(input)).toEqual(createEmptyExtraAlerts());
    }
  });

  it("preserva true e false espliciti, chiave per chiave", () => {
    for (const key of KEYS) {
      expect(normalizeExtraAlerts(withFlag(key, true))).toEqual(withFlag(key, true));
      expect(normalizeExtraAlerts(withFlag(key, false))).toEqual(
        createEmptyExtraAlerts(),
      );
    }
  });

  it("un oggetto parziale lascia false le chiavi mancanti", () => {
    expect(normalizeExtraAlerts({ banche: true })).toEqual(
      withFlag("banche", true),
    );
    expect(
      normalizeExtraAlerts({ retribuzioni: true, iva: false, inps: true }),
    ).toEqual({
      ...createEmptyExtraAlerts(),
      retribuzioni: true,
      iva: false,
      inps: true,
    });
  });

  it("scarta le chiavi sconosciute (extra=forbid sul server)", () => {
    const out = normalizeExtraAlerts({
      ...createEmptyExtraAlerts(),
      campo_inventato: true,
      updated_at: "2026-09-14T00:00:00Z",
    });
    expect(Object.keys(out)).toHaveLength(7);
    expect(out).toEqual(createEmptyExtraAlerts());
  });

  it("i valori non booleani non sono mai veri (StrictBool)", () => {
    for (const value of ["true", 1, 0, null, {}, [], "false"]) {
      expect(normalizeExtraAlerts({ banche: value })).toEqual(
        createEmptyExtraAlerts(),
      );
    }
  });

  it("le proprietà ereditate dal prototipo non contano", () => {
    const proto = { iva: true } as Record<string, unknown>;
    const input = Object.create(proto) as Record<string, unknown>;
    input.banche = true;
    expect(normalizeExtraAlerts(input)).toEqual(withFlag("banche", true));
  });

  it("restituisce sempre una nuova istanza, mai l'input", () => {
    const input = { banche: true } as Record<string, unknown>;
    const out = normalizeExtraAlerts(input);
    out.banche = false;
    expect(input.banche).toBe(true);
  });
});

describe("serializeExtraAlerts", () => {
  it("emette sempre tutte e sette le chiavi", () => {
    const payload = serializeExtraAlerts(createEmptyExtraAlerts());
    expect(payload).toEqual({
      retribuzioni: false,
      fornitori: false,
      banche: false,
      inps: false,
      inail: false,
      riscossione: false,
      iva: false,
    });
  });

  it("preserva i false espliciti: nessuna chiave viene omessa", () => {
    const state = { ...createEmptyExtraAlerts(), inps: true };
    const payload = serializeExtraAlerts(state);
    for (const key of KEYS) {
      expect(key in payload).toBe(true);
      expect(typeof payload[key]).toBe("boolean");
    }
    expect(payload.inps).toBe(true);
    expect(payload.banche).toBe(false);
  });

  it("non lascia mai uscire chiavi sconosciute, nemmeno se in stato sporco", () => {
    const dirty = {
      ...createEmptyExtraAlerts(),
      banche: true,
      fantasma: true,
    } as ReturnType<typeof createEmptyExtraAlerts> & Record<string, unknown>;
    const payload = serializeExtraAlerts(dirty);
    expect(Object.keys(payload).sort()).toEqual([...KEYS].sort());
    expect(payload.banche).toBe(true);
  });

  it("normalizza un input grezzo (parziale o null) come la normalize", () => {
    expect(serializeExtraAlerts(null)).toEqual(createEmptyExtraAlerts());
    expect(serializeExtraAlerts({ iva: "sì" })).toEqual(createEmptyExtraAlerts());
    expect(serializeExtraAlerts({ iva: true })).toEqual(withFlag("iva", true));
  });
});

describe("extraAlertsDirty", () => {
  it("null caricato equivale a tutto false", () => {
    expect(extraAlertsDirty(createEmptyExtraAlerts(), null)).toBe(false);
    expect(extraAlertsDirty(createEmptyExtraAlerts(), undefined)).toBe(false);
  });

  it("una flip su qualunque chiave è sporca", () => {
    for (const key of KEYS) {
      expect(
        extraAlertsDirty(withFlag(key, true), createEmptyExtraAlerts()),
      ).toBe(true);
      expect(
        extraAlertsDirty(createEmptyExtraAlerts(), withFlag(key, true)),
      ).toBe(true);
    }
  });

  it("flip e ripristino non sono sporchi", () => {
    const loaded = withFlag("banche", true);
    const flipped = { ...loaded, banche: false, inail: true };
    expect(extraAlertsDirty(flipped, loaded)).toBe(true);
    expect(extraAlertsDirty(loaded, flipped)).toBe(true);
    expect(extraAlertsDirty({ ...loaded }, loaded)).toBe(false);
    expect(extraAlertsDirty(serializeExtraAlerts(flipped), flipped)).toBe(false);
  });

  it("confronta da normalizzato: snapshot parziale o chiavi extra non sporcano", () => {
    // {banche:true} e il suo equivalente completo: nessuna differenza.
    expect(extraAlertsDirty(withFlag("banche", true), { banche: true })).toBe(
      false,
    );
    expect(
      extraAlertsDirty(withFlag("banche", true), {
        ...createEmptyExtraAlerts(),
        banche: true,
        campo_extra: "x",
      }),
    ).toBe(false);
    // Un true "spacciato" per stringa è false normalizzato: se il corrente
    // è davvero true, la differenza c'è ed è sporca.
    expect(extraAlertsDirty(withFlag("banche", true), { banche: "true" })).toBe(
      true,
    );
  });
});

describe("canSaveExtraAlerts", () => {
  it("blocca il salvataggio finché la GET dello scenario corrente non riesce", () => {
    expect(
      canSaveExtraAlerts({ dirty: true, loaded: false, loading: false, saving: false }),
    ).toBe(false);
    expect(
      canSaveExtraAlerts({ dirty: true, loaded: false, loading: true, saving: false }),
    ).toBe(false);
  });

  it("permette il retry dopo un PUT fallito, ma non durante load o save", () => {
    expect(
      canSaveExtraAlerts({ dirty: true, loaded: true, loading: false, saving: false }),
    ).toBe(true);
    expect(
      canSaveExtraAlerts({ dirty: true, loaded: true, loading: true, saving: false }),
    ).toBe(false);
    expect(
      canSaveExtraAlerts({ dirty: true, loaded: true, loading: false, saving: true }),
    ).toBe(false);
    expect(
      canSaveExtraAlerts({ dirty: false, loaded: true, loading: false, saving: false }),
    ).toBe(false);
  });
});
