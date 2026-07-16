from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import FinancialYear
from importers.xbrl_parser_enhanced import EnhancedXBRLParser


XBRL_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:t="urn:test-taxonomy">
 <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <xbrli:unit id="EUR"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
 <xbrli:context id="D_9M"><xbrli:entity><xbrli:identifier scheme="urn:cf">ENTITY1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="I_9M"><xbrli:entity><xbrli:identifier scheme="urn:cf">ENTITY1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-09-30</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:context id="D_FY"><xbrli:entity><xbrli:identifier scheme="urn:cf">ENTITY1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="I_FY"><xbrli:entity><xbrli:identifier scheme="urn:cf">ENTITY1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:context id="D_9M_DIM"><xbrli:entity><xbrli:identifier scheme="urn:cf">ENTITY1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="t:Scope">t:SegmentA</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
 <t:DatiAnagraficiDenominazione contextRef="I_FY">Context Test Srl</t:DatiAnagraficiDenominazione>
 <t:TotaleDisponibilitaLiquide contextRef="I_FY" unitRef="EUR" decimals="2">1000</t:TotaleDisponibilitaLiquide>
 <t:PatrimonioNettoCapitale contextRef="I_FY" unitRef="EUR" decimals="2">900</t:PatrimonioNettoCapitale>
 <t:PatrimonioNettoUtilePerditaEsercizio contextRef="I_FY" unitRef="EUR" decimals="2">100</t:PatrimonioNettoUtilePerditaEsercizio>
 <t:ValoreProduzioneRicaviVenditePrestazioni contextRef="D_FY" unitRef="USD" decimals="2">9999</t:ValoreProduzioneRicaviVenditePrestazioni>
 <t:ValoreProduzioneRicaviVenditePrestazioni contextRef="D_FY" unitRef="EUR" decimals="2">200</t:ValoreProduzioneRicaviVenditePrestazioni>
 <t:CostiProduzioneMateriePrimeSussidiarieConsumoMerci contextRef="D_FY" unitRef="EUR" decimals="2">100</t:CostiProduzioneMateriePrimeSussidiarieConsumoMerci>
 <t:TotaleDisponibilitaLiquide contextRef="I_9M" unitRef="EUR" decimals="2">800</t:TotaleDisponibilitaLiquide>
 <t:PatrimonioNettoCapitale contextRef="I_9M" unitRef="EUR" decimals="2">750</t:PatrimonioNettoCapitale>
 <t:PatrimonioNettoUtilePerditaEsercizio contextRef="I_9M" unitRef="EUR" decimals="2">50</t:PatrimonioNettoUtilePerditaEsercizio>
 <t:ValoreProduzioneRicaviVenditePrestazioni contextRef="D_9M" unitRef="EUR" decimals="2">120</t:ValoreProduzioneRicaviVenditePrestazioni>
 <t:CostiProduzioneMateriePrimeSussidiarieConsumoMerci contextRef="D_9M" unitRef="EUR" decimals="2">70</t:CostiProduzioneMateriePrimeSussidiarieConsumoMerci>
 <t:ValoreProduzioneRicaviVenditePrestazioni contextRef="D_9M_DIM" unitRef="EUR" decimals="2">7777</t:ValoreProduzioneRicaviVenditePrestazioni>
