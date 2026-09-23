"""Formati italiani del Business plan: i valori attesi sono letti dal PDF del committente."""
from decimal import Decimal as D

from app.renderers.business_plan import fmt


def test_euro_e_segno():
    assert fmt.eur(D("4109510")) == "4.109.510"
    assert fmt.eur(D("-45192.4")) == "−45.192"
    assert fmt.eur(D("0")) == "0"
    assert fmt.eur(None) == "n.d."


def test_percentuali_rapporti_giorni():
    assert fmt.pct(D("4.035447")) == "4,04%"
    assert fmt.pct(D("-4.31")) == "−4,31%"
    assert fmt.ratio(D("5.7941"), 3) == "5,794×"
    assert fmt.ratio(D("2.94")) == "2,94×"
    assert fmt.days(D("119")) == "119,0 gg"
    assert fmt.value(D("12.5"), "percent") == "12,50%"
    assert fmt.value(D("1000"), "eur") == "1.000"
    assert fmt.value(None, "ratio") == "n.d."


def test_compatti():
    assert fmt.compact_eur(D("4109510")) == "€ 4,11 mln"
    assert fmt.compact_eur(D("4001471")) == "€ 4,00 mln"
    assert fmt.compact_eur(D("402197")) == "€ 402,2 mila"
    assert fmt.compact_eur(D("150000")) == "€ 150 mila"
    assert fmt.compact_eur(D("-150000")) == "−€ 150 mila"
    assert fmt.compact_eur(D("55")) == "€ 55"
    assert fmt.compact_range(D("960883"), D("73185")) == "€ 961 → 73 mila"
    assert fmt.compact_range(D("4109510"), D("4673885")) == "€ 4,11 → 4,67 mln"


def test_crescite_e_preposizioni():
    assert fmt.pct_short(D("5.000000")) == "5%"
    assert fmt.pct_short(D("5.5")) == "5,5%"
    assert fmt.prep("del", "5%") == "del 5%"
    assert fmt.prep("del", "1%") == "dell'1%"
    assert fmt.prep("dal", "8,61%") == "dall'8,61%"
    assert fmt.prep("al", "11%") == "all'11%"
    assert fmt.prep("al", "14,39%") == "al 14,39%"
    assert fmt.prep("dal", "180%") == "dal 180%"
    assert fmt.prep("del", "18%") == "dell'18%"


def test_numeri_dei_grafici_usano_il_trattino_ascii():
    assert fmt.chart_num(-225.5) == "-226"
    assert fmt.chart_num(4109.51) == "4.110"
    assert fmt.chart_num(8.614, 2) == "8,61"
