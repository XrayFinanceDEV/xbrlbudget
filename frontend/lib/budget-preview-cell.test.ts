import { describe, expect, it } from "vitest";
import { describeCell, rowClass } from "./budget-preview-cell";

describe("describeCell", () => {
  it("un valore assente con una percentuale vera mostra la percentuale, non solo il trattino (C1)", () => {
    const d = describeCell({ value: null, pct: 21 });
    expect(d.main).toBe("—");
    expect(d.sub).not.toBeNull();
    expect(d.sub).toContain("21");
  });

  it("un valore vero con una nota porta anche la nota (I2)", () => {
    const d = describeCell({ value: 1000, note: "forzato in CE Prev." });
    expect(d.main).not.toBe("—");
    expect(d.note).toBe("forzato in CE Prev.");
  });

  it("un valore assente puro da' il trattino e niente sotto-riga", () => {
    const d = describeCell({ value: null });
    expect(d.main).toBe("—");
    expect(d.sub).toBeNull();
    expect(d.note).toBeNull();
  });

  it("uno zero e' uno zero formattato, non un trattino", () => {
    const d = describeCell({ value: 0 });
    expect(d.main).not.toBe("—");
    expect(d.main).toMatch(/0/);
  });

  it("giorni quando non c'e' percentuale", () => {
    const d = describeCell({ value: 30, days: 45 });
    expect(d.sub).toBe("45 gg");
  });

  it("la percentuale ha precedenza sui giorni se entrambi presenti", () => {
    const d = describeCell({ value: 30, pct: 5, days: 45 });
    expect(d.sub).not.toBe("45 gg");
  });
});

describe("rowClass", () => {
  it("da' una classe per ciascuno dei quattro kind", () => {
    expect(rowClass("value")).toBe("");
    expect(rowClass("sub")).toContain("text-muted-foreground");
    expect(rowClass("total")).toContain("border-t");
    expect(rowClass("kpi")).toContain("font-semibold");
  });
});
