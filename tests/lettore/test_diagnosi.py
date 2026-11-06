"""Task 3 (Fase 2): la diagnosi di un import. Non solleva mai, ha un tetto di tempo, esce in JSON."""
import json
import time

import fitz
import pytest

from importers.lettore import diagnosi as mod
from importers.lettore import leggi_pdf as _leggi_pdf
from importers.lettore.diagnosi import diagnosi_pdf, frasi_per_utente
from tests.lettore.pdf_sintetico import scrivi_pdf
from tests.lettore.test_blocchi import _APERTURA, _righe


@pytest.fixture
def come_schema(monkeypatch):
    """Il PDF sintetico e' «ignoto»: si forza lo schema, come fa test_blocchi."""
    def leggi(path):
        doc = _leggi_pdf(path)
        doc.profilo.tipo = "schema"
        return doc
    monkeypatch.setattr(mod, "leggi_pdf", leggi)


def _pdf(tmp_path, righe, nome="d.pdf"):
    p = tmp_path / nome
    scrivi_pdf(p, [_righe(140, _APERTURA + righe)])
    return str(p)


_CHIUDE = [("Conto uno", "100,00", "90,00"), ("Conto due", "250,00", "80,00"),
           ("Conto tre", "300,00", "70,00"), ("Totale", "650,00", "240,00")]
_APERTO = [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Conto tre", "250,00"), ("Totale", "610,00")]


def test_diagnosi_documento_che_chiude(tmp_path, come_schema):
    p = tmp_path / "c.pdf"
    scrivi_pdf(p, [_righe(140, _CHIUDE)])
    d = diagnosi_pdf(str(p))
    assert d["esito"] == "ok" and d["blocchi_aperti"] == []
    assert "blocchi_aperti" in d and d["ingresso"] == "pdf"


def test_diagnosi_blocco_aperto(tmp_path, come_schema):
    d = diagnosi_pdf(_pdf(tmp_path, _APERTO))
    assert d["esito"] == "ok" and len(d["blocchi_aperti"]) == 1
    assert d["blocchi_aperti"][0]["scarto"] == "10.00"
    assert d["blocchi_aperti"][0]["cercato"] is True


def test_diagnosi_non_solleva(tmp_path):
    d = diagnosi_pdf(str(tmp_path / "non_esiste.pdf"))
    assert d["esito"] == "errore" and d["motivo"]


def test_diagnosi_tetto_di_tempo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "leggi_pdf", lambda p: time.sleep(2))
    t = time.monotonic()
    d = diagnosi_pdf(str(tmp_path / "x.pdf"), tetto_secondi=0.5)
    assert d["esito"] == "tempo" and time.monotonic() - t < 1.5


class _T:
    def __init__(self, html, page):
        self.html, self.page, self.caption = html, page, None


class _Ctx:
    def __init__(self, tables):
        self.tables = tuple(tables)


def _tabella(*righe):
    return "<table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in righe) + "</table>"


def test_diagnosi_mineru(tmp_path):
    t1 = _tabella(["", "31/12/2024", "31/12/2023"], ["Crediti verso clienti", "1.200,00", "1.000,00"],
                  ["Altri crediti", "300,00", "400,00"])
    t2 = _tabella(["Debiti verso fornitori", "700,00", "650,00"], ["Debiti tributari", "", "30,00"])
    d = diagnosi_pdf(str(tmp_path / "x.pdf"), _Ctx([_T(t1, 0), _T(t2, 1)]))  # page_idx di MinerU: da 0
    assert d["ingresso"] == "mineru" and d["esito"] == "ok"


def test_diagnosi_scansione_senza_tabelle(tmp_path):
    p = tmp_path / "s.pdf"
    doc = fitz.open()
    pag = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    pag.insert_image(fitz.Rect(50, 50, 300, 300), pixmap=pix)
    doc.save(str(p))
    assert diagnosi_pdf(str(p))["esito"] == "non_applicabile"


def _b(corrente, sezione="SP", scarto="10.00", cercato=False, voce="Voce", fine="2025-12-31"):
    return {"voce": voce, "codice": "", "sezione": sezione, "lato": "U", "colonna": 0, "fine": fine, "mesi": 12,
            "corrente": corrente, "stampato": "110.00", "somma": str(110 - float(scarto)), "scarto": scarto,
            "pagina": 1, "righe": ["p1r1U", "p1r4U"], "etichette": [], "cercato": cercato}


