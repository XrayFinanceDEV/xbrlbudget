import { describe, expect, it, vi } from "vitest";
import {
  FinalReportDownloadError,
  createDownloadGuardState,
  isRetryableDownloadStatus,
  resolveDownloadErrorMessage,
  resolveDownloadFilename,
  saveBlobAsFile,
  withDownloadGuard,
  type FinalReportDownloadSink,
} from "./final-report-download";

describe("resolveDownloadFilename", () => {
  it("preferisce filename* (RFC 5987) e decodifica il percent-encoding UTF-8", () => {
    const header = "attachment; filename=\"Report.pdf\"; filename*=UTF-8''Report%20Budget%20-%20Acme%20%26%20C.pdf";
    expect(resolveDownloadFilename(header)).toBe("Report Budget - Acme & C.pdf");
  });

  it("usa filename ASCII quando non c'è filename*", () => {
    const header = 'attachment; filename="Report Budget.pdf"';
    expect(resolveDownloadFilename(header)).toBe("Report Budget.pdf");
  });

  it("ricade sul nome di default senza header", () => {
    expect(resolveDownloadFilename(null)).toBe("Report Budget.pdf");
    expect(resolveDownloadFilename(undefined)).toBe("Report Budget.pdf");
    expect(resolveDownloadFilename("")).toBe("Report Budget.pdf");
  });

  it("ricade sul nome di default con un header senza alcun token filename", () => {
    expect(resolveDownloadFilename("attachment")).toBe("Report Budget.pdf");
  });

  it("ricade sul token ASCII quando filename* ha una codifica percent non valida", () => {
    const header = "attachment; filename=\"Report.pdf\"; filename*=UTF-8''%E0%A4%A";
    expect(resolveDownloadFilename(header)).toBe("Report.pdf");
  });
});

describe("resolveDownloadErrorMessage", () => {
  it("usa il detail del server quando presente, per ogni stato", () => {
    for (const status of [404, 409, 422, 500, 503, 504]) {
      expect(resolveDownloadErrorMessage(status, "Messaggio specifico dal server")).toBe(
        "Messaggio specifico dal server"
      );
    }
  });

  it("ignora un detail vuoto o solo spazi e ricade sulla mappa per stato", () => {
    expect(resolveDownloadErrorMessage(409, "   ")).toMatch(/piano editoriale/);
    expect(resolveDownloadErrorMessage(409, "")).toMatch(/piano editoriale/);
    expect(resolveDownloadErrorMessage(409, null)).toMatch(/piano editoriale/);
    expect(resolveDownloadErrorMessage(409, undefined)).toMatch(/piano editoriale/);
  });

  it("mappa 422 al messaggio di impaginazione", () => {
    expect(resolveDownloadErrorMessage(422)).toMatch(/non si impagina/);
  });

  it("mappa 503 e 504 a messaggi distinti", () => {
    expect(resolveDownloadErrorMessage(503)).toMatch(/disponibile/);
    expect(resolveDownloadErrorMessage(504)).toMatch(/tempo/);
  });

  it("mappa 404 al messaggio di risorsa non trovata", () => {
    expect(resolveDownloadErrorMessage(404)).toMatch(/non trovat/);
  });

  it("ricade sul messaggio del 500 per uno stato non mappato", () => {
    expect(resolveDownloadErrorMessage(418)).toBe(resolveDownloadErrorMessage(500));
  });
});

describe("isRetryableDownloadStatus", () => {
  it("è vero solo per 503 e 504", () => {
    expect(isRetryableDownloadStatus(503)).toBe(true);
    expect(isRetryableDownloadStatus(504)).toBe(true);
    expect(isRetryableDownloadStatus(409)).toBe(false);
    expect(isRetryableDownloadStatus(422)).toBe(false);
    expect(isRetryableDownloadStatus(500)).toBe(false);
    expect(isRetryableDownloadStatus(404)).toBe(false);
  });
});

describe("FinalReportDownloadError", () => {
  it("porta lo stato HTTP e il messaggio già risolto", () => {
    const error = new FinalReportDownloadError(503, "Il servizio non è disponibile.");
    expect(error).toBeInstanceOf(Error);
    expect(error.status).toBe(503);
    expect(error.message).toBe("Il servizio non è disponibile.");
    expect(error.name).toBe("FinalReportDownloadError");
  });
});

describe("saveBlobAsFile", () => {
  it("crea l'URL, attiva il download e lo revoca, in quest'ordine", () => {
    const calls: string[] = [];
    const sink: FinalReportDownloadSink = {
      createObjectURL: vi.fn(() => {
        calls.push("create");
        return "blob:fake-url";
      }),
      triggerAnchorDownload: vi.fn((url, filename) => {
        expect(url).toBe("blob:fake-url");
        expect(filename).toBe("Report Budget.pdf");
        calls.push("trigger");
      }),
      revokeObjectURL: vi.fn((url) => {
        expect(url).toBe("blob:fake-url");
        calls.push("revoke");
      }),
    };
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });

    saveBlobAsFile(blob, "Report Budget.pdf", sink);

    expect(calls).toEqual(["create", "trigger", "revoke"]);
  });

  it("revoca l'URL anche se il trigger lancia", () => {
    const sink: FinalReportDownloadSink = {
      createObjectURL: vi.fn(() => "blob:fake-url"),
      triggerAnchorDownload: vi.fn(() => {
        throw new Error("boom");
      }),
      revokeObjectURL: vi.fn(),
    };
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });

    expect(() => saveBlobAsFile(blob, "Report Budget.pdf", sink)).toThrow("boom");
    expect(sink.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });
});

describe("withDownloadGuard", () => {
  it("lascia passare una sola richiesta quando due chiamate ravvicinate condividono il guard (doppio click)", async () => {
    const guard = createDownloadGuardState();
    let resolveTask: (value: string) => void = () => {};
    const task = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveTask = resolve;
        })
    );

    const first = withDownloadGuard(guard, task);
    // Il "secondo click" arriva mentre la prima richiesta è ancora in volo.
    const second = withDownloadGuard(guard, task);

    expect(task).toHaveBeenCalledTimes(1);

    resolveTask("fatto");
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(firstResult).toBe("fatto");
    expect(secondResult).toBeNull();
    expect(task).toHaveBeenCalledTimes(1);
  });

  it("libera il guard anche se il task lancia, e una chiamata successiva riparte", async () => {
    const guard = createDownloadGuardState();
    const failing = vi.fn(async () => {
      throw new Error("errore di rete");
    });

    await expect(withDownloadGuard(guard, failing)).rejects.toThrow("errore di rete");
    expect(guard.pending).toBe(false);

    const succeeding = vi.fn(async () => "ok");
    await expect(withDownloadGuard(guard, succeeding)).resolves.toBe("ok");
    expect(succeeding).toHaveBeenCalledTimes(1);
  });

  it("permette due chiamate in sequenza (non contemporanee) sullo stesso guard", async () => {
    const guard = createDownloadGuardState();
    const task = vi.fn(async () => "risultato");

    await withDownloadGuard(guard, task);
    await withDownloadGuard(guard, task);

    expect(task).toHaveBeenCalledTimes(2);
  });
});
