"""Task 7 (Fase 3): il percorso del lettore nel percorso snello, dopo i lettori noti e prima del modello.

Qwen e' sempre finto; i PDF sono sintetici in tmp_path; `_importa_modello` e `deterministico.tentativo` sono
sostituiti dove serve (nessuna rete, nessuna struttura vision)."""
import json
from decimal import Decimal as D

import pytest

from importers import import_snello, llm_provider, pdf_importer
from importers.import_snello import Risultato, deterministico
from importers.lettore import percorso
from tests.lettore.test_percorso import _REGOLE, Finto, _mai, _pdf, _schema_di_legge
from tests.lettore.test_foglie import _contrapposte_sp
from tests.test_snello_innesto import _db_in_memoria, _risultato_quadrato, _struttura
from tests.test_coge_provider import RIGHE_PAREGGIO
from tests.test_coge_provider import _pdf as _pdf_coge


def _nessun_lettore_noto(monkeypatch):
    monkeypatch.setattr(deterministico, "tentativo",
                        lambda f, o=None: {"adottato": False, "parser": "x", "esito": "vuoto"})


def _modello_sentinella(monkeypatch):
    chiamate = []

    def finto(file_path, _det, t0, **k):
        chiamate.append(file_path)
        return Risultato(bs={"sp09_disponibilita_liquide": D("5")}, ce={}, prior_bs=None, prior_ce=None,
                         report={"esito": "ok", "fonte": "modello", "secondi": 0.0}, struttura=_struttura())
    monkeypatch.setattr(import_snello, "_importa_modello", finto)
    return chiamate


def test_lettori_noti_restano_davanti(tmp_path, monkeypatch):
    def vietato(*a, **k):
        raise AssertionError("il percorso del lettore non va chiamato davanti a un lettore noto")
    monkeypatch.setattr(percorso, "importa_col_lettore", vietato)
    r = import_snello.importa(_pdf(tmp_path, _schema_di_legge()))
    assert r.report["fonte"] == "deterministico:schema_legge_generico"
    assert "lettore_percorso" not in r.report


