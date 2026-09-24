import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `api.ts` costruisce l'istanza axios al load del modulo (`axios.create`):
// il finto deve rispondere PRIMA dell'import, altrimenti `api.ts` esplode
// su `api.interceptors.request.use is not a function`.
const postMock = vi.fn();
const getMock = vi.fn();
const putMock = vi.fn();
vi.mock("axios", () => {
  const instance = {
    post: (...args: unknown[]) => postMock(...args),
    get: (...args: unknown[]) => getMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => instance),
      isCancel: vi.fn(() => false),
    },
  };
});

import { downloadFinalReportPdf, downloadInfrannualePdf, downloadReportDocx, generateEditorialNotes, getEditorialSession, getFinalReport, getFinalReportV2, prepareEditorialSession, previewForecast, saveEditorialNotes, setAuthToken } from "./api";
import { FinalReportDownloadError } from "./final-report-download";
import v1 from "../../tests/fixtures/final_report/bilancio.json";
import v2 from "../../tests/fixtures/final_report/v2/bilancio.json";

const editorialSession = { report: v2, revision: 3, archived_notes: [], generation_warnings: [] };

describe("previewForecast", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it("posta le ipotesi sull'endpoint di anteprima con lo stesso corpo del bulk, e inoltra il signal", async () => {
    const response = { scenario_id: 1, base_year: 2024, forecast_years: [], error: null };
    postMock.mockResolvedValue({ data: response });
    const controller = new AbortController();
    const rows = [{ forecast_year: 2025, revenue_growth_pct: 5 }];

    const result = await previewForecast(1, 2, rows, controller.signal);

    expect(result).toEqual(response);
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock).toHaveBeenCalledWith(
      "/companies/1/scenarios/2/preview",
      { assumptions: rows },
      { signal: controller.signal }
    );
  });

  it("funziona anche senza signal (nessuna annullabilita' richiesta dal chiamante)", async () => {
    const response = { scenario_id: 7, base_year: 2023, forecast_years: [], error: null };
    postMock.mockResolvedValue({ data: response });

    const result = await previewForecast(7, 9, []);

    expect(result).toEqual(response);
    expect(postMock).toHaveBeenCalledWith(
      "/companies/7/scenarios/9/preview",
      { assumptions: [] },
      { signal: undefined }
    );
  });
});

describe("versioned final report getters", () => {
  beforeEach(() => getMock.mockReset());
  it("requests v2 explicitly through the authenticated API instance", async () => {
    getMock.mockResolvedValue({data: v2});
    expect(await getFinalReportV2(1, 2)).toEqual(v2);
    expect(getMock).toHaveBeenCalledWith("/companies/1/scenarios/2/final-report", {params: {schema_version: 2}});
  });
  it("retains the v1 getter and rejects a response with the wrong version", async () => {
    getMock.mockResolvedValue({data: v1});
    expect(await getFinalReport(1, 2)).toEqual(v1);
    expect(getMock).toHaveBeenCalledWith("/companies/1/scenarios/2/final-report");
    await expect(getFinalReportV2(1, 2)).rejects.toThrow(/v2/);
  });
});

describe("editorial session API", () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset(); putMock.mockReset(); });
  it("uses the dedicated session boundary and sends only hashes, revisions and note IDs", async () => {
    getMock.mockResolvedValue({ data: editorialSession });
    postMock.mockResolvedValue({ data: editorialSession });
    putMock.mockResolvedValue({ data: editorialSession });
    expect(await getEditorialSession(1, 2)).toEqual(editorialSession);
    await prepareEditorialSession(1, 2);
    await saveEditorialNotes(1, 2, { source_hash: v2.source_hash, plan_hash: "a".repeat(64), expected_revision: 3, notes: [{ id: "page-1", text: "Testo", revision: 2, from_note: { id: "old", plan_hash: "b".repeat(64), revision: 1 } }] });
    await generateEditorialNotes(1, 2, { source_hash: v2.source_hash, plan_hash: "a".repeat(64), expected_revision: 3, notes: [{ id: "page-1", revision: 2 }] });
    expect(getMock).toHaveBeenCalledWith("/companies/1/scenarios/2/final-report/editorial");
    expect(postMock).toHaveBeenNthCalledWith(1, "/companies/1/scenarios/2/final-report/editorial/prepare", { source_hash: v2.source_hash, expected_revision: 3 });
    expect(putMock).toHaveBeenCalledWith("/companies/1/scenarios/2/final-report/editorial/notes", expect.objectContaining({ expected_revision: 3, notes: [{ id: "page-1", text: "Testo", revision: 2, from_note: { id: "old", plan_hash: "b".repeat(64), revision: 1 } }] }));
    expect(postMock).toHaveBeenNthCalledWith(2, "/companies/1/scenarios/2/final-report/editorial/generate", expect.objectContaining({ notes: [{ id: "page-1", revision: 2 }] }));
  });

  it("prepares with the current source and revision after narrative generation, not the cached session", async () => {
    getMock.mockResolvedValueOnce({ data: editorialSession });
    const cached = await getEditorialSession(575, 18);
    const current = { ...editorialSession, revision: 7, report: { ...v2, source_hash: "c".repeat(64) } };
    getMock.mockResolvedValueOnce({ data: current });
    postMock.mockResolvedValueOnce({ data: { ...current, revision: 8 } });

    const prepared = await prepareEditorialSession(575, 18);

    expect(cached.revision).toBe(3);
    expect(prepared.revision).toBe(8);
    expect(getMock).toHaveBeenNthCalledWith(2, "/companies/575/scenarios/18/final-report/editorial");
    expect(postMock).toHaveBeenCalledWith("/companies/575/scenarios/18/final-report/editorial/prepare", {
      source_hash: current.report.source_hash, expected_revision: 7,
    });
    expect(getMock.mock.invocationCallOrder[1]).toBeLessThan(postMock.mock.invocationCallOrder[0]);
  });

  it("does not prepare with stale data when refreshing the session fails", async () => {
    const error = new Error("Sessione non disponibile");
    getMock.mockRejectedValueOnce(error);
    await expect(prepareEditorialSession(575, 18)).rejects.toBe(error);
    expect(postMock).not.toHaveBeenCalled();
  });

  it("preserves a conflict that occurs after the fresh read without retrying writes", async () => {
    const conflict = { response: { status: 409 } };
    getMock.mockResolvedValueOnce({ data: editorialSession });
    postMock.mockRejectedValueOnce(conflict);
    await expect(prepareEditorialSession(575, 18)).rejects.toBe(conflict);
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(postMock).toHaveBeenCalledTimes(1);
  });
});

