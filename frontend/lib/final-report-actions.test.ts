import { describe, expect, it, vi } from "vitest";

import { regenerateFinalReport } from "./final-report-actions";

describe("regenerateFinalReport", () => {
  it("runs the real generation callback before refetching the stale report", async () => {
    const generate = vi.fn().mockResolvedValue({ generated: true });
    const refetch = vi.fn().mockResolvedValue({ error: null });

    await regenerateFinalReport(generate, refetch);

    expect(generate).toHaveBeenCalledOnce();
    expect(refetch).toHaveBeenCalledOnce();
    expect(generate.mock.invocationCallOrder[0]).toBeLessThan(refetch.mock.invocationCallOrder[0]);
  });

  it("does not allow a success path when refetch returns an error result", async () => {
    const refetchError = new Error("modello non ricaricato");
    await expect(regenerateFinalReport(
      vi.fn().mockResolvedValue({ generated: true }),
      vi.fn().mockResolvedValue({ error: refetchError }),
    )).rejects.toThrow("modello non ricaricato");
  });
});
