"""Source proofs can correct a balanced hypothesis; balance alone is not proof."""
from decimal import Decimal as D
from pathlib import Path

import fitz
import pytest

from importers import source_reconciliation as sr
from importers.detail_enrichment import SourceRow, collect_source_rows
from importers.iv_cee_hierarchy import check_quadratura
from importers.standard_ivcee_parser import has_comparative_ivcee_columns


def legal_rows():
    labels = [
        ('Stato patrimoniale attivo', None),
        ('Totale immobilizzazioni (B)', '0.00'),
        ('I - Rimanenze', None), ('4) prodotti finiti e merci', '60.00'),
        ('Totale rimanenze', '60.00'), ('II - Crediti', None),
        ('1) verso clienti', None), ('esigibili entro', '45.00'),
        ('5-quater) verso altri', None), ('esigibili entro', '-5.00'),
        ('Totale crediti', '40.00'), ('Totale attivo circolante (C)', '100.00'),
        ('Totale attivo', '100.00'), ('Stato patrimoniale passivo', None),
        ('A) Patrimonio netto', None), ('I - Capitale', '20.00'),
        ("IX Utile (perdita) dell'esercizio", '10.00'), ('Totale patrimonio netto', '30.00'),
        ('D) Debiti', None), ('7) verso fornitori', None), ('esigibili entro', '70.00'),
        ('Totale debiti', '70.00'), ('Totale passivo', '100.00'),
        ('Conto economico', None), ('1) ricavi', '10.00'),
        ('Totale valore della produzione', '10.00'), ('Totale costi della produzione', '0.00'),
        ('Risultato prima delle imposte', '10.00'), ("Utile (perdita) dell'esercizio", '10.00'),
    ]
    return [SourceRow(str(i), 1, 'T', label, () if v is None else (D(v),),
                      positions=() if v is None else (420,)) for i, (label, v) in enumerate(labels)]


def test_legal_partition_preserves_negative_credits_and_checks_every_control():
    bs, ce, report = sr._read_column(legal_rows(), 0, None)
    assert report['status'] == 'verified' and report['tolerance'] == '0.01'
    assert bs['sp05d_prodotti_finiti'] == 60
    assert bs['sp06a_crediti_clienti_breve'] == 45
    assert bs['sp06g_crediti_altri_breve'] == -5
    assert check_quadratura(bs, ce).semantic_valid


@pytest.mark.parametrize('label', ['Totale crediti', 'Totale immobilizzazioni (B)', 'Totale passivo'])
def test_missing_independent_control_declines_without_plug(label):
    rows = [r for r in legal_rows() if r.text != label]
    bs, ce, report = sr._read_column(rows, 0, None)
    assert bs is ce is None and report['status'] == 'declined'


def test_cent_based_statement_does_not_tolerate_euro_sized_missing_detail():
    from dataclasses import replace
    rows = [replace(r, amounts=(D('43.50'),)) if r.text == 'esigibili entro' and r.amounts == (D('45'),) else r
            for r in legal_rows()]
    assert sr._read_column(rows, 0, None)[0] is None


def test_source_can_correct_balanced_macro_and_specific_fields_and_drop_stale_flags():
    source_bs, ce, audit = sr._read_column(legal_rows(), 0, None)
    old = dict(source_bs, sp05_rimanenze=D('0'), sp05d_prodotti_finiti=D('0'),
               sp06_crediti_breve=D('100'), sp06a_crediti_clienti_breve=D('105'),
               _plug_residual=D('50'))
    assert old['totale_attivo'] == old['totale_passivo']
    new, _, report = sr.apply_source_candidate(old, ce, (source_bs, ce, audit))
    assert new['sp05_rimanenze'] == 60 and new['sp06a_crediti_clienti_breve'] == 45
    assert '_plug_residual' not in new and old['_plug_residual'] == 50
    assert report['changes']['sp06_crediti_breve'] == {'before': '100', 'after': '40.00'}


def test_unproved_source_never_replaces_extraction():
    bs, ce = {'sp06_crediti_breve': D('10')}, {'ce01_ricavi_vendite': D('5')}
    actual_bs, actual_ce, _ = sr.apply_source_candidate(bs, ce, (None, None, {'status': 'declined'}))
    assert actual_bs == bs and actual_ce == ce


def test_prior_only_cell_does_not_become_current_value():
    from dataclasses import replace
    rows = [replace(r, positions=(520,)) if r.amounts else r for r in legal_rows()]
    assert sr._read_column(rows, 0, 480)[0] is None
    assert sr._read_column(rows, 1, 480)[0]['totale_attivo'] == 100


def test_hyphen_dates_and_separate_negative_parenthesis(tmp_path):
    path = tmp_path / 'columns.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((400, 50), '31-12-2025', fontsize=8)
        page.insert_text((500, 50), '31-12-2024', fontsize=8)
        page.insert_text((400, 70), '( 152.249)', fontsize=8)
        doc.save(path)
    assert has_comparative_ivcee_columns(path)
    assert any(r.amounts == (D('-152249'),) for r in collect_source_rows(path))


CORPUS = Path(__file__).resolve().parents[1] / 'inbox' / 'riptova'


def pdf(code):
    paths = list(CORPUS.glob(f'budget_{code}_*.pdf'))
    if not paths:
        pytest.skip('private regression PDF not present')
    return paths[0]


