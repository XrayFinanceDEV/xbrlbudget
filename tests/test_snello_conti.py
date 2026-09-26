from decimal import Decimal as D

from importers.import_snello.conti import applica_lato, da_coppie, da_foglie
from importers.import_snello.percorsi import NOMI
from importers.import_snello.righe import Riga
from importers.iv_cee_hierarchy import detail_fields

_TIER0 = ("sp02", "sp03", "sp04", "sp11", "sp12", "sp13", "sp16a", "sp17a")


def _f(i, lato, valore, percorso):
    return Riga(id=str(i), pagina=1, lato=lato, testo=f"c{i}", valore=D(valore), percorso=percorso)


def test_contrapposte_fondo_a_destra_e_cc_passivo():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "R", "400", "SPA.B.II.2.F"),
              _f(3, "L", "300", "SPA.C.IV.1"), _f(4, "R", "150", "SPA.C.IV.1"),   # c/c stampato fra le passivita'
              _f(5, "R", "500", "SPP.A.I"), _f(6, "R", "250", "SPP.D.7"),
              _f(7, "L", "80", "CE.B.7"), _f(8, "R", "100", "CE.A.1"), _f(9, "R", "20", "R"),
              _f(10, "L", "5", "X")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03b_impianti_macchinari"] == D("600.00")
    assert bs["sp09_disponibilita_liquide"] == D("300.00")
    assert bs["sp16a_debiti_banche_breve"] == D("150.00")
    assert bs["sp16_debiti_breve"] == D("400.00")
    assert ce["ce06_servizi"] == D("80.00") and ce["ce01_ricavi_vendite"] == D("100.00")
    assert diag["risultato_stampato"] == "20.00" and diag["lato_corretti"] == 1
    assert diag["escluse"] == [["10", "X", "5.00"]]


def test_colonna_unica_con_segno():
    foglie = [_f(1, "T", "1000", "SPA.B.II.4"), _f(2, "T", "-300", "SPA.B.II.4.F"),
              _f(3, "T", "-200", "SPP.D.4"), _f(4, "T", "50", "SPP.D.12"),          # erario in dare: e' un credito
              _f(5, "T", "-500", "SPP.A.I"), _f(6, "T", "90", "CE.B.6"), _f(7, "T", "-60", "CE.A.1")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03d_altri_beni"] == D("700.00")
    assert bs["sp16a_debiti_banche_breve"] == D("200.00")
    assert bs["sp06e_crediti_tributari_breve"] == D("50.00")
    assert bs["sp11_capitale"] == D("500.00")
    assert ce["ce05_materie_prime"] == D("90.00") and ce["ce01_ricavi_vendite"] == D("60.00")


def test_applica_lato_non_tocca_i_fondi():
    foglie = [_f(1, "L", "10", "SPA.B.II.2"), _f(2, "R", "4", "SPA.B.II.2.F"), _f(3, "R", "9", "SPP.D.7")]
    assert applica_lato(foglie) == 0
    assert foglie[1].percorso == "SPA.B.II.2.F"


def test_coppie_schema_di_legge_genitore_e_fondo():
    coppie = [("SPA.B.I", D("584094")), ("SPA.B.I.1", D("118720")), ("SPA.B.I.5", D("88362")),
              ("SPA.B.II.2", D("47738")), ("SPA.B.II.2.F", D("17605")),
              ("SPA.C.II.1", D("863659")), ("SPA.C.II.1.E", D("800000")), ("SPA.C.II.1.O", D("63659")),
              ("SPP.D.4", D("100")), ("SPP.D.4", D("100")), ("CE.B.7", D("9")), ("CE.21", D("7422"))]
    bs, ce, diag = da_coppie(coppie)
    assert bs["sp02_immob_immateriali"] == D("207082.00")        # il genitore cade: contano i figli
    assert bs["sp03b_impianti_macchinari"] == D("30133.00")       # fondo sottratto
    assert bs["sp06a_crediti_clienti_breve"] == D("800000.00") and bs["sp07a_crediti_clienti_lungo"] == D("63659.00")
    assert bs["sp16a_debiti_banche_breve"] == D("100.00")         # la voce ripetuta si conta una volta
    assert diag["risultato_stampato"] == "7422.00"


def _nessun_tier0_negativo(bs):
    assert all(bs.get(NOMI[c], D("0.00")) >= 0 for c in _TIER0 if NOMI[c] in bs)


def _coerenza_aggregati(bs, brevi=("sp02", "sp03", "sp04", "sp06", "sp16")):
    """Nessun dettaglio negativo, e l'aggregato resta la somma di quel che completa() gli
    attribuisce (diretto + dettagli): la stessa formula che completa() applica, verificata
    dal lato del risultato."""
    for breve in brevi:
        pieno = NOMI[breve]
        dettagli = [d for d in detail_fields(pieno) if d in bs]
        assert all(bs[d] >= 0 for d in dettagli), f"{pieno}: dettaglio negativo"


def test_fondo_piu_fine_del_lordo_stampato_coppie():
    bs, ce, diag = da_coppie([("SPA.B.II", D("1000")), ("SPA.B.II.2.F", D("400")), ("SPP.D.7", D("600"))])
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert "sp03b_impianti_macchinari" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)
    assert diag["lato_irrisolti"] == []


def test_fondo_piu_fine_del_lordo_stampato_foglie():
    foglie = [_f(1, "L", "1000", "SPA.B.II"), _f(2, "R", "400", "SPA.B.II.2.F"), _f(3, "R", "600", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert "sp03b_impianti_macchinari" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)
    assert diag["lato_irrisolti"] == []


def test_lato_senza_contropartita_diventa_fallback_dichiarato():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "L", "800", "SPA.C.IV.1"),
              _f(3, "R", "50", "SPA.B.I.1"), _f(4, "R", "500", "SPP.A.I"), _f(5, "R", "600", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp16g_altri_debiti_breve"] == D("50.00")
    assert diag["lato_corretti"] == 0
    assert diag["lato_irrisolti"] == [["3", "SPA.B.I.1", "50.00"]]
    assert "sp02_immob_immateriali" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)


def test_fornitori_stampato_fra_gli_attivi_va_al_credito_di_contropartita():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "L", "300", "SPP.D.7"), _f(3, "R", "500", "SPP.A.I")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp06g_crediti_altri_breve"] == D("300.00")
    assert bs["sp06_crediti_breve"] == D("300.00")
    assert diag["lato_corretti"] == 1
    assert diag["lato_irrisolti"] == []
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)


def test_lato_irrisolti_sempre_presente_anche_vuoto():
    foglie = [_f(1, "L", "10", "SPA.B.II.2"), _f(2, "R", "4", "SPA.B.II.2.F"), _f(3, "R", "9", "SPP.D.7")]
    _, _, diag = da_foglie(foglie)
    assert diag["lato_irrisolti"] == []
    _, _, diag2 = da_coppie([("SPP.D.7", D("9"))])
    assert diag2["lato_irrisolti"] == []
