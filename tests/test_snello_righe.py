from decimal import Decimal as D

from importers.detail_enrichment import SourceRow
from importers.import_snello import righe as R


def test_importi_con_segni_e_sottolineature():
    assert R.importi("CASSA 1.199,64 A 4.251,97 3.119,94 D") == [(D("1199.64"), "A"), (D("4251.97"), ""), (D("3119.94"), "D")]
    assert R.importi("riserva legale _3_.09_4_,_3_1_") == [(D("3094.31"), "")]
    assert R.importi("Beni non superiori a € 516,46 24.087,77")[-1] == (D("24087.77"), "")
    assert R.importi("Perdite (1.500,00)") == [(D("-1500.00"), "")]
    assert R.importi("conto 10000001673 c/c 320.100,68") == [(D("320100.68"), "")]


def test_etichetta():
    assert R.etichetta("10101 CASSA CONTANTI 839,66 D 2.000,00") == "10101 CASSA CONTANTI"


def test_regola_e_saldo():
    assert R.regola_colonna(["saldo_precedente", "dare", "avere", "saldo_corrente"]) == {"n": 4, "k": 3}
    assert R.regola_colonna(["saldo_corrente", "saldo_precedente", "variazione", "percentuale"]) == {"n": 4, "k": 0}
    assert R.regola_colonna(["dare", "avere"]) == {}
    r4 = SourceRow("p1r1", 1, "T", "X 10,00 D 5,00 3,00 12,00 A", (D("10"), D("5"), D("3"), D("12")))
    assert R.saldo(r4, {"n": 4, "k": 3}) == D("-12.00")
    r1 = SourceRow("p1r2", 1, "T", "X 7,00", (D("7"),))
    assert R.saldo(r1, {"n": 4, "k": 3}) == D("7.00")          # un solo importo e il saldo e' l'ultima colonna
    r2 = SourceRow("p1r3", 1, "T", "X 7,00 8,00", (D("7"), D("8")))
    assert R.saldo(r2, {"n": 4, "k": 1}) is None               # ambiguo: dichiarato, non indovinato
    assert R.saldo(r1, {}) == D("7.00")                        # senza struttura: l'ultimo importo


def _r(i, valore, lato="L", testo=None):
    return R.Riga(id=str(i), pagina=1, lato=lato, testo=testo or f"conto {i}", valore=None if valore is None else D(valore))


def test_totali_dopo_i_figli_catene_e_somme_zero():
    righe = [_r(1, "100"), _r(2, "50"), _r(3, "150", testo="mastro A"),        # totale dopo i figli
             _r(4, "30"), _r(5, "30", testo="mastro B"), _r(6, "30", testo="gruppo B"),  # catena
             _r(7, "10"), _r(8, "-10"), _r(9, "5"), _r(10, "5", testo="mastro C")]       # coppia a somma zero dentro
    direzioni = R.marca_totali(righe)
    assert direzioni.most_common(1)[0][0] == -1
    tot = {r.id for r in righe if r.totale}
    assert {"3", "5", "6", "10"} <= tot
    assert "4" not in tot and "1" not in tot
    assert sum(r.valore for r in R.foglie(righe)) == D("185")   # 100+50+30+10-10+5


def test_totali_prima_dei_figli_e_lati_separati():
    righe = [_r(1, "80", testo="mastro"), _r(2, "50"), _r(3, "30"),
             _r(4, "80", lato="R", testo="mastro passivo"), _r(5, "80", lato="R")]
    R.marca_totali(righe)
    assert [r.id for r in righe if r.totale] == ["1", "4"]
    assert righe[1].mastro == "mastro"
