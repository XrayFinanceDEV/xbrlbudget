import { describe, it, expect } from "vitest";
import { hrefGuida, srcImmagineGuida } from "./guida";

describe("guida in app", () => {
  it("le schermate passano da docs/images/guida a /guida", () => {
    expect(srcImmagineGuida("images/guida/01-home.jpg")).toBe("/guida/01-home.jpg");
    expect(srcImmagineGuida("https://example.com/x.png")).toBe("https://example.com/x.png");
    expect(srcImmagineGuida(undefined)).toBeUndefined();
  });

  it("restano link solo le ancore e gli indirizzi web", () => {
    expect(hrefGuida("#3-rettifiche")).toBe("#3-rettifiche");
    expect(hrefGuida("https://formulafinance.it")).toBe("https://formulafinance.it");
    expect(hrefGuida("budget/FORECASTING_GUIDE.md")).toBeNull();
    expect(hrefGuida("frontend/RETTIFICHE.md#2")).toBeNull();
    expect(hrefGuida(undefined)).toBeNull();
  });
});