</xbrli:xbrl>
"""


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_same_year_annual_and_nine_month_contexts_are_kept_separate(tmp_path: Path):
    source = tmp_path / "annual-and-9m.xbrl"
    source.write_text(XBRL_FIXTURE, encoding="utf-8")
    db = _session()
    parser = EnhancedXBRLParser(db_session=db)

    root = parser.parse_file(str(source))
    contexts = parser.extract_contexts(root)
    facts = parser.extract_facts(root, contexts)

    assert {key.period_months for key in facts} == {9, 12}
    annual_key = next(key for key in facts if key.period_months == 12)
    interim_key = next(key for key in facts if key.period_months == 9)
    revenue_tag = "{urn:test-taxonomy}ValoreProduzioneRicaviVenditePrestazioni"
    assert facts[annual_key][revenue_tag] == Decimal("200")
    assert facts[interim_key][revenue_tag] == Decimal("120")

    result = parser.import_to_database(str(source), create_company=True)
    imported = db.query(FinancialYear).filter(FinancialYear.year == 2025).all()
    assert len(imported) == 2
    assert {row.period_months for row in imported} == {None, 9}
    assert len(result["periods_imported"]) == 2
    assert all(row.validation_status == "verified" for row in imported)
    assert all(row.forecastable for row in imported)


def test_xbrl_aggregate_conflict_is_diagnostic_not_a_plug():
    parser = EnhancedXBRLParser(db_session=_session())
    facts = {
        "{urn:test}TotaleCrediti": Decimal("100"),
        "{urn:test}TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio": Decimal("80"),
    }
    bs, _, info = parser.map_facts_to_fields_with_reconciliation(facts)
    assert bs["sp06_crediti_breve"] == Decimal("80")
    assert info["aggregate_conflicts"]["total_crediti"]["difference"] == 20.0
    assert info["reconciliation_adjustments"] == {}


def test_xbrl_maps_other_provisions_and_credit_write_down_to_distinct_ce_lines():
    parser = EnhancedXBRLParser(db_session=_session())
    facts = {
        "{urn:test}CostiProduzioneAltriAccantonamenti": Decimal("4005000"),
        (
            "{urn:test}CostiProduzioneAmmortamentiSvalutazioni"
            "SvalutazioniCreditiCompresiAttivoCircolanteDisponibilitaLiquide"
        ): Decimal("150000"),
        (
            "{urn:test}CostiProduzioneAmmortamentiSvalutazioni"
            "AltreSvalutazioniImmobilizzazioni"
        ): Decimal("72895"),
    }

    _, ce, _ = parser.map_facts_to_fields_with_reconciliation(facts)

    assert ce["ce11b_altri_accantonamenti"] == Decimal("4005000")
    assert ce["ce09d_svalutazione_crediti"] == Decimal("150000")
    assert ce["ce09c_svalutazioni"] == Decimal("72895")


def test_xbrl_maps_combined_inventory_and_contract_work_variation_to_a2():
    parser = EnhancedXBRLParser(db_session=_session())
    facts = {
        (
            "{urn:test}ValoreProduzioneVariazioniRimanenzeProdottiCorso"
            "LavorazioneSemilavoratiFinitiLavoriCorsoOrdinazione"
        ): Decimal("-55931")
    }

    _, ce, _ = parser.map_facts_to_fields_with_reconciliation(facts)

    assert ce["ce02_variazioni_rimanenze"] == Decimal("-55931")


def test_xbrl_derives_missing_maturity_only_from_published_total_and_details():
    parser = EnhancedXBRLParser(db_session=_session())
    facts = {
        "{urn:test}TotaleCrediti": Decimal("300"),
        "{urn:test}PatrimonioNettoCapitale": Decimal("300"),
        (
            "{urn:test}TotaleCreditiIscrittiAttivoCircolante"
            "QuotaScadenteEntroEsercizio"
        ): Decimal("190"),
        (
            "{urn:test}TotaleCreditiIscrittiAttivoCircolante"
            "QuotaScadenteOltreEsercizio"
        ): Decimal("100"),
        "{urn:test}CreditiVersoClientiEsigibiliEntroEsercizioSuccessivo": Decimal("200"),
        "{urn:test}CreditiVersoClientiEsigibiliOltreEsercizioSuccessivo": Decimal("100"),
    }

    bs, _, info = parser.map_facts_to_fields_with_reconciliation(facts)

    assert bs["sp06_crediti_breve"] == Decimal("200")
    assert bs["sp07_crediti_lungo"] == Decimal("100")
    assert info["source_derivations"]["sp06_crediti_breve"]["formula"] == (
        "total_crediti - sp07_crediti_lungo"
    )
    assert info["reconciliation_adjustments"] == {}


def test_xbrl_adds_an_explicit_detail_omitted_from_published_maturity_subtotal():
    parser = EnhancedXBRLParser(db_session=_session())
    facts = {
        "{urn:test}TotaleAttivo": Decimal("300"),
        "{urn:test}TotalePassivo": Decimal("300"),
        "{urn:test}TotaleCrediti": Decimal("300"),
        "{urn:test}PatrimonioNettoCapitale": Decimal("300"),
        (
            "{urn:test}TotaleCreditiIscrittiAttivoCircolante"
            "QuotaScadenteEntroEsercizio"
        ): Decimal("290"),
        "{urn:test}CreditiImposteAnticipateTotaleImposteAnticipate": Decimal("10"),
    }

    bs, _, info = parser.map_facts_to_fields_with_reconciliation(facts)

    assert bs["sp06_crediti_breve"] == Decimal("300")
    assert bs["sp06f_imposte_anticipate_breve"] == Decimal("10")
    assert info["source_derivations"]["sp06_crediti_breve"]["published_total"] == 300.0
    assert info["reconciliation_adjustments"] == {}
