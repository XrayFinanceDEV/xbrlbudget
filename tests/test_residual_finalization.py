"""Mandatory closure is independent of LLM proposals and cannot balance SP/CE."""
from copy import deepcopy
from decimal import Decimal as D
import json
from pathlib import Path

import fitz
import pytest

from importers.iv_cee_hierarchy import aggregates_with_details, detail_fields, check_quadratura
from importers.residual_finalization import finalize_pdf_residuals

INV = 'sp05_rimanenze'
RAW = 'sp05a_materie_prime'
GOODS = 'sp05d_prodotti_finiti'
CREDIT = 'sp06_crediti_breve'
CLIENTS = 'sp06a_crediti_clienti_breve'
OTHER = 'sp06g_crediti_altri_breve'
DEBT = 'sp16_debiti_breve'
BANK = 'sp16a_debiti_banche_breve'
MISC_DEBT = 'sp16g_altri_debiti_breve'


@pytest.mark.parametrize('aggregate', aggregates_with_details())
@pytest.mark.parametrize('partial', [False, True])
def test_all_additive_families_close_exactly_without_changing_parents(aggregate, partial):
    statement = {aggregate: D('100.01')}
    fields = detail_fields(aggregate)
    if partial:
        statement[fields[0]] = D('60')
    bs, ce = (statement, {}) if aggregate.startswith('sp') else ({}, statement)
    old_bs, old_ce = deepcopy(bs), deepcopy(ce)
    new_bs, new_ce, report = finalize_pdf_residuals(bs, ce)
    actual = new_bs if aggregate.startswith('sp') else new_ce
    assert actual[aggregate] == D('100.01')
    assert sum((actual.get(f, D(0)) for f in fields), D(0)) == D('100.01')
    assert bs == old_bs and ce == old_ce
    assert not report['requires_review']
    twice_bs, twice_ce, twice_report = finalize_pdf_residuals(new_bs, new_ce)
    assert (twice_bs, twice_ce) == (new_bs, new_ce)
    assert twice_report['families'][aggregate]['allocated'] == '0'
    json.dumps(report)


def test_default_buckets_and_existing_generic_residual_are_explicit():
    bs, _, report = finalize_pdf_residuals({INV: D(100), CREDIT: D(200), DEBT: D(100), BANK: D(60), MISC_DEBT: D(10)})
    assert bs[RAW] == 100 and bs[CLIENTS] == 200
    assert bs[BANK] == 60 and bs[MISC_DEBT] == 40
    assert report['families'][DEBT]['allocated'] == '30'
    assert report['families'][DEBT]['basis'] == 'conventional_residual_not_source_detail'


def test_one_cent_is_closed_and_signed_offsets_do_not_mean_absent_detail():
    bs, _, _ = finalize_pdf_residuals({CREDIT: D('0.01'), CLIENTS: D(5), OTHER: D(-5)})
    assert bs[CLIENTS] == 5 and bs[OTHER] == D('-4.99')


@pytest.mark.parametrize('total,detail', [('100', '100.01'), ('100', '120'), ('0', '10')])
def test_excess_is_not_hidden_in_negative_other_or_changed_parent(total, detail):
    original = {CREDIT: D(total), CLIENTS: D(detail), DEBT: D(50)}
    bs, _, report = finalize_pdf_residuals(original)
    assert bs[CREDIT] == original[CREDIT] and bs[CLIENTS] == original[CLIENTS]
    assert OTHER not in bs
    assert bs[MISC_DEBT] == 50  # independent valid family still completed
    assert report['requires_review'] and report['families'][CREDIT]['status'] == 'conflict'


def test_orphan_details_are_not_treated_as_proof_of_a_parent():
    bs, _, report = finalize_pdf_residuals({CLIENTS: D(50)})
    assert bs == {CLIENTS: D(50)} and report['requires_review']
    assert report['families'][CREDIT]['aggregate'] is None


def test_negative_aggregate_without_details_is_carried_but_partial_signed_gap_is_flagged():
    bs, _, report = finalize_pdf_residuals({'sp12_riserve': D('-50')})
    assert bs['sp12e_altre_riserve'] == -50 and not report['requires_review']
    partial = {'sp12_riserve': D('-50'), 'sp12g_utili_perdite_portati': D('-30')}
    bs, _, report = finalize_pdf_residuals(partial)
    assert bs == partial and report['requires_review']