@pytest.mark.parametrize('code', ['623', '636', '637', '682'])
def test_real_statements_crossfoot_without_llm_and_keep_typed_hierarchy(code):
    for bs, ce, report in sr.extract_source_candidates(pdf(code)):
        assert report['status'] == 'verified' and report['income_verified']
        assert check_quadratura(bs, ce, tol=D('2')).semantic_valid


def test_ago_does_not_turn_inventory_or_prior_losses_into_receivables():
    bs, ce, _ = sr.extract_ago_source(pdf('623'))
    assert bs['sp05_rimanenze'] == D('1405556.94')
    assert bs['sp12g_utili_perdite_portati'] == D('-122614.63')
    assert bs['sp11_capitale'] == D('51480')  # c/capitale reserve is NOT capital
    assert bs['sp12e_altre_riserve'] == D('160211.27')
    assert ce['ce10_var_rimanenze_mat_prime'] == D('63442.30')


def test_analytic_pass_cannot_demote_source_proved_long_debts_on_type_conflict(monkeypatch):
    from importers.detail_enrichment import enrich_pdf_details
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    path = pdf('623')
    bs, _, _ = sr.extract_ago_source(path)
    updated, _, report = enrich_pdf_details(path, bs)
    assert updated['sp17_debiti_lungo'] == D('1018268.52')
    assert updated['sp17b_debiti_altri_finanz_lungo'] == D('35000')
    assert updated['sp17g_altri_debiti_lungo'] == D('110063.12')
    assert updated['sp07f_imposte_anticipate_lungo'] == D('39852.12')
    assert report['periods']['current']['maturity']['source_debt_maturities_preserved']


def test_incomplete_ago_ce_never_fabricates_missing_costs():
    bs, ce, report = sr.extract_ago_source(pdf('624'))
    assert bs['sp05_rimanenze'] == D('1468999.24')
    assert ce is None and not report['income_verified'] and report['errors']


def test_pharma_common_control_is_not_controlling_company_and_prior_blank_stays_zero():
    current, prior = sr.extract_legal_source(pdf('682'))
    assert current[0]['sp06d_crediti_controllanti_breve'] == 938
    assert current[0]['sp06b_crediti_controllate_breve'] == 937202
    assert current[0]['sp06g_crediti_altri_breve'] == 154257
    assert prior[0]['sp07e_crediti_tributari_lungo'] == 173
    assert current[0]['sp07_crediti_lungo'] == 0


def test_trial_opening_imbalance_is_flagged_not_hidden_in_current_result():
    report = sr.inspect_signed_closing_controls(pdf('680'))
    assert report['status'] == 'source_conflict' and report['requires_review']
    assert report['controls']['profit'] == '140832.76'
    assert report['controls']['unreconciled'] == '-348287.23'


@pytest.mark.parametrize('requires_review', [False, True])
def test_source_proof_is_wired_to_import_persistence_and_manual_edit_gate(monkeypatch, tmp_path, requires_review):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base, FinancialYear
    from importers import pdf_importer as importer, bilancio_classifier as classifier
    from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

    path = tmp_path / 'source.pdf'
    _write_compact_infrannual_pdf(path)
    candidate = sr._read_column(legal_rows(), 0, None)
    candidate[2]['requires_review'] = requires_review
    monkeypatch.setattr(sr, 'extract_source_candidates', lambda *a: [candidate])
    monkeypatch.setattr(classifier, 'classify_bilancio', lambda **kw: classifier.Classification(
        'A', 'synthetic', classifier.ROUTE_IVCEE, 'test', 'high', {}, 'test'))
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(importer, 'SessionLocal', sessions)
    try:
        result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Source proof test')
        assert result['success'] and result['forecastable'] is not requires_review
        assert result['validation_report']['source_reconciliation']['requires_review'] is requires_review
        with sessions() as db:
            fy = db.query(FinancialYear).one()
            assert fy.balance_sheet.sp05_rimanenze == 60
            monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
            from app.api.v1 import financial_years as endpoint
            from app.schemas.adjustments import AdjustmentsUpdate
            monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
            endpoint.save_adjustments(
                company_id=result['company_id'], year=2025,
                payload=AdjustmentsUpdate(balance_sheet={}, income_statement={}),
                period_months=None, user_id='test', db=db)
            db.refresh(fy)
            assert fy.forecastable is not requires_review
            assert json.loads(fy.validation_report)['source_reconciliation']['requires_review'] is requires_review
    finally:
        engine.dispose()


def test_prior_source_review_cannot_be_cleared_by_small_rounding_tolerance(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base, FinancialYear
    from importers import pdf_importer as importer, bilancio_classifier as classifier
    from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

    path = tmp_path / 'comparative.pdf'
    _write_compact_infrannual_pdf(path)
    current = sr._read_column(legal_rows(), 0, None)
    prior = sr._read_column(legal_rows(), 0, None)
    prior[2]['requires_review'] = True
    prior[2]['errors'] = ['Printed source discrepancy, even if below legacy rounding tolerance']
    monkeypatch.setattr(sr, 'extract_source_candidates', lambda *a: [current, prior])
    monkeypatch.setattr(classifier, 'classify_bilancio', lambda **kw: classifier.Classification(
        'A', 'synthetic', classifier.ROUTE_IVCEE, 'test', 'high', {}, 'test'))
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(importer, 'SessionLocal', sessions)
    try:
        result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Prior review')
        assert result['success'] and result['prior_year_imported']
        with sessions() as db:
            years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
            assert [y.year for y in years] == [2025, 2024]
            assert years[0].forecastable and not years[1].forecastable
            assert years[1].validation_status == 'review_required'
    finally:
        engine.dispose()
