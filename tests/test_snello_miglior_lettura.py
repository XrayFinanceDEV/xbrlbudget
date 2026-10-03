"""Task 28: quando il modello non quadra, si salva la lettura piu' vicina, non l'ultima.

Il candidato deterministico respinto solo per il limite del tappo (``oltre_soglia``) tiene la sua
lettura; se il percorso del modello finisce squadrato peggio (o ripiega), si salva quella. Il
modello e' sempre finto: nessuna chiamata di rete."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from importers import import_snello as S
from tests.test_snello_deterministico import _TESTO_BILANCIO_DI_VERIFICA, _pdf_situazione_contabile
from tests.test_snello_importa import _struttura


def _det_949(monkeypatch, *, bs=None, ce=None):
    """Il caso budget_949: SP quadrato, utile CE diverso da sp13 di 745,89 euro."""
    bs = bs if bs is not None else {"sp09": D("100000.00"), "sp11": D("52000.00"), "sp13": D("48000.00")}
    ce = ce if ce is not None else {"ce01": D("100000.00"), "ce06": D("51254.11")}

    def _fake(file_path, return_prior=False, text_override=None):
        return dict(bs), dict(ce), None, None

    monkeypatch.setattr("importers.situazione_contabile_parser.extract_situazione_contabile", _fake)


def _modello(passivo_capitale: str, utile_ce_voce="100000"):
    """Una lettura del modello: attivo 100.000, passivo = ``passivo_capitale``, CE a utile zero
    (CE.A.1 = CE.B.7) salvo ``utile_ce_voce``."""
    def voci(testo, intestazioni, nota=""):
        return {"corrente": [("SPA.C.IV.1", D("100000")), ("SPP.A.I", D(passivo_capitale)),
                             ("CE.A.1", D("100000")), ("CE.B.7", D(utile_ce_voce))],
                "precedente": [], "totali": {}}
    return voci


def _importa(tmp_path, leggi_voci):
    pdf = str(tmp_path / "v.pdf")
    _pdf_situazione_contabile(pdf)
    return S.importa(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA,
                     analizza=lambda p, route_hint=None: _struttura("legge"), leggi_voci=leggi_voci)


def test_modello_squadrato_peggio_vince_la_lettura_deterministica(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    r = _importa(tmp_path, _modello("2700.60"))          # scarto SP 97.299,40
    assert r.report["esito"] == "squadrato"
    assert r.report["fonte"] == "deterministico:situazione_contabile_parser"
    assert r.report["misura"]["corrente"]["scarto_sp"] == "0.00"
    assert r.report["misura"]["corrente"]["scarto_ce"] == "745.89"
    assert r.report["tappo"]["corrente"] is None
    assert r.bs["_plug_residual"] == D("0")
    assert r.ce["ce06_servizi"] == D("51254.11")            # nessun tappo sul CE
    c = r.report["confronto_letture"]
    assert (c["deterministica"], c["modello"], c["vince"]) == ("745.89", "97299.40", "deterministica")
    assert r.report["letture"] and sum(r.report["letture"].values()) >= 2   # le letture fatte restano


def test_avviso_costruito_dalla_lettura_salvata(tmp_path, monkeypatch):
    from importers.pdf_importer import _snello_squadrato_reason
    _det_949(monkeypatch)
    r = _importa(tmp_path, _modello("2700.60"))
    testo = _snello_squadrato_reason(r.report)
    assert "745,89" in testo and "97.299,40" not in testo


def test_modello_squadrato_ma_meno_peggio_vince_il_modello(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    r = _importa(tmp_path, _modello("99700"))            # scarto SP 300 < 745,89
    assert r.report["esito"] == "squadrato"
    assert r.report["fonte"] == "qwen"
    c = r.report["confronto_letture"]
    assert (c["deterministica"], c["modello"], c["vince"]) == ("745.89", "300.00", "modello")


def test_modello_ok_vince_senza_confronto(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    r = _importa(tmp_path, _modello("100000"))
    assert r.report["esito"] == "ok" and r.report["fonte"] == "qwen"
    assert "confronto_letture" not in r.report


def test_modello_tappo_vince(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    r = _importa(tmp_path, _modello("99995"))             # scarto 5 <= 10: tappo
    assert r.report["esito"] == "tappo" and r.report["fonte"] == "qwen"


def test_ripiego_del_modello_salva_la_lettura_deterministica_squadrata(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    def vuoto(testo, intestazioni, nota=""):
        return {"corrente": [], "precedente": [], "totali": {}}
    r = _importa(tmp_path, vuoto)
    assert r.report["esito"] == "squadrato"
    assert r.report["fonte"] == "deterministico:situazione_contabile_parser"
    assert r.report["ripiego_evitato"]["esito"] == "ripiego"


def test_errore_del_modello_salva_la_lettura_deterministica_squadrata(tmp_path, monkeypatch):
    _det_949(monkeypatch)
    def rotta(testo, intestazioni, nota=""):
        raise RuntimeError("modello non raggiungibile")
    r = _importa(tmp_path, rotta)
    assert r.report["esito"] == "squadrato"
    assert r.report["fonte"] == "deterministico:situazione_contabile_parser"
    assert r.report["ripiego_evitato"]["fase"]


def test_candidato_vuoto_non_e_mai_un_ripiego(tmp_path, monkeypatch):
    _det_949(monkeypatch, bs={}, ce={})
    def vuoto(testo, intestazioni, nota=""):
        return {"corrente": [], "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito):
        _importa(tmp_path, vuoto)


def test_candidato_con_massa_non_classificata_non_e_mai_un_ripiego(tmp_path, monkeypatch):
    _det_949(monkeypatch, bs={"sp09": D("100000.00"), "sp11": D("100000.00"),
                              "_unclassified_mass": D("80000.00")},
             ce={"ce01": D("0.00")})
    def vuoto(testo, intestazioni, nota=""):
        return {"corrente": [], "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        _importa(tmp_path, vuoto)
    assert exc.value.report["deterministico"]["esito"] == "massa_non_classificata"
    # il modello che legge male NON fa risalire la lettura con massa non classificata
    r = _importa(tmp_path, _modello("2700.60"))
    assert r.report["fonte"] == "qwen" and "confronto_letture" not in r.report
