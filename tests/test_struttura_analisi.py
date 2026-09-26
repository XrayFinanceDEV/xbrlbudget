from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.analisi import (
    Struttura, analizza_struttura, modo_da_mappe, pagine_tabelle_nota, route_da_mappe)
from tests._struttura_fixtures import (MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_contrapposte,
                                       pdf_xbrl_con_tabelle_nota, pdf_xbrl_legge)


def _m(tipo, schema):
    return {"tipo_pagina": tipo, "schema": schema}


def test_route_da_mappe_conti_contro_legge():
    assert route_da_mappe([_m("prospetto_sp", "piano_dei_conti_gerarchico"),
                           _m("prospetto_ce", "piano_dei_conti_gerarchico")]) == ROUTE_TRIAL
    assert route_da_mappe([_m("prospetto_sp", "iv_cee_di_legge"),
                           _m("prospetto_ce", "riclassificato_con_codici_ivcee")]) == ROUTE_IVCEE
    assert route_da_mappe([_m("nota_o_testo", "elenco_piatto")]) is None       # nessun prospetto
    assert route_da_mappe([_m("prospetto_sp", "elenco_piatto"),
                           _m("prospetto_ce", "iv_cee_di_legge")]) is None     # pari: decide il classificatore


def test_xbrl_di_legge_zero_chiamate_e_pagine_dai_titoli(tmp_path):
    s = analizza_struttura(pdf_xbrl_legge(str(tmp_path / "x.pdf")),
                           mappa_pagina_fn=lambda c, png: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.fonte == "xbrl_titoli" and s.chiamate_vision == 0
    assert s.route == ROUTE_IVCEE
    assert s.pagine_sp == [1] and s.pagine_ce == [2]


def test_contrapposte_una_chiamata_per_blocco_e_route_c(tmp_path):
    chiamate = []
    def finta(client, png):
        chiamate.append(png)
        return {**MAPPA_CONTRAPPOSTE, "schema": "piano_dei_conti_gerarchico"}
    s = analizza_struttura(pdf_contrapposte(str(tmp_path / "c.pdf")), mappa_pagina_fn=finta)
    assert s.fonte == "vision" and s.chiamate_vision == len(chiamate) >= 1
    assert s.route == ROUTE_TRIAL


def test_tabelle_nota_dai_titoli_standard(tmp_path):
    path = pdf_xbrl_con_tabelle_nota(str(tmp_path / "n.pdf"))
    pagine = pagine_tabelle_nota(path)
    assert pagine == [4]
    s = analizza_struttura(path, mappa_pagina_fn=lambda c, p: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.pagine_dettaglio == pagine
    assert not set(pagine) & (set(s.pagine_sp) | set(s.pagine_ce))


def test_insiemi_vuoti_non_restringono():
    s = Struttura(fonte="vision", route=None, pagine_sp=[], pagine_ce=[], pagine_dettaglio=[],
                  chiamate_vision=1, secondi=0.1, mappe=[])
    assert s.pagine_macro() is None and s.pagine_dettagli() is None
    s2 = Struttura(fonte="vision", route=ROUTE_IVCEE, pagine_sp=[1, 2], pagine_ce=[3], pagine_dettaglio=[],
                   chiamate_vision=1, secondi=0.1, mappe=[])
    assert s2.pagine_macro() == {1, 2, 3}
    assert s2.pagine_dettagli() == {1, 2}           # senza tabelle di nota: le pagine SP (sottoconti)
    r = s2.report()
    assert r["stato"] == "ok" and r["route_struttura"] == ROUTE_IVCEE and r["pagine_sp"] == [1, 2]
    assert "mappe" not in r                          # il report persistito non porta le mappe intere


def _p(pagina, tipo, schema, ruoli, intest):
    return {"pagina": pagina, "tipo_pagina": tipo, "schema": schema,
            "sezioni": [{"posizione": "unica", "contenuto": "misto",
                         "colonne": [{"ruolo": r, "intestazione": i} for r, i in zip(ruoli, intest)]}]}


def test_modo_conti_o_legge():
    assert modo_da_mappe([_p(1, "prospetto_sp", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "elenco_piatto", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["2025"])]) == "legge"
    assert modo_da_mappe([_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]) == "legge"


def test_struttura_porta_colonne_e_pagine_senza_testo(tmp_path):
    from importers.struttura_documento.analisi import analizza_struttura
    from tests._struttura_fixtures import pdf_colonna_unica, MAPPA_COLONNA_UNICA
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    s = analizza_struttura(pdf, mappa_pagina_fn=lambda client, png: MAPPA_COLONNA_UNICA)
    assert s.modo in ("conti", "legge")
    assert s.colonne_sp and all(isinstance(r, str) for r in s.colonne_sp)
    assert s.pagine_senza_testo == []
