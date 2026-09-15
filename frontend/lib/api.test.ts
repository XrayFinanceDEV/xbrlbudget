import { beforeEach, describe, expect, it, vi } from "vitest";

// `api.ts` costruisce l'istanza axios al load del modulo (`axios.create`):
// il finto deve rispondere PRIMA dell'import, altrimenti `api.ts` esplode
// su `api.interceptors.request.use is not a function`.
const postMock = vi.fn();
const getMock = vi.fn();
vi.mock("axios", () => {
  const instance = {
    post: (...args: unknown[]) => postMock(...args),
    get: (...args: unknown[]) => getMock(...args),
    put: vi.fn(),
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

import { getFinalReport, getFinalReportV2, previewForecast } from "./api";
import v1 from "../../tests/fixtures/final_report/bilancio.json";
import v2 from "../../tests/fixtures/final_report/v2/bilancio.json";

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
