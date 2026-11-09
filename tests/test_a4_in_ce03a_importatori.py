"""Task 5-bis parte 1: la voce A.4 (incrementi di immobilizzazioni per lavori interni) va in
``ce03a`` in ogni importatore; ``ce03`` resta A.3 (lavori in corso su ordinazione).
Solo dati sintetici."""
import re
from decimal import Decimal

from importers import situazione_contabile_parser as scp
from importers import source_reconciliation as sr
from importers import pdf_extractor_llm as llm
from importers import legal_path_evidence as lpe
from importers import standard_ivcee_parser as sip

D = Decimal
A4 = "ce03a_incrementi_immobilizzazioni"
A3 = "ce03_lavori_interni"


def _rows(spec):
    return [sip._Row(page=1, y=float(i), label=lab, values=(val, None)) for i, (lab, val) in enumerate(spec)]


def test_compact_ivcee_a4_in_ce03a():
    rows = _rows([
        ("conto economico", None),
        ("a) valore della produzione", None),
        ("1) ricavi delle vendite", D("1000")),
        ("4) incrementi di immobilizzazioni per lavori interni", D("50")),
        ("totale valore della produzione", D("1050")),
        ("b) costi della produzione", None),
        ("7) per servizi", D("400")),
        ("9) per il personale", D("300")),
        ("a) salari e stipendi", D("300")),
        ("10) ammortamenti e svalutazioni", D("100")),
        ("totale costi della produzione", D("800")),
        ("differenza tra valore e costi della produzione", D("250")),
        ("c) proventi e oneri finanziari", None),
        ("totale proventi e oneri finanziari", D("0")),
        ("d) rettifiche di valore", D("0")),
        ("risultato prima delle imposte", D("250")),
        ("20) imposte sul reddito", D("50")),
        ("21) utile (perdita) dell'esercizio", D("200")),
    ])
    ce = sip._parse_compact_income(rows)
    assert ce is not None
    assert ce[A4] == D("50")
    assert ce.get(A3, D("0")) == D("0")


def test_source_reconciliation_a4_in_ce03a():
    facts = {"ce_a": D("1050"), "ce_b": D("800"), "ce_pretax": D("250"), "ce_result": D("200"),
             "ceitem_1": D("1000"), "ceitem_4": D("50"), "ceitem_7": D("400"),
             "ceitem_9": D("300"), "ceitem_10": D("100"), "ceitem_20": D("50")}
    out = sr._income(facts, D("200"))
    assert out is not None
    assert out[A4] == D("50") and out.get(A3, D("0")) == D("0")


def test_legal_path_evidence_mapping_a4_in_ce03a():
    src = open(lpe.__file__, encoding="utf-8").read()
    assert "'A.4':'ce03a_incrementi_immobilizzazioni'" in src
    assert "'A.4':'ce03_lavori_interni'" not in src


def test_schema_llm_distingue_a3_e_a4():
    campi = llm.IncomeStatementExtraction.model_fields
    assert A4 in campi and "A.4" in campi[A4].description
    assert "A.3" in campi[A3].description and "A.4" not in campi[A3].description
    assert A4 in llm._BLANK_CURRENT_CE_ROWS
    assert A3 not in llm._BLANK_CURRENT_CE_ROWS


def test_route_c_parole_chiave_incrementi_in_ce03a():
    assert (['INCREM', 'IMMOB'], 'ce03a') in scp._CE_RICAVI_RULES
    assert (['INCREM', 'IMMOB'], 'ce03') not in scp._CE_RICAVI_RULES
    assert (['INCREMENTI'], 'ce03a') in scp._VSEG_CE_RICAVI
    assert (['INCREMENTI'], 'ce03') not in scp._VSEG_CE_RICAVI


def test_source_reconciliation_a3_stampata_va_in_ce03_non_in_ce02():
    facts = {"ce_a": D("1080"), "ce_b": D("800"), "ce_pretax": D("280"), "ce_result": D("230"),
             "ceitem_1": D("1000"), "ceitem_3": D("30"), "ceitem_4": D("50"), "ceitem_7": D("400"),
             "ceitem_9": D("300"), "ceitem_10": D("100"), "ceitem_20": D("50")}
    out = sr._income(facts, D("230"))
    assert out is not None
    assert out[A3] == D("30") and out[A4] == D("50")
    assert out["ce02_variazioni_rimanenze"] == D("0")