def test_frasi_solo_colonna_corrente():
    dg = {"blocchi_aperti": [_b(False, voce="Vecchio", fine="2024-12-31"), _b(True, voce="Nuovo")]}
    frasi = frasi_per_utente(dg, {"SP"})
    assert len(frasi) == 2 and frasi[0].startswith("BLOCCHI CHE NON CHIUDONO NEL PDF") and "Nuovo" in frasi[1]
    assert len(frasi_per_utente(dg, {"SP"}, anno_precedente=2024)) == 3
    assert frasi_per_utente(dg, {"CE"}) == []


def test_frasi_vuote_senza_blocchi():
    assert frasi_per_utente({"blocchi_aperti": []}, {"SP", "CE"}) == []


def test_frasi_blocco_cercato_da_verificare():
    dg = {"blocchi_aperti": [_b(True, scarto="500.00", cercato=True, voce="Cercato"),
                             _b(True, scarto="5.00", voce="Noto"),
                             *[_b(True, scarto=f"{i}.00", voce=f"N{i}") for i in range(10, 17)]]}
    frasi = frasi_per_utente(dg, {"SP"})
    assert len(frasi) == 6                      # intestazione + 5 blocchi
    assert frasi[1].startswith("N16") and not frasi[1].endswith("da verificare)")
    assert all("da verificare" not in f for f in frasi[1:])      # il cercato e' fuori dai primi 5
    dg2 = {"blocchi_aperti": [_b(True, scarto="500.00", cercato=True, voce="Cercato"), _b(True, voce="Noto")]}
    f2 = frasi_per_utente(dg2, {"SP"})
    assert f2[1].startswith("Noto")
    assert f2[2].startswith("Cercato") and f2[2].endswith(" (righe individuate dal lettore: da verificare)")
    assert not f2[1].endswith("da verificare)")


def test_json_serializzabile(tmp_path, come_schema):
    json.dumps(diagnosi_pdf(_pdf(tmp_path, _APERTO)))
    json.dumps(diagnosi_pdf(str(tmp_path / "no.pdf")))


def _blocco(anno, k=0):
    from datetime import date
    from decimal import Decimal
    from importers.lettore import Blocco
    return Blocco(voce=f"V{k}", codice="", sezione="SP", lato="U", colonna=0, fine=date(anno, 12, 31), mesi=12,
                  corrente=True, stampato=Decimal(100 + k), somma=Decimal(100), scarto=Decimal(k), pagina=1,
                  righe=("p1r1U", "p1r2U"), etichette=(), cercato=False)


def _doc_finto(monkeypatch, blocchi):
    class _P:
        tipo, avvisi = "schema", []

    class _D:
        righe, colonne, contrapposto, profilo = [object()], [], False, _P()

        def tutti_gli_avvisi(self):
            return []
    monkeypatch.setattr(mod, "leggi_pdf", lambda p: _D())
    monkeypatch.setattr(mod, "blocchi_aperti", lambda d: blocchi)


def test_tetto_di_venti_blocchi(monkeypatch):
    _doc_finto(monkeypatch, [_blocco(2025, k) for k in range(25)])
    assert len(diagnosi_pdf("x.pdf")["blocchi_aperti"]) == 20


def test_filtro_per_anno(monkeypatch):
    _doc_finto(monkeypatch, [_blocco(2025), _blocco(2024), _blocco(2020)])
    d = diagnosi_pdf("x.pdf", anno_corrente=2025, anno_precedente=2024)
    assert sorted(b["fine"][:4] for b in d["blocchi_aperti"]) == ["2024", "2025"]
    assert len(diagnosi_pdf("x.pdf")["blocchi_aperti"]) == 3


def test_tetto_env_non_numerico(monkeypatch):
    monkeypatch.setenv("LETTORE_TETTO_SECONDI", "abc")
    assert mod._tetto(None) == mod.TETTO_SECONDI_DEFAULT


def test_contesto_che_solleva(tmp_path):
    class _Cattivo:
        @property
        def tables(self):
            raise RuntimeError("rotto")
    d = diagnosi_pdf(str(tmp_path / "x.pdf"), _Cattivo())
    assert d["esito"] == "errore" and d["motivo"]


def test_frasi_diagnosi_malformata():
    assert frasi_per_utente({}, {"SP"}) == []
    assert frasi_per_utente({"esito": "errore"}, {"SP"}) == []
    assert frasi_per_utente({"blocchi_aperti": [{"sezione": "SP", "corrente": True}]}, {"SP"}) == []
    assert frasi_per_utente(None, {"SP"}) == []


def test_frasi_esito_non_ok():
    assert frasi_per_utente({"esito": "tempo", "blocchi_aperti": [_b(True)]}, {"SP"}) == []