def test_no_cross_family_maturity_or_ce_sp_compensations_or_proportions():
    bs = {INV: D(100), 'sp11_capitale': D(95), 'sp13_utile_perdita': D(3),
          'sp02_immob_immateriali': D(30), 'sp03_immob_materiali': D(70),
          'sp17_debiti_lungo': D(20)}
    ce = {'ce01_ricavi_vendite': D(100), 'ce08_costi_personale': D(20), 'ce09_ammortamenti': D(10),
          'ce17_rettifiche_attivita_fin': D(5)}
    before = check_quadratura(bs, ce)
    new_bs, new_ce, _ = finalize_pdf_residuals(bs, ce)
    after = check_quadratura(new_bs, new_ce)
    assert before.sbilancio == after.sbilancio and before.utile_ce == after.utile_ce
    assert new_bs['sp17_debiti_lungo'] == 20 and 'sp16_debiti_breve' not in new_bs
    assert 'sp09_disponibilita_liquide' not in new_bs
    assert new_ce['ce08d_altri_costi_personale'] == 20
    assert 'ce08a_tfr_accrual' not in new_ce
    assert new_ce['ce09c_svalutazioni'] == 10  # explicitly conventional UI bucket
    assert 'ce09a_ammort_immateriali' not in new_ce and 'ce09b_ammort_materiali' not in new_ce
    assert 'ce17a_rivalutazioni' not in new_ce  # non-additive family untouched


@pytest.fixture
def import_fixture(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base
    from importers import pdf_importer as importer, pdf_extractor_llm as extractor
    from importers import standard_ivcee_parser as standard, bilancio_classifier as classifier, source_reconciliation as source

    path = tmp_path / 'residuals.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 50), 'Stato patrimoniale Attivo 2025 2024 - prova residui')
        page.insert_text((40, 70), 'Merci 30,00 20,00')
        doc.save(path)
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(importer, 'SessionLocal', sessions)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-not-used')
    monkeypatch.setattr(classifier, 'classify_bilancio', lambda **kw: classifier.Classification(
        'A', 'synthetic', classifier.ROUTE_IVCEE, 'test', 'high', {}, 'test'))
    monkeypatch.setattr(source, 'extract_source_candidates', lambda *a: [])
    monkeypatch.setattr(standard, 'extract_standard_ivcee_balances', lambda *a: (None, None))
    current = {INV: D(100), CREDIT: D(200), 'sp11_capitale': D(300),
               'totale_attivo': D(300), 'totale_passivo': D(300)}
    prior = {INV: D(60), CREDIT: D(120), 'sp11_capitale': D(180),
             'totale_attivo': D(180), 'totale_passivo': D(180)}
    ce = {'ce01_ricavi_vendite': D(50), 'ce08_costi_personale': D(50)}
    monkeypatch.setattr(extractor, 'extract_pdf_with_llm', lambda *a, **kw: (dict(current), dict(ce)))
    monkeypatch.setattr(extractor, 'extract_pdf_both_years_with_llm', lambda *a, **kw: (
        dict(current), dict(ce), dict(prior), dict(ce)))
    from importers import macro_analysis
    monkeypatch.setattr(macro_analysis, 'analyze_pdf_macros', lambda *a, **kw: (
        dict(current), dict(ce), dict(prior), dict(ce),
        {'status': 'verified', 'income_verified': True,
         'prior': {'status': 'verified', 'income_verified': True}}))
    yield importer, sessions, path, current, prior
    engine.dispose()


@pytest.mark.parametrize('reader', ['disabled', 'empty', 'timeout', 'rejected', 'no_cells', 'partial'])
def test_real_pipeline_always_persists_residuals_for_both_years(import_fixture, monkeypatch, reader):
    from database.models import FinancialYear
    from importers import detail_enrichment as de
    importer, sessions, path, current, prior = import_fixture
    if reader == 'disabled':
        monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
        monkeypatch.setattr(de, 'read_details', lambda *a: pytest.fail('disabled reader called'))
    elif reader == 'no_cells':
        monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: [])
        monkeypatch.setattr(de, 'read_details', lambda *a: pytest.fail('empty document reader called'))
    else:
        def read(rows, *args):
            if reader == 'timeout':
                raise TimeoutError('simulated unavailable LLM')
            if reader == 'empty':
                return de.DetailReading()
            row = next(r for r in rows if r.text.startswith('Merci'))
            return de.DetailReading(proposals=[de.DetailProposal(period=period, aggregate=INV, items=[
                de.DetailCell(field=GOODS, row=row.id if reader == 'partial' else 'nonexistent', column=col)])
                for period, col in [('current', 0), ('prior', 1)]])
        monkeypatch.setattr(de, 'read_details', read)
    result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Residual closure')
    assert result['success'] and result['prior_year_imported'] and result['forecastable']
    with sessions() as db:
        years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
        assert len(years) == 2
        for fy, inv, credit, goods in zip(years, [100, 60], [200, 120], [30, 20]):
            assert fy.balance_sheet.sp05_rimanenze == inv
            assert fy.balance_sheet.sp05a_materie_prime == (inv - goods if reader == 'partial' else inv)
            assert fy.balance_sheet.sp06a_crediti_clienti_breve == credit
            assert fy.income_statement.ce08d_altri_costi_personale == 50
            assert fy.forecastable
            report = json.loads(fy.validation_report)['residual_finalization']
            assert report['status'] == 'completed'
            assert report['families'][CREDIT]['allocated'] == str(credit)
        monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
        from app.api.v1 import financial_years as endpoint
        from app.schemas.adjustments import AdjustmentsUpdate
        monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
        original_audit = json.loads(years[0].validation_report)['residual_finalization']
        endpoint.save_adjustments(company_id=result['company_id'], year=2025, period_months=None,
                                  payload=AdjustmentsUpdate(balance_sheet={}, income_statement={}), user_id='test', db=db)
        db.refresh(years[0])
        assert json.loads(years[0].validation_report)['residual_finalization'] == original_audit


