import { describe, expect, it, vi } from "vitest";
import {
  FinalReportDownloadError,
  REPORT_MODELS,
  reportPdfPath,
  PREVIEW_BLOCKED_MESSAGE,
  PREVIEW_REVOKE_DELAY_MS,
  closePreviewTabOnError,
  createDownloadGuardState,
  isRetryableDownloadStatus,
  resolveDownloadErrorMessage,
  resolveDownloadFilename,
  saveBlobAsFile,
  showPdfPreview,
  withDownloadGuard,
  type FinalReportDownloadSink,
  type FinalReportPreviewSink,
  type FinalReportPreviewTab,
  nextInlinePreviewUrl,
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

  it("download e anteprima condividono lo stesso guard: non partono insieme", async () => {
    const guard = createDownloadGuardState();
    let resolveDownload: (value: string) => void = () => {};
    const downloadTask = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveDownload = resolve;
        })
    );
    const previewTask = vi.fn(async () => "anteprima");

    const download = withDownloadGuard(guard, downloadTask);
    // Click su "Anteprima PDF" mentre il download è ancora in volo.
    const preview = withDownloadGuard(guard, previewTask);

    expect(previewTask).not.toHaveBeenCalled();

    resolveDownload("scaricato");
    const [downloadResult, previewResult] = await Promise.all([download, preview]);

    expect(downloadResult).toBe("scaricato");
    expect(previewResult).toBeNull();
  });
});

function createPreviewSink(): FinalReportPreviewSink & {
  calls: string[];
  revokeCallbacks: Array<() => void>;
} {
  const calls: string[] = [];
  const revokeCallbacks: Array<() => void> = [];
  return {
    calls,
    revokeCallbacks,
    createObjectURL: vi.fn(() => {
      calls.push("create");
      return "blob:preview-url";
    }),
    revokeObjectURL: vi.fn((url) => {
      expect(url).toBe("blob:preview-url");
      calls.push("revoke");
    }),
    triggerAnchorDownload: vi.fn((url, filename) => {
      expect(url).toBe("blob:preview-url");
      expect(filename).toBe("Report Budget.pdf");
      calls.push("trigger-download");
    }),
    scheduleRevoke: vi.fn((callback, delayMs) => {
      expect(delayMs).toBe(PREVIEW_REVOKE_DELAY_MS);
      calls.push("schedule-revoke");
      revokeCallbacks.push(callback);
    }),
  };
}

function createPreviewTab(): FinalReportPreviewTab & { navigatedTo: string[]; closed: boolean } {
  const navigatedTo: string[] = [];
  return {
    navigatedTo,
    closed: false,
    navigate(url: string) {
      navigatedTo.push(url);
    },
    close() {
      this.closed = true;
    },
  };
}

describe("showPdfPreview", () => {
  it("naviga la scheda preaperta sull'object URL e pianifica la revoca ritardata, senza revocare subito", () => {
    const sink = createPreviewSink();
    const tab = createPreviewTab();
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });

    const outcome = showPdfPreview(tab, blob, "Report Budget.pdf", sink);

    expect(outcome).toEqual({ opened: true });
    expect(tab.navigatedTo).toEqual(["blob:preview-url"]);
    expect(sink.calls).toEqual(["create", "schedule-revoke"]);
    expect(sink.revokeObjectURL).not.toHaveBeenCalled();

    // Solo quando il timer iniettato scatta la revoca avviene davvero.
    sink.revokeCallbacks[0]();
    expect(sink.calls).toEqual(["create", "schedule-revoke", "revoke"]);
  });

  it("ripiega sul download quando la scheda è null (popup bloccato)", () => {
    const sink = createPreviewSink();
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });

    const outcome = showPdfPreview(null, blob, "Report Budget.pdf", sink);

    expect(outcome).toEqual({ opened: false, fallbackToDownload: true });
    expect(sink.calls).toEqual(["create", "trigger-download", "revoke"]);
  });

  it("accetta un ritardo di revoca esplicito, per i test dell'hook", () => {
    const sink = createPreviewSink();
    sink.scheduleRevoke = vi.fn((callback, delayMs) => {
      expect(delayMs).toBe(5000);
      callback();
    });
    const tab = createPreviewTab();
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });

    showPdfPreview(tab, blob, "Report Budget.pdf", sink, 5000);

    expect(sink.revokeObjectURL).toHaveBeenCalledWith("blob:preview-url");
  });
});

describe("closePreviewTabOnError", () => {
  it("chiude la scheda preaperta quando esiste", () => {
    const tab = createPreviewTab();
    closePreviewTabOnError(tab);
    expect(tab.closed).toBe(true);
  });

  it("non lancia quando la scheda è null (popup già bloccato)", () => {
    expect(() => closePreviewTabOnError(null)).not.toThrow();
  });
});

describe("PREVIEW_BLOCKED_MESSAGE", () => {
  it("è un messaggio informativo non vuoto", () => {
    expect(PREVIEW_BLOCKED_MESSAGE.length).toBeGreaterThan(0);
  });
});

describe("nextInlinePreviewUrl", () => {
  const sink = () => {
    const revoked: string[] = [];
    const created: Blob[] = [];
    return {
      revoked,
      created,
      sink: {
        createObjectURL: (blob: Blob) => {
          created.push(blob);
          return `blob:nuovo-${created.length}`;
        },
        revokeObjectURL: (url: string) => {
          revoked.push(url);
        },
        triggerAnchorDownload: () => {},
      },
    };
  };

  it("revoca l'URL precedente prima di crearne uno nuovo: un PDF per volta in memoria", () => {
    const { revoked, sink: downloadSink } = sink();
    const url = nextInlinePreviewUrl("blob:vecchio", new Blob(["%PDF"]), downloadSink);
    expect(revoked).toEqual(["blob:vecchio"]);
    expect(url).toBe("blob:nuovo-1");
  });

  it("senza blob chiude l'anteprima: revoca e restituisce null", () => {
    const { revoked, created, sink: downloadSink } = sink();
    expect(nextInlinePreviewUrl("blob:vecchio", null, downloadSink)).toBeNull();
    expect(revoked).toEqual(["blob:vecchio"]);
    expect(created).toEqual([]);
  });

  it("una revoca che fallisce non impedisce la nuova anteprima", () => {
    const { created } = sink();
    const url = nextInlinePreviewUrl("blob:vecchio", new Blob(["%PDF"]), {
      createObjectURL: () => "blob:nuovo",
      revokeObjectURL: () => {
        throw new Error("già revocato");
      },
      triggerAnchorDownload: () => {},
    });
    expect(url).toBe("blob:nuovo");
    expect(created).toEqual([]);
  });

  it("senza URL precedente non revoca nulla", () => {
    const { revoked, sink: downloadSink } = sink();
    expect(nextInlinePreviewUrl(null, new Blob(["%PDF"]), downloadSink)).toBe("blob:nuovo-1");
    expect(revoked).toEqual([]);
  });
});

describe("modelli di report", () => {
  it("il Business plan è il primo, ed è il default", () => {
    expect(REPORT_MODELS.map((m) => m.value)).toEqual(["business_plan", "dossier"]);
  });
  it("ogni modello ha la sua rotta", () => {
    expect(reportPdfPath("dossier")).toBe("final-report/pdf");
    expect(reportPdfPath("business_plan")).toBe("business-plan/pdf");
  });
});
