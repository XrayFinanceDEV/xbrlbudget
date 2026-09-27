from decimal import Decimal as D

import pytest

from importers import import_snello as S
from importers.struttura_documento.analisi import Struttura
from tests._struttura_fixtures import pdf_colonna_unica


def _struttura(modo, **kw):
    base = dict(fonte="vision", route=None, pagine_sp=[1], pagine_ce=[1], pagine_dettaglio=[],
                chiamate_vision=1, secondi=0.1, mappe=[], modo=modo,
                colonne_sp=["saldo_corrente", "saldo_precedente"], colonne_ce=["saldo_corrente", "saldo_precedente"],
                intestazioni_sp=["2025", "2024"], intestazioni_ce=["2025", "2024"], pagine_senza_testo=[])
    base.update(kw)
    return Struttura(**base)


def _voci_quadrate(testo, intestazioni, nota=""):
    if "rilettura" in nota:
        raise AssertionError("non serve rileggere")
    return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                         ("CE.A.1", D("500")), ("CE.B.7", D("400")), ("CE.21", D("100"))],
            "precedente": [], "totali": {"totale_attivo": D("1000"), "totale_passivo": D("1000"), "utile": D("100")}}


def test_legge_che_quadra(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=_voci_quadrate)
    assert r.bs["sp09_disponibilita_liquide"] == D("1000.00") and r.ce["ce06_servizi"] == D("400.00")
    assert r.report["esito"] == "ok" and r.prior_bs is None
    assert r.bs["_plug_residual"] == 0


