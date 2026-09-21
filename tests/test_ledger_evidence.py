"""Disjoint source facts, semantic constraints and independent cent controls."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from importers import ledger_evidence as le
from importers.detail_enrichment import SourceRow, DetailReadError, collect_source_rows
from importers.iv_cee_hierarchy import check_quadratura


def row(code, caption, amount, statement='bs', side='L', identifier=None):
    value = D(amount)
    return SourceRow(identifier or statement+side+code, 1, side,
                     f'{code} {caption} ' + f'{value:.2f}'.replace('.', ','),
                     (value,), code=code, statement=statement)


def rows():
    accounts = [
        row('01', 'RIMANENZE', '20'), row('01.01', 'PRODOTTI FINITI', '12'),
        row('02', 'CLIENTI', '40'), row('02.01', 'CLIENTE UNO', '40'),
        row('03', 'CASSA', '60'), row('03.01', 'CASSA CONTANTI', '60'),
        row('04', 'CAPITALE SOCIALE', '70', side='R'),
        row('04.01', 'CAPITALE SOCIALE', '70', side='R'),
        row('05', 'FORNITORI', '30', side='R'),
        row('05.01', 'FORNITORE UNO', '30', side='R'),
        row('06', 'SERVIZI', '20', statement='ce'),
        row('06.01', 'SERVIZI', '20', statement='ce'),
        row('07', 'RICAVI VENDITE', '40', statement='ce', side='R'),
        row('07.01', 'VENDITE', '40', statement='ce', side='R'),
    ]
    for statement, side, label, value in [
        ('bs', 'L', 'TOTALE ATTIVITA', '120'), ('bs', 'R', 'TOTALE PASSIVITA', '100'),
        ('bs', 'R', 'UTILE ESERCIZIO', '20'), ('ce', 'L', 'TOTALE COSTI', '20'),
        ('ce', 'R', 'TOTALE RICAVI', '40'), ('ce', 'L', 'UTILE ESERCIZIO', '20')]:
        accounts.append(row('', label, value, statement, side, statement+label))
    return accounts


def assignments(frontier):
    fields = {'01': 'sp05d_prodotti_finiti', '01.01': 'sp05d_prodotti_finiti',
              '02.01': 'sp06a_crediti_clienti_breve', '03.01': 'sp09_disponibilita_liquide',
              '04.01': 'sp11_capitale', '05.01': 'sp16d_debiti_fornitori_breve',
              '06.01': 'ce06_servizi', '07.01': 'ce01_ricavi_vendite'}
    return [le.AccountAssignment(row=r.id, field=fields[r.code], basis='caption') for r, _ in frontier]


def test_partial_children_leave_exact_residual_never_count_parent_twice():
    frontier, audit = le.prepare_ledger(rows())
    assert audit['status'] == 'ready'
    assert len(frontier) == 8
    assert audit['residuals'][0]['residual'] == '8'
    bs, ce, report = le.reduce_accounts(frontier, assignments(frontier), audit)
    assert bs['sp05_rimanenze'] == 20
    assert bs['sp05a_materie_prime'] == 8
    assert bs['sp05d_prodotti_finiti'] == 12
    assert bs['totale_attivo'] == bs['totale_passivo'] == 120
    assert check_quadratura(bs, ce).semantic_valid
    assert report['accounts_classified'] == 8


def test_inconsistent_children_retain_parent_without_negative_residual():
    source = [replace(r, amounts=(D('21'),)) if r.code == '01.01' else r for r in rows()]
    frontier, audit = le.prepare_ledger(source)
    assert audit['status'] == 'ready' and not audit['residuals']
    assert any(r.code == '01' and r.amounts == (D(20),) for r, _ in frontier)
    assert not any(r.code == '01.01' for r, _ in frontier)


def test_repeated_account_carry_forward_is_not_spent_twice():
    source = rows()
    frontier, audit = le.prepare_ledger(source + [replace(source[3], id='page2')])
    assert audit['status'] == 'ready'
    assert sum(r.amounts[-1] for r, _ in frontier if r.code == '02.01') == 40


def test_repeated_code_parties_require_exact_sum():
    source = rows() + [row('02.01', 'CLIENTE A', '15', identifier='a'),
                       row('02.01', 'CLIENTE B', '25', identifier='b')]
    assert le.prepare_ledger(source)[1]['status'] == 'ready'
    source[-1] = replace(source[-1], amounts=(D(24),))
    assert le.prepare_ledger(source)[0] is None


def test_unvalued_loan_identifier_is_not_a_monetary_fact():
    source = rows() + [replace(row('05.99', 'MUTUO NUMERO', '4793013', side='R'),
                              text='05.99 MUTUO NUMERO 4793013')]
    frontier, audit = le.prepare_ledger(source)
    assert audit['status'] == 'ready'
    assert not any(r.code == '05.99' for r, _ in frontier)


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'cross_statement'])
def test_invalid_llm_assignment_never_becomes_a_candidate(damage):
    frontier, audit = le.prepare_ledger(rows())
    reading = assignments(frontier)
    if damage == 'missing':
        reading.pop()
    elif damage == 'duplicate':
        reading.append(reading[0])
    else:
        reading[0].field = 'ce06_servizi'
    with pytest.raises(DetailReadError):
        le.reduce_accounts(frontier, reading, audit)


def test_source_profit_disagreement_is_preserved_and_requires_review():
    source = [replace(r, amounts=(D('21'),)) if r.id == 'bsUTILE ESERCIZIO' else
              replace(r, amounts=(D('99'),)) if r.id == 'bsTOTALE PASSIVITA' else
              replace(r, amounts=(D('69'),)) if r.code.startswith('04') else r for r in rows()]
    frontier, audit = le.prepare_ledger(source)
    bs, ce, report = le.reduce_accounts(frontier, assignments(frontier), audit)
    assert bs['sp13_utile_perdita'] == 21
    assert le._net_profit_from_ce(ce) == 20
    assert report['requires_review'] and report['income_verified']


def test_reader_failure_is_a_review_reason_not_silent_success(monkeypatch):
    monkeypatch.setattr(le, 'collect_source_rows', lambda p: rows())
    def fail(frontier):
        raise TimeoutError('test')
    bs, ce, report = le.extract_ledger_source('unused.pdf', reader=fail)
    assert bs is ce is None
    assert report['requires_review'] and report['errors'] == ['TimeoutError']


def test_reader_repairs_only_missing_or_ambiguous_accounts(monkeypatch):
    import anthropic
    import json
    from types import SimpleNamespace as NS
    frontier, _ = le.prepare_ledger(rows())
    expected = {a.row: a.model_dump() for a in assignments(frontier)}
    requests = []
    def create(**kwargs):
        ids = [c['id'] for c in json.loads(kwargs['messages'][0]['content'])['accounts']]
        requests.append(ids)
        if len(requests) == 1:
            # One valid row, one duplicated/ambiguous row, everything else missing.
            data = [expected[ids[0]], expected[ids[1]], expected[ids[1]]]
        else:
            data = [expected[i] for i in ids]
        return NS(stop_reason='tool_use', content=[NS(type='tool_use', name='classifica_conti',
                                                      input={'accounts': data})])
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: NS(messages=NS(create=create)))
    result = le.read_accounts(frontier)
    assert [a.row for a in result] == [r.id for r, _ in frontier]
    assert len(requests) == 2
    assert requests[0][0] not in requests[1]
    assert requests[0][1] in requests[1]


def test_reader_does_not_invent_accounts_after_exhausted_repairs(monkeypatch):
    import anthropic
    from types import SimpleNamespace as NS
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return NS(stop_reason='tool_use', content=[NS(type='tool_use', name='classifica_conti',
                                                      input={'accounts': []})])
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: NS(messages=NS(create=create)))
    frontier, _ = le.prepare_ledger(rows())
    with pytest.raises(DetailReadError, match='ledger_incomplete_assignments'):
        le.read_accounts(frontier)
    assert len(calls) == 3


def test_missing_reader_marks_supported_ledger_for_review(monkeypatch):
    monkeypatch.setattr(le, 'collect_source_rows', lambda p: rows())
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert le.extract_ledger_source('unused.pdf')[2]['requires_review']


@pytest.mark.parametrize('caption,side,proposed,expected,ancestors', [
    ('AMMINISTRATORI C/COMPENSI', 'R', 'sp16a_debiti_banche_breve', 'sp16g_altri_debiti_breve', []),
    ('SINDACATI C/RITENUTE', 'R', 'sp16e_debiti_tributari_breve', 'sp16g_altri_debiti_breve', []),
    ('BANCA C/C', 'R', 'sp09_disponibilita_liquide', 'sp16a_debiti_banche_breve', []),
    ('FINANZIAMENTO SOCIO MARIO', 'R', 'sp16a_debiti_banche_breve', 'sp17b_debiti_altri_finanz_lungo', []),
    ('BANCA SOCIETA XYZ FINANZIAMENTO', 'R', 'sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo', []),
    ('MUTUO BANCA', 'R', 'sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo', []),
    ('MUTUO BANCA ENTRO 12 MESI', 'R', 'sp17a_debiti_banche_lungo', 'sp16a_debiti_banche_breve', []),
    ('BANCA C/ANTICIPAZIONI', 'R', 'sp17a_debiti_banche_lungo', 'sp16a_debiti_banche_breve', ['MUTUI BANCARI']),
    ('BANCA C/C', 'R', 'sp17a_debiti_banche_lungo', 'sp16a_debiti_banche_breve', ['MUTUI BANCARI']),
    ('INTERESSI BANCARI MATURATI', 'R', 'sp17a_debiti_banche_lungo', 'sp16a_debiti_banche_breve', ['MUTUI BANCARI']),
    ('CRED.DIV.ESIG.OLTRE ES.SUCC.', 'L', 'sp06a_crediti_clienti_breve', 'sp07g_crediti_altri_lungo', []),
    ('FORNITORI', 'L', 'sp16d_debiti_fornitori_breve', 'sp06g_crediti_altri_breve', []),
    ('DEBITI V/FORNITORI', 'L', 'sp07d_crediti_controllanti_lungo', 'sp06g_crediti_altri_breve', []),
    ('CREDITO XYZ SRL', 'L', 'sp06b_crediti_controllate_breve', 'sp06g_crediti_altri_breve', []),
    ('SOCI C/RIMBORSI', 'L', 'sp17b_debiti_altri_finanz_lungo', 'sp06g_crediti_altri_breve', []),
    ('CLIENTI', 'L', 'sp07a_crediti_clienti_lungo', 'sp06a_crediti_clienti_breve', []),
])
def test_source_side_nature_and_maturity_constrain_llm(caption, side, proposed, expected, ancestors):
    assert le.account_contract(row('01.01', caption, '10', side=side), ancestors, proposed)[0] == expected


def test_funds_cannot_become_generic_debt():
    with pytest.raises(DetailReadError, match='ledger_contra_not_linked_to_asset'):
        le.account_contract(row('01.01', 'FONDO AMMORTAMENTO IMPIANTI', '10', side='R'),
                            [], 'sp16g_altri_debiti_breve')


def test_nonfinancial_asset_sale_is_in_operating_other_income():
    account = row('53.01.92', 'Plusvalenza da alienazione cespiti', '19391.35', statement='ce', side='R')
    assert le.account_contract(account, [], 'ce18_proventi_straordinari')[0] == 'ce04_altri_ricavi'


@pytest.mark.parametrize('caption', ['Pedaggi autostradali veicoli', 'Servizio di vigilanza'])
def test_documented_services_are_not_generic_other_expenses(caption):
    account = row('63.01', caption, '10', statement='ce')
    assert le.account_contract(account, [], 'ce12_oneri_diversi')[0] == 'ce06_servizi'


def test_explicit_other_provisions_are_not_risk_provisions():
    account = row('69.03', 'Accantonamento altri fondi e spese', '10', statement='ce')
    assert le.account_contract(account, [], 'ce11_accantonamenti')[0] == 'ce11b_altri_accantonamenti'


def test_profit_tolerance_never_scales_with_asset_size():
    bs = {'sp09_disponibilita_liquide': D('2584168.34'), 'sp11_capitale': D('2536264.53'),
          'sp13_utile_perdita': D('47903.81'), 'totale_attivo': D('2584168.34'),
          'totale_passivo': D('2584168.34')}
    q = check_quadratura(bs, {'ce01_ricavi_vendite': D('48649.70')}, tol=D(2))
    assert not q.semantic_valid


CORPUS = Path(__file__).resolve().parents[1] / 'inbox' / 'check-budget1'


@pytest.mark.parametrize('code', ['948', '949', '972'])
def test_real_disjoint_account_frontier_equals_each_of_four_printed_totals(code):
    paths = list(CORPUS.glob(f'budget_{code}_*.pdf'))
    if not paths:
        pytest.skip('private regression PDF not present')
    source = collect_source_rows(paths[0])
    frontier, audit = le.prepare_ledger(source)
    assert frontier and audit['status'] == 'ready' and not audit['errors']
    assert not any(r.code and '/' in r.code and len(r.code) == 10 for r, _ in frontier)
    assert len(frontier) == len({r.id for r, _ in frontier})


def test_liabilities_footer_excluding_profit_is_not_a_source_imbalance():
    from importers.pdf_importer import _classify_balance_failure
    paths = list(CORPUS.glob('budget_972_*.pdf'))
    if not paths:
        pytest.skip('private regression PDF not present')
    verdict = _classify_balance_failure({'totale_attivo': D(10)},
        is_scanned=False, ocr_source=False, is_trial_balance=True,
        sample_text='', file_path=str(paths[0]), ocr_text=None)
    assert 'componenti patrimoniali estratte' in verdict.warning