describe("downloadFinalReportPdf", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setAuthToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setAuthToken(null);
  });

  it("con model business_plan chiama la rotta del Business plan e manda solo document_state", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: { get: () => null }, blob: async () => blob, json: async () => ({}) });
    await downloadFinalReportPdf(1, 2, { documentState: "draft", model: "business_plan" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/companies/1/scenarios/2/business-plan/pdf");
    expect(JSON.parse(init.body)).toEqual({ document_state: "draft" });
  });

  it("posta document_state e grayscale, con Bearer quando il token è impostato, e legge blob e nome file dagli header", async () => {
    setAuthToken("un-jwt");
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: (name: string) => (name === "Content-Disposition" ? "attachment; filename=\"Report.pdf\"; filename*=UTF-8''Report%20Budget.pdf" : null) },
      blob: async () => blob,
      json: async () => ({}),
    });

    const result = await downloadFinalReportPdf(1, 2, { documentState: "final", grayscale: true });

    expect(result.blob).toBe(blob);
    expect(result.filename).toBe("Report Budget.pdf");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/companies/1/scenarios/2/final-report/pdf");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer un-jwt");
    expect(JSON.parse(init.body)).toEqual({ document_state: "final", grayscale: true });
  });

  it("non manda Authorization senza token impostato, e grayscale di default è false", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      blob: async () => blob,
      json: async () => ({}),
    });

    const result = await downloadFinalReportPdf(1, 2, { documentState: "draft" });

    expect(result.filename).toBe("Report Budget.pdf");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
    expect(JSON.parse(init.body)).toEqual({ document_state: "draft", grayscale: false });
  });

  it("lancia FinalReportDownloadError col detail del server su un errore JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      headers: { get: () => null },
      json: async () => ({ detail: "Prepara il piano editoriale prima di scaricare il PDF." }),
    });

    await expect(downloadFinalReportPdf(1, 2, { documentState: "final" })).rejects.toMatchObject({
      status: 409,
      message: "Prepara il piano editoriale prima di scaricare il PDF.",
    });
  });

  it("ricade sul messaggio per stato quando il corpo dell'errore non è JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      headers: { get: () => null },
      json: async () => {
        throw new Error("non è JSON");
      },
    });

    const error = await downloadFinalReportPdf(1, 2, { documentState: "draft" }).catch((e) => e);

    expect(error).toBeInstanceOf(FinalReportDownloadError);
    expect(error.status).toBe(503);
    expect(error.message).toMatch(/disponibile/);
  });
});

describe("downloadInfrannualePdf", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setAuthToken(null);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("chiama la rotta del report infrannuale con corpo vuoto e legge il nome file", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetchMock.mockResolvedValue({
      ok: true, status: 200, blob: async () => blob, json: async () => ({}),
      headers: { get: (n: string) => (n === "Content-Disposition" ? "attachment; filename=\"Report.pdf\"; filename*=UTF-8''Report%20infrannuale%20X%206M%202026.pdf" : null) },
    });
    const result = await downloadInfrannualePdf(1, 2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/companies/1/scenarios/2/infrannuale/pdf");
    expect(JSON.parse(init.body)).toEqual({});
    expect(result.filename).toBe("Report infrannuale X 6M 2026.pdf");
  });
});

describe("downloadReportDocx", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setAuthToken(null);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("chiama la rotta Word giusta col corpo della rotta PDF", async () => {
    const blob = new Blob(["PK"]);
    fetchMock.mockResolvedValue({
      ok: true, status: 200, blob: async () => blob, json: async () => ({}),
      headers: { get: (n: string) => (n === "Content-Disposition" ? 'attachment; filename="Report.docx"' : null) },
    });
    const result = await downloadReportDocx(1, 2, "infrannuale");
    expect(fetchMock.mock.calls[0][0]).toContain("/companies/1/scenarios/2/infrannuale/docx");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
    expect(result.filename).toBe("Report.docx");
    await downloadReportDocx(1, 3, "business-plan", "final");
    expect(fetchMock.mock.calls[1][0]).toContain("/companies/1/scenarios/3/business-plan/docx");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ document_state: "final" });
  });

  it("un errore del server diventa FinalReportDownloadError", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "non trovato" }), headers: { get: () => null } });
    const error = await downloadReportDocx(1, 2, "infrannuale").catch((e) => e);
    expect(error.status).toBe(404);
  });
});