def test_legge_oltre_soglia_rilegge_una_volta_poi_ripiega(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    chiamate = []
    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        return {"corrente": [("SPA.C.IV.1", D("5000")), ("SPP.A.I", D("900")), ("CE.A.1", D("500")), ("CE.B.7", D("400"))],
                "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["esito"] == "ripiego" and exc.value.report["fase"] == "verifica"
    assert len(chiamate) == 3 and any("scarto" in n for n in chiamate)     # SP, CE, una rilettura


def test_route_hint_si_inoltra_alla_struttura(tmp_path):
    # Task lotto-b, fix 9: route_hint arriva dal chiamante (pdf_importer.py, la route del
    # classificatore) fino ad analizza_struttura, che lo passa a modo_da_mappe. Il default None
    # non cambia la firma che i test esistenti usano (`analizza=lambda p: ...`).
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    visti = {}

    def analizza(p, *, route_hint=None):
        visti["route_hint"] = route_hint
        return _struttura("legge")

    r = S.importa(pdf, analizza=analizza, leggi_voci=_voci_quadrate, route_hint="TRIAL_BALANCE")
    assert visti["route_hint"] == "TRIAL_BALANCE"
    assert r.report["esito"] == "ok"


def test_route_hint_assente_non_rompe_una_analizza_senza_quel_parametro(tmp_path):
    # Senza route_hint (default None) la chiamata resta quella di sempre, posizionale sola:
    # una `analizza` finta che non accetta affatto quel parametro non deve rompersi.
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=_voci_quadrate)
    assert r.report["esito"] == "ok"


def test_struttura_in_errore_ripiega(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    def rotta(p):
        raise RuntimeError("sonnet giu'")
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=rotta)
    assert exc.value.report["fase"] == "struttura" and exc.value.report["errore"] == "RuntimeError"


def test_pagina_condivisa_sp_e_ce_si_legge_una_sola_volta(tmp_path):
    """Task lotto-b, fix 8: una pagina "prospetto_sp_e_ce" (SP e CE sulla stessa pagina fisica)
    entra in pagine_sp E pagine_ce (TIPI_SP/TIPI_CE di analisi.py): leggerla due volte manda la
    stessa riga stampata a due chiamate indipendenti, che possono risolverla con due percorsi
    diversi (come budget_397: la stessa riga di debito letta 'SPP.D.O' dalla chiamata SP e
    'SPP.D.E' dalla chiamata CE) e la contano due volte, perche' da_coppie deduplica solo per
    percorso esatto. Una pagina cosi' si legge una volta sola."""
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    chiamate = []

    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        # stesso debito, percorso diverso alla seconda chiamata SE la pagina viene letta due volte
        percorso = "SPP.D.O" if len(chiamate) == 1 else "SPP.D.E"
        return {"corrente": [("SPA.C.IV.1", D("2100")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                             (percorso, D("1100")), ("CE.A.1", D("500")), ("CE.B.7", D("400")), ("CE.21", D("100"))],
                "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[1], pagine_ce=[1],
                                     mappe=[{"pagina": 1, "tipo_pagina": "prospetto_sp_e_ce"}])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert len(chiamate) == 1
    assert r.report["esito"] == "ok"       # con una lettura sola il debito conta una volta: attivo=passivo=2100


def test_pagina_condivisa_rilettura_dichiara_entrambe_le_sezioni(tmp_path):
    """Fix round 1, minor 4: sulla pagina condivisa la rilettura dopo uno scarto oltre soglia
    rilegge SP e CE insieme (`_leggi_sp_e_ce`), ma la diagnostica `letture` incrementava solo la
    sezione scelta dall'euristica (`sezione`), lasciando l'altra ferma a 1 anche se era stata
    riletta anch'essa. Ora entrambe le sezioni dichiarano la rilettura."""
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    chiamate = []

    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        debito = D("900") if len(chiamate) == 1 else D("1100")   # 1a chiamata: scarto; 2a: quadra
        return {"corrente": [("SPA.C.IV.1", D("2100")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                             ("SPP.D.E", debito), ("CE.A.1", D("500")), ("CE.B.7", D("400")),
                             ("CE.21", D("100"))],
                "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[1], pagine_ce=[1],
                                     mappe=[{"pagina": 1, "tipo_pagina": "prospetto_sp_e_ce"}])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert len(chiamate) == 2
    assert r.report["esito"] == "ok"
    assert r.report["letture"] == {"sp": 2, "ce": 2}


# --- Estensioni Task 8 (rulings del controllo) --------------------------------------------------


def test_legge_vuoto_rilegge_poi_ripiega(tmp_path):
    """esito 'vuoto' (attivo e passivo entrambi zero) si tratta come oltre_soglia: una sola
    rilettura, poi SnelloNonRiuscito con errore 'vuoto' dichiarato."""
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    chiamate = []
    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        return {"corrente": [], "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["esito"] == "ripiego" and exc.value.report["fase"] == "verifica"
    assert exc.value.report["errore"] == "vuoto"
    assert len(chiamate) == 3   # SP, CE, una rilettura


def test_legge_tappo_entro_soglia_plug_residual(tmp_path):
    """Uno scarto SP entro soglia si tampona (sp16g altri debiti): _plug_residual riporta
    esattamente l'importo del tappo e il report dichiara esito 'tappo'."""
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))

    def voci(testo, intestazioni, nota=""):
        if intestazioni and intestazioni[0].startswith("SP"):
            return {"corrente": [("SPA.B.II", D("1000")), ("SPA.C.IV", D("550")),
                                 ("SPP.A.I", D("800")), ("SPP.A.IX", D("100")), ("SPP.D.7", D("600"))],
                    "precedente": [], "totali": {}}
        return {"corrente": [("CE.A.1", D("400")), ("CE.B.7", D("300"))], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", intestazioni_sp=["SP-2025"], intestazioni_ce=["CE-2025"])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert r.report["esito"] == "tappo"
    assert r.report["tappo"]["corrente"]["campo"] == "sp16g_altri_debiti_breve"
    assert r.bs["_plug_residual"] == D("50.00")


def test_conti_percorso_finto_bilancio_quadra(tmp_path, monkeypatch):
    """Modo 'conti' con un `leggi_conti` finto che assegna i percorsi a righe fabbricate a mano
    (righe_da_pdf monkeypatchato): risultato in bilancio, `_unclassified_mass` sempre presente."""
    from importers.import_snello import righe as R

    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    righe_finte = [
        R.Riga(id="p1r1", pagina=1, lato="L", testo="IMPIANTI", valore=D("1000")),
        R.Riga(id="p1r2", pagina=1, lato="L", testo="BANCA C/C", valore=D("500")),
        R.Riga(id="p1r3", pagina=1, lato="R", testo="CAPITALE SOCIALE", valore=D("1000")),
        R.Riga(id="p1r4", pagina=1, lato="R", testo="FORNITORI ITALIA", valore=D("500")),
    ]
    monkeypatch.setattr(R, "righe_da_pdf", lambda *a, **k: righe_finte)

    def leggi_conti(righe, foglie):
        percorsi = {"p1r1": "SPA.B.II", "p1r2": "SPA.C.IV", "p1r3": "SPP.A.I", "p1r4": "SPP.D.7"}
        for f in foglie:
            f.percorso = percorsi[f.id]
        return {"chiamate": 1, "saltate_prima": 0, "senza_percorso": 0}

    r = S.importa(pdf, analizza=lambda p: _struttura("conti"), leggi_conti=leggi_conti)
    assert r.report["esito"] == "ok" and r.report["modo"] == "conti"
    assert r.bs["sp09_disponibilita_liquide"] == D("500.00")
    assert r.bs["_unclassified_mass"] == D("0")
    assert r.prior_bs is None


def test_eccezione_in_lettura_diventa_ripiego(tmp_path):
    """Un'eccezione del lettore (ContestoEccessivo, o qualunque altra) non esce cruda: diventa
    SnelloNonRiuscito con fase e classe dichiarate."""
    from importers.llm_provider import ContestoEccessivo

    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    def voci(testo, intestazioni, nota=""):
        raise ContestoEccessivo("troppo grande")
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["fase"] == "lettura"
    assert exc.value.report["errore"] == "ContestoEccessivo"


def test_anomalie_immobilizzazioni_negative(tmp_path):
    """report['anomalie'] dichiara un'immobilizzazione netta negativa, senza correggerla."""
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))

    def voci(testo, intestazioni, nota=""):
        if intestazioni and intestazioni[0].startswith("SP"):
            return {"corrente": [("SPA.B.II", D("-50")), ("SPA.C.IV", D("1050")),
                                 ("SPP.A.I", D("1000")), ("SPP.A.IX", D("0"))],
                    "precedente": [], "totali": {}}
        return {"corrente": [], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", intestazioni_sp=["SP-2025"], intestazioni_ce=["CE-2025"])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert r.report["esito"] == "ok"
    assert r.report["anomalie"] == [["sp03_immob_materiali", "-50.00"]]
    assert r.bs["sp03_immob_materiali"] == D("-50.00")