def test_lettore_adottato_quando_quadra(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", _mai)
    r = import_snello.importa(_pdf(tmp_path, _schema_di_legge()))
    assert not modello
    assert r.report["fonte"] == "deterministico:lettore" and r.report["esito"] == "ok"
    assert r.report["modo"] == "conti"
    lp = r.report["lettore_percorso"]
    assert lp["esito"] == "adottato" and lp["cancello"] == "ok" and lp["mesi_precedente"] == 12
    assert r.bs["sp03_immob_materiali"] == D("800.00") and r.bs["sp13_utile_perdita"] == D("400.00")
    assert r.prior_bs is not None and r.prior_ce is not None
    assert r.report["deterministico"]["prior_stato"] == "letto"
    json.dumps(r.report, default=str)          # il report finisce nel DB


def test_lettore_non_quadra_prosegue_il_modello(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", _mai)
    voci = _schema_di_legge()
    # il totale attivo stampato non torna con le foglie: un blocco oltre soglia
    i = next(k for k, v in enumerate(voci) if v[2] == "2.000,00")
    voci[i] = (voci[i][0], voci[i][1], "2.300,00")
    r = import_snello.importa(_pdf(tmp_path, voci))
    assert len(modello) == 1 and r.report["fonte"] == "modello"
    lp = r.report["lettore_percorso"]
    assert lp["esito"] in ("non_adottato", "vuoto") and lp["blocchi"]


def test_senza_ce_il_percorso_di_oggi_prosegue(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", Finto(_REGOLE))
    r = import_snello.importa(_pdf(tmp_path, _contrapposte_sp()))
    assert len(modello) == 1 and r.report["lettore_percorso"]["esito"] == "vuoto"


def test_interruttore_spento_identico(tmp_path, monkeypatch):
    """Spento: il percorso e' quello di prima. Il confronto e' con la sequenza di BASE scritta a mano
    (lettori noti, poi `_importa_modello`), con il modulo del lettore che fallisce il test se solo importato."""
    _nessun_lettore_noto(monkeypatch)
    _modello_sentinella(monkeypatch)
    pdf = _pdf(tmp_path, _contrapposte_sp())

    def vietato(*a, **k):
        raise AssertionError("IMPORT_LETTORE spento: il percorso del lettore non va chiamato")
    monkeypatch.setattr(percorso, "importa_col_lettore", vietato)
    monkeypatch.setattr(import_snello, "_tenta_lettore", vietato)
    base = import_snello._importa_modello(pdf, deterministico.tentativo(pdf), 0.0, ocr_text=None, analizza=None,
                                          leggi_conti=None, leggi_voci=None, trascrivi=None, route_hint=None)
    for valore in ("0", "false", "No", "OFF"):
        monkeypatch.setenv("IMPORT_LETTORE", valore)
        spento = import_snello.importa(pdf)
        assert (spento.bs, spento.ce, spento.prior_bs, spento.prior_ce) == (base.bs, base.ce, base.prior_bs, base.prior_ce)
        assert spento.report == base.report and "lettore_percorso" not in spento.report


def test_qwen_in_errore_prosegue(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)

    def giu(*a, **k):
        raise llm_provider.LLMProviderError("gx10 giu'")
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", giu)
    r = import_snello.importa(_pdf(tmp_path, _contrapposte_sp()))
    assert len(modello) == 1 and r.report["fonte"] == "modello"
    assert r.report["lettore_percorso"]["esito"] in ("vuoto", "non_adottato")


def test_eccezione_del_percorso_prosegue(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)

    def rotto(*a, **k):
        raise RuntimeError("difetto del lettore")
    monkeypatch.setattr(percorso, "importa_col_lettore", rotto)
    r = import_snello.importa(_pdf(tmp_path, _contrapposte_sp()))
    assert len(modello) == 1
    assert r.report["lettore_percorso"]["esito"] == "eccezione"
    assert "difetto del lettore" in r.report["lettore_percorso"]["errore"]


def test_snello_non_riuscito_porta_il_tentativo_del_lettore(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)

    def cade(*a, **k):
        raise import_snello.SnelloNonRiuscito({"esito": "ripiego", "fase": "verifica"})
    monkeypatch.setattr(import_snello, "_importa_modello", cade)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", Finto(_REGOLE))
    with pytest.raises(import_snello.SnelloNonRiuscito) as e:
        import_snello.importa(_pdf(tmp_path, _contrapposte_sp()))
    assert e.value.report["lettore_percorso"]["esito"] == "vuoto"


def _salva_con_mesi(tmp_path, monkeypatch, mesi_lettore, period_months=9):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finta(file_path, *, ocr_text=None, **_):
        r = _risultato_quadrato()
        r.prior_bs, r.prior_ce = dict(r.bs), {"ce01_ricavi_vendite": D("0")}
        r.report["fonte"] = "deterministico:lettore"
        r.report["lettore_percorso"] = {"esito": "adottato", "mesi_precedente": mesi_lettore}
        return r
    monkeypatch.setattr(import_snello, "importa", finta)
    sf = _db_in_memoria(monkeypatch)
    res = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf_coge(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025, company_name="Mesi dal lettore",
        create_company=True, sector=1, user_id="snello-mesi", period_months=period_months)
    from database.models import FinancialYear
    with sf() as db:
        return sorted((fy.year, fy.period_months) for fy in
                      db.query(FinancialYear).filter_by(company_id=res["company_id"]))


def test_mesi_dal_lettore_nel_salvataggio(tmp_path, monkeypatch):
    # la colonna di confronto e' di 9 mesi: l'anno precedente si salva parziale, mai come anno pieno
    assert (2024, 9) in _salva_con_mesi(tmp_path, monkeypatch, 9)


def test_mesi_del_lettore_pieni_anno_intero(tmp_path, monkeypatch):
    anni = _salva_con_mesi(tmp_path, monkeypatch, 12)
    assert (2024, None) in anni


def test_mesi_dal_lettore_anche_ad_anno_pieno(tmp_path, monkeypatch):
    # F3-14: corrente di 12 mesi (period_months assente), colonna di confronto di 9: il precedente e' parziale
    assert (2024, 9) in _salva_con_mesi(tmp_path, monkeypatch, 9, period_months=None)


def test_senza_mesi_del_lettore_anno_pieno_invariato(tmp_path, monkeypatch):
    anni = _salva_con_mesi(tmp_path, monkeypatch, None, period_months=None)
    assert (2024, None) in anni and (2024, 9) not in anni


def test_adozione_che_solleva_prosegue_il_modello(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    modello = _modello_sentinella(monkeypatch)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", _mai)

    def rotta(*a, **k):
        raise RuntimeError("struttura rotta")
    monkeypatch.setattr(import_snello, "_risultato_deterministico", rotta)
    r = import_snello.importa(_pdf(tmp_path, _schema_di_legge()))
    assert len(modello) == 1 and r.report["lettore_percorso"]["esito"] == "eccezione_adozione"


def test_report_senza_etichette_ne_importi(tmp_path, monkeypatch):
    _nessun_lettore_noto(monkeypatch)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", _mai)
    r = import_snello.importa(_pdf(tmp_path, _schema_di_legge()))
    testo = json.dumps(r.report["lettore_percorso"])
    for k in ("scarti", "chiusure", "scelte", "sbilancio", "senza_colonna", "sp13_da"):
        assert k not in r.report["lettore_percorso"]
    assert "impianti" not in testo.lower() and "2.000" not in testo


def test_fondo_oltre_il_cespite_nelle_anomalie(tmp_path, monkeypatch):
    # l'eccedenza tagliata dal lettore arriva nelle anomalie come per il percorso snello (`conti.py`)
    _nessun_lettore_noto(monkeypatch)
    vero = percorso.importa_col_lettore

    def con_taglio(*a, **k):
        out = vero(*a, **k)
        out["diagnostica"]["immobilizzazioni_negative_tagliate"] = [["sp02_immob_immateriali", "4.00"]]
        return out
    monkeypatch.setattr(percorso, "importa_col_lettore", con_taglio)
    monkeypatch.setattr(llm_provider, "chiama_gx10_json", _mai)
    r = import_snello.importa(_pdf(tmp_path, _schema_di_legge()))
    assert r.report["fonte"] == "deterministico:lettore"
    assert ["sp02_immob_immateriali", "4.00"] in r.report["anomalie"]
    assert r.report["diag"]["immobilizzazioni_negative_tagliate"] == [["sp02_immob_immateriali", "4.00"]]
