import { describe, expect, it } from "vitest";
import { numericDraftState } from "./budget-numeric-draft";

describe("numericDraftState", () => {
  it("keeps the minus while typing and accepts -100 as a complete value", () => {
    expect(numericDraftState("-", true)).toBe("partial");
    expect(numericDraftState("-1", true)).toBe("complete");
    expect(numericDraftState("-100", true)).toBe("complete");
  });

  it("accepts Italian decimals and rejects characters outside a number", () => {
    expect(numericDraftState("-0,5", true)).toBe("complete");
    expect(numericDraftState("-.", true)).toBe("partial");
    expect(numericDraftState("", true)).toBe("partial");
    expect(numericDraftState("12x", true)).toBe("invalid");
    expect(numericDraftState("-1", false)).toBe("invalid");
  });
});
