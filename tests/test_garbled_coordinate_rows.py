from decimal import Decimal

from importers.situazione_contabile_parser import _be_collect_side_facts


def _word(x0, y0, x1, y1, text, word_no=0):
    return (x0, y0, x1, y1, text, 0, 0, word_no)


def test_coordinate_row_joins_baseline_jitter_and_split_amount():
    words = [
        _word(10, 100.0, 35, 110.0, "404007", 0),
        _word(45, 101.5, 80, 111.5, "ONERI", 1),
        _word(82, 101.5, 140, 111.5, "PLURIENNALI", 2),
        _word(180, 99.0, 210, 109.0, "3.239", 3),
        _word(212, 100.5, 215, 110.5, ",", 4),
        _word(218, 101.0, 228, 111.0, "12", 5),
    ]

    facts = _be_collect_side_facts(words, 0, 250, page=7)

    assert len(facts) == 1
    fact = facts[0]
    assert fact.code == "404007"
    assert fact.description == "ONERI PLURIENNALI"
    assert fact.amount == Decimal("3239.12")
    assert fact.raw_amount == "3.239 , 12"
    assert fact.normalized_amount == "3.239,12"
    assert fact.page == 7
    assert fact.bbox == (10, 99.0, 228, 111.5)
    assert fact.confidence == "exact"


def test_coordinate_row_repairs_numeric_glyphs_only_in_amount_suffix():
    words = [
        _word(10, 50, 35, 60, "509001", 0),
        _word(45, 50, 105, 60, "FINANZIAMENTO", 1),
        _word(180, 50, 215, 60, "42.100", 2),
        _word(217, 50, 220, 60, ",", 3),
        _word(222, 50, 232, 60, "DO", 4),
    ]

    fact = _be_collect_side_facts(words, 0, 250)[0]

    assert fact.description == "FINANZIAMENTO"
    assert fact.amount == Decimal("42100.00")
    assert fact.raw_amount == "42.100 , DO"
    assert fact.normalized_amount == "42100,00"
    assert fact.confidence == "repaired"


def test_coordinate_control_ignores_detached_column_marker():
    words = [
        _word(10, 100, 45, 110, "Totale", 0),
        _word(48, 100, 85, 110, "Attivita", 1),
        _word(100, 100, 104, 110, "1", 2),
        _word(180, 100, 225, 110, "315.121,", 3),
        _word(228, 100, 238, 110, "19", 4),
    ]

    facts = _be_collect_side_facts(
        words, 0, 250, codeless=True, include_controls=True)

    assert len(facts) == 1
    assert facts[0].control
    assert facts[0].description == "TOTALE ATTIVITA 1"
    assert facts[0].amount == Decimal("315121.19")