def test_one_cent_excess_is_persisted_flagged_and_only_real_correction_clears_gate(import_fixture, monkeypatch):
    from database.models import FinancialYear
    importer, sessions, path, current, prior = import_fixture
    current[CLIENTS] = D('200.01')
    prior[CLIENTS] = D('120.01')
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Conflicting residual')
    assert result['success'] and not result['forecastable'] and result['prior_year_imported']
    assert result['validation_status'] == 'review_required'
    with sessions() as db:
        years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
        assert all(not y.forecastable and y.validation_status == 'review_required' for y in years)
        fy = years[0]
        assert fy.balance_sheet.sp06a_crediti_clienti_breve == D('200.01')
        assert fy.balance_sheet.sp06g_crediti_altri_breve == 0
        audit = json.loads(fy.validation_report)['residual_finalization']
        assert audit['requires_review']
        monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
        from app.api.v1 import financial_years as endpoint
        from app.schemas.adjustments import AdjustmentsUpdate
        monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
        for edits, expected in [({}, False), ({CLIENTS: 200}, True)]:
            endpoint.save_adjustments(company_id=result['company_id'], year=2025, period_months=None,
                                      payload=AdjustmentsUpdate(balance_sheet=edits, income_statement={}), user_id='test', db=db)
            db.refresh(fy)
            assert fy.forecastable is expected
            assert json.loads(fy.validation_report)['residual_finalization'] == audit


@pytest.mark.parametrize('reason', ['missing macro/control: ce09_ammortamenti',
                                   'macro_reader_failed:ValidationError'])
def test_incomplete_macros_import_with_other_debt_residuals(import_fixture, monkeypatch, reason):
    from database.models import FinancialYear
    from importers import macro_analysis, standard_ivcee_parser
    importer, sessions, path, current, prior = import_fixture
    for data in (current, prior):
        data['sp11_capitale'] -= D(50)
        data[DEBT] = D(50)
        data[BANK] = D(20)
    def incomplete(*args, **kwargs):
        raise macro_analysis.MacroAnalysisError({'status': 'incomplete', 'errors': [reason]})
    monkeypatch.setattr(macro_analysis, 'analyze_pdf_macros', incomplete)
    monkeypatch.setattr(standard_ivcee_parser, 'has_comparative_ivcee_columns', lambda *a: True)
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Macro fallback')
    assert result['success'] and result['prior_year_imported']
    assert any('MACROVOCI DA VERIFICARE' in w for w in result['warnings'])
    with sessions() as db:
        years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
        assert len(years) == 2
        for year in years:
            assert year.balance_sheet.sp16_debiti_breve == 50
            assert year.balance_sheet.sp16a_debiti_banche_breve == 20
            assert year.balance_sheet.sp16g_altri_debiti_breve == 30
        audit = json.loads(years[0].validation_report)
        assert audit['macro_analysis']['fallback_used']
        assert audit['macro_analysis']['status'] == 'incomplete'
        assert audit['source_reconciliation'].get('status') != 'verified'
        assert audit['residual_finalization']['families'][DEBT]['allocated'] == '30'


def test_conflicting_comparative_never_replaces_previously_valid_prior(import_fixture, monkeypatch):
    from database.models import FinancialYear
    importer, sessions, path, current, prior = import_fixture
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Preserve valid prior')
    with sessions() as db:
        old = db.query(FinancialYear).filter_by(year=2024).one()
        old_id, old_audit = old.id, old.validation_report
    prior[CLIENTS] = D('120.01')
    again = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_id=result['company_id'])
    assert again['success'] and any('ANNO PRECEDENTE NON IMPORTATO' in w for w in again['warnings'])
    with sessions() as db:
        kept = db.query(FinancialYear).filter_by(year=2024).one()
        assert kept.id == old_id and kept.validation_report == old_audit and kept.forecastable
        assert kept.balance_sheet.sp06a_crediti_clienti_breve == 120
