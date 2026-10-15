"""XBRL 2018 con crediti e debiti infragruppo (budget_1324, Santini): crediti verso controllanti
e verso imprese sottoposte al controllo delle controllanti, debiti verso controllate,
controllanti e sottoposte. Nessuno ha un sotto-campo proprio tranne i crediti verso
controllanti; gli altri vanno fra gli altri crediti / altri debiti, sommati e mai scartati."""
from decimal import Decimal as D

from importers.xbrl_parser_enhanced import EnhancedXBRLParser

NS = "{http://www.infocamere.it/itnn/fr/itcc/ci/2018-11-04}"


def _mappa(facts):
    p = EnhancedXBRLParser.__new__(EnhancedXBRLParser)
    EnhancedXBRLParser.__init__(p, db_session=object())
    return p.map_facts_to_fields_with_reconciliation({NS + k: D(v) for k, v in facts.items()})


FATTI = {
    "TotaleCrediti": "1345",
    "TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio": "1300",
    "CreditiVersoClientiEsigibiliEntroEsercizioSuccessivo": "1000",
    "CreditiVersoControllantiEsigibiliEntroEsercizioSuccessivo": "80",
    "CreditiVersoImpreseSottoposteControlloControllantiEsigibiliEntroEsercizioSuccessivo": "200",
    "CreditiVersoAltriEsigibiliEntroEsercizioSuccessivo": "20",
    "CreditiImposteAnticipateTotaleImposteAnticipate": "45",
    "TotaleDebiti": "850",
    "TotaleDebitiQuotaScadenteEntroEsercizio": "850",
    "DebitiDebitiVersoFornitoriEsigibiliEntroEsercizioSuccessivo": "700",
    "DebitiDebitiVersoImpreseControllateEsigibiliEntroEsercizioSuccessivo": "70",
    "DebitiDebitiVersoControllantiEsigibiliEntroEsercizioSuccessivo": "30",
    "DebitiDebitiVersoImpreseSottoposteControlloControllantiEsigibiliEntroEsercizioSuccessivo": "-150",
    "DebitiAltriDebitiEsigibiliEntroEsercizioSuccessivo": "200",
    "PatrimonioNettoCapitale": "495",           # attivo 1.345 = passivo 850 + 495
}


def test_crediti_infragruppo_e_imposte_anticipate_nel_totale():
    bs, _inc, info = _mappa(FATTI)
    assert bs["sp06d_crediti_controllanti_breve"] == D("80")
    assert bs["sp06g_crediti_altri_breve"] == D("220")          # altri + sottoposte
    assert bs["sp06f_imposte_anticipate_breve"] == D("45")
    assert bs["sp06_crediti_breve"] == D("1345")                # entro + imposte anticipate
    assert "total_crediti" not in info["aggregate_conflicts"]


def test_debiti_infragruppo_fra_gli_altri_debiti():
    bs, _inc, info = _mappa(FATTI)
    assert bs["sp16g_altri_debiti_breve"] == D("150")           # 200 + 70 + 30 - 150
    assert bs["sp16_debiti_breve"] == D("850")
    assert "sp16_debiti_breve" not in info["aggregate_conflicts"]
