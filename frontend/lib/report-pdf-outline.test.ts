import { describe, expect, it } from "vitest";
import { buildPdfOutline, pdfPageLabel, pdfPageUrl } from "./report-pdf-outline";

describe("buildPdfOutline", () => {
  it("numera le pagine dalla posizione nel piano: una pagina fisica per voce", () => {
    const outline = buildPdfOutline([{ section_id: "cover" }, { section_id: "sintesi" }, { section_id: "ce" }]);
    expect(outline).toEqual([
      { page: 1, label: "Copertina", sectionId: "cover" },
      { page: 2, label: "Sintesi esecutiva", sectionId: "sintesi" },
      { page: 3, label: "Conto economico previsionale", sectionId: "ce" },
    ]);
  });

  it("nomina le parti di un allegato dalla lettera", () => {
    expect(pdfPageLabel("allegato-A-2")).toBe("A · Conto economico completo (2)");
    expect(pdfPageLabel("allegato-D")).toBe("D · Registro delle rettifiche");
  });

  it("un id sconosciuto resta nell'indice com'è: meglio un nome tecnico di un buco", () => {
    expect(pdfPageLabel("pagina-nuova")).toBe("pagina-nuova");
    expect(buildPdfOutline([{ section_id: "pagina-nuova" }])).toEqual([
      { page: 1, label: "pagina-nuova", sectionId: "pagina-nuova" },
    ]);
  });

  it("un piano vuoto non produce indice", () => {
    expect(buildPdfOutline([])).toEqual([]);
  });
});

describe("pdfPageUrl", () => {
  it("apre il visualizzatore sulla pagina chiesta, a tutta larghezza", () => {
    expect(pdfPageUrl("blob:abc", 7)).toBe("blob:abc#page=7&zoom=page-width");
  });

  it("sostituisce un frammento già presente invece di accodarne un altro", () => {
    expect(pdfPageUrl("blob:abc#page=3&zoom=page-width", 9)).toBe("blob:abc#page=9&zoom=page-width");
  });

  it("non esiste una pagina zero o negativa", () => {
    expect(pdfPageUrl("blob:abc", 0)).toBe("blob:abc#page=1&zoom=page-width");
    expect(pdfPageUrl("blob:abc", -4)).toBe("blob:abc#page=1&zoom=page-width");
  });
});
