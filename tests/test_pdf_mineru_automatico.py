"""POST /import/pdf manda in automatico le scansioni a MinerU (decisione del proprietario,
2026-10-14). MinerU finto: nessun servizio vero, nessun OCR."""
import fitz
import pytest

from tests.test_pdf_ocr_endpoint import _auth, _fake_client_cls, ctx  # noqa: F401 - fixture

URL = "/api/v1/import/pdf?fiscal_year=2026&company_name=Acme&create_company=true"


def _pdf(con_testo: bool) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    if con_testo:
        page.insert_text((40, 60), "Bilancio di verifica al 31/08/2026 - Totale attivo 1.000,00")
    else:
        page.draw_rect(fitz.Rect(40, 40, 200, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def chiamate(ctx):  # noqa: F811
    client, settings, imports_router, mc, mp = ctx
    viste = []

    def finto_import(**kwargs):
        viste.append(kwargs)
        return {"success": True, "company_id": 1, "warnings": []}

    mp.setattr(imports_router, "import_pdf_balance_sheet", finto_import)
    return client, settings, mc, mp, viste


def _carica(client, contenuto):
    return client.post(URL, files={"file": ("b.pdf", contenuto, "application/pdf")},
                       headers=_auth("u1"))


def test_una_scansione_passa_da_mineru(chiamate):
    client, settings, mc, mp, viste = chiamate
    mp.setattr(mc, "MinerUClient", _fake_client_cls(md="Stato Patrimoniale Totale attivo 100"))
    r = _carica(client, _pdf(con_testo=False))
    assert r.status_code == 200, r.text
    contesto = viste[0]["extraction_context"]
    assert contesto is not None and "Totale attivo" in contesto.full_text
    assert r.json()["warnings"] == []


def test_un_pdf_con_testo_non_passa_da_mineru(chiamate):
    client, settings, mc, mp, viste = chiamate

    class _Vietato:
        @classmethod
        def from_settings(cls, *a, **k):
            raise AssertionError("MinerU chiamato su un PDF con testo")

    mp.setattr(mc, "MinerUClient", _Vietato)
    assert _carica(client, _pdf(con_testo=True)).status_code == 200
    assert viste[0]["extraction_context"] is None


def test_mineru_spento_non_si_chiama(chiamate):
    client, settings, mc, mp, viste = chiamate
    mp.setattr(settings, "MINERU_OCR_ENABLED", False)
    r = _carica(client, _pdf(con_testo=False))
    assert r.status_code == 200
    assert viste[0]["extraction_context"] is None
    assert r.json()["warnings"] == []


def test_mineru_che_non_risponde_ripiega_e_lo_dichiara(chiamate):
    client, settings, mc, mp, viste = chiamate
    mp.setattr(mc, "MinerUClient", _fake_client_cls(health_exc=mc.MinerUUnavailableError("giu'")))
    r = _carica(client, _pdf(con_testo=False))
    assert r.status_code == 200
    assert viste[0]["extraction_context"] is None
    assert r.json()["warnings"][0].startswith("OCR MINERU NON DISPONIBILE")


def _scansione_con_ocr(fonts: int) -> bytes:
    """Un'immagine a pagina intera con sopra un testo: il livello OCR di uno scanner
    (NAPS2, Unicarton 31/08/2026) ha un font solo; un PDF nativo con sfondo ne ha di
    piu'."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 80), False)
    pix.clear_with(200)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pix)
    nomi = ["helv", "tiro", "cour"][:fonts]
    for i, nome in enumerate(nomi):
        page.insert_text((40, 60 + 20 * i), "Stato patrimoniale Totale attivita' 5.888.998,46 Erario c/IVA",
                         fontname=nome)
    data = doc.tobytes()
    doc.close()
    return data


def test_una_scansione_con_testo_ocr_passa_da_mineru(chiamate):
    client, settings, mc, mp, viste = chiamate
    mp.setattr(mc, "MinerUClient", _fake_client_cls(md="Stato Patrimoniale Totale attivo 100"))
    r = _carica(client, _scansione_con_ocr(fonts=1))
    assert r.status_code == 200, r.text
    assert viste[0]["extraction_context"] is not None


def test_uno_sfondo_con_i_font_del_gestionale_resta_un_pdf_di_testo():
    from app.api.v1.imports import _e_una_scansione
    assert _e_una_scansione(_scansione_con_ocr(fonts=1))
    assert not _e_una_scansione(_scansione_con_ocr(fonts=3))
    assert not _e_una_scansione(_pdf(con_testo=True))
