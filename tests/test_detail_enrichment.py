"""Analytical extraction must recover facts without spending the parent twice."""
from decimal import Decimal as D
import json
from pathlib import Path

import fitz
import pytest

from importers import detail_enrichment as de
from importers.iv_cee_hierarchy import detail_fields


INBOX = Path(__file__).resolve().parents[1] / "inbox" / "import-test"
INV = "sp05_rimanenze"
RAW = "sp05a_materie_prime"
GOODS = "sp05d_prodotti_finiti"
WIP = "sp05c_lavori_in_corso"
DEBT = "sp16_debiti_breve"
OTHER = "sp16g_altri_debiti_breve"
BANK = "sp16a_debiti_banche_breve"
SUPPLIER = "sp16d_debiti_fornitori_breve"
CREDIT = "sp06_crediti_breve"
LONG_CREDIT = "sp07_crediti_lungo"
CLIENTS = "sp06a_crediti_clienti_breve"
TAX = "sp06e_crediti_tributari_breve"
DEFERRED = "sp06f_imposte_anticipate_breve"
OTHER_CREDIT = "sp06g_crediti_altri_breve"
LONG_TAX = "sp07e_crediti_tributari_lungo"


def row(id, amount, code="", text="documented detail"):
    return de.SourceRow(id, 1, "L", text, (D(amount),), code)


def proposal(aggregate, *cells, period="current"):
    return de.DetailProposal(period=period, aggregate=aggregate, items=[
        de.DetailCell(field=f, row=r, column=c) for f, r, c in cells
    ])


def test_partial_inventory_releases_initial_raw_bucket_and_keeps_exact_remainder():
    initial = {INV: D("231250.03"), RAW: D("231250.03")}
    rows = [row("goods", "170000"), row("wip", "40000"), row("raw", "21250")]
    p = proposal(INV, (GOODS, "goods", 0), (WIP, "wip", 0), (RAW, "raw", 0))
    actual, report = de.apply_details(initial, [p], rows)
    assert initial[RAW] == D("231250.03")
    assert actual[INV] == D("231250.03")
    assert actual[RAW] == D("21250.03")  # 3 cents stay in the original bucket
    assert actual[GOODS] == D("170000") and actual[WIP] == D("40000")
    assert report["families"][INV]["unresolved"] == "0.03"
    again, _ = de.apply_details(actual, [p], rows)
    assert again == actual


def test_partial_debt_does_not_require_whole_family_to_reconcile():
    p = proposal(DEBT, (BANK, "bank", 0), (SUPPLIER, "suppliers", 0))
    actual, report = de.apply_details({DEBT: D("100")}, [p], [row("bank", "25"), row("suppliers", "60")])
    assert actual[BANK] == 25 and actual[SUPPLIER] == 60 and actual[OTHER] == 15
    assert report["families"][DEBT]["unresolved"] == "15"


def test_conflicting_existing_specific_detail_is_preserved_but_other_detail_added():
    bs = {DEBT: D("100"), BANK: D("20"), OTHER: D("80")}
    p = proposal(DEBT, (BANK, "bank", 0), (SUPPLIER, "suppliers", 0))
    actual, report = de.apply_details(bs, [p], [row("bank", "25"), row("suppliers", "60")])
    assert actual[BANK] == 20 and actual[SUPPLIER] == 60 and actual[OTHER] == 20
    assert any("conflitto" in r["reason"] for r in report["rejected"])


def test_overfull_suggestion_is_not_scaled_and_does_not_discard_valid_sibling():
    p = proposal(DEBT, (BANK, "bank", 0), (SUPPLIER, "suppliers", 0))
    actual, report = de.apply_details({DEBT: D("100")}, [p], [row("bank", "120"), row("suppliers", "60")])
    assert actual.get(BANK, 0) == 0 and actual[SUPPLIER] == 60 and actual[OTHER] == 40
    assert report["rejected"]


@pytest.mark.parametrize("bad", [(SUPPLIER, "missing", 0), (SUPPLIER, "good", 4), ("sp13_utile_perdita", "good", 0)])
def test_invalid_reference_or_cross_family_target_cannot_change_totals(bad):
    bs = {DEBT: D("100"), "sp13_utile_perdita": D("30")}
    actual, report = de.apply_details(bs, [proposal(DEBT, bad)], [row("good", "50")])
    assert actual == bs
    assert report["rejected"]


def test_parent_child_and_duplicate_cells_cannot_be_spent_twice():
    rows = [row("parent", "80", "09.01"), row("child", "60", "09.01.03")]
    p = proposal(INV, (GOODS, "parent", 0), (GOODS, "parent", 0), (RAW, "child", 0))
    actual, report = de.apply_details({INV: D("100")}, [p], rows)
    assert actual[GOODS] == 80 and actual[RAW] == 20
    assert len(report["rejected"]) == 2


def test_negative_printed_details_are_preserved_and_release_capacity():
    p = proposal(DEBT, (BANK, "bank", 0), (SUPPLIER, "credit", 0))
    actual, _ = de.apply_details({DEBT: D("100")}, [p], [row("bank", "120"), row("credit", "-20")])
    assert actual[BANK] == 120 and actual[SUPPLIER] == -20 and actual[OTHER] == 0


def test_existing_negative_other_credits_allow_confirmation_without_spending_again():
    initial = {CREDIT: D('1917167.75'), CLIENTS: D('1915277.87'), TAX: D('13940.57'), OTHER_CREDIT: D('-12050.69')}
    rows = [row('clients', '1915277.87'), row('tax', '13940.57'), row('other', '-12050.69')]
    ps = [proposal(CREDIT, (CLIENTS, 'clients', 0), (TAX, 'tax', 0), (OTHER_CREDIT, 'other', 0))]
    actual, report = de.apply_details(initial, ps, rows)
    assert all(actual[k] == v for k, v in initial.items())
    assert not report['rejected'] and D(report['families'][CREDIT]['unresolved']) == 0


def test_detailed_other_is_checked_after_other_categories_consume_capacity():
    p = proposal(DEBT, (OTHER, "other", 0), (BANK, "bank", 0))
    actual, report = de.apply_details({DEBT: D("100")}, [p], [row("other", "70"), row("bank", "80")])
    assert actual[BANK] == 80 and actual[OTHER] == 20
    assert report["families"][DEBT]["unresolved"] == "20"


def test_failed_reader_preserves_initial_extraction(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: [row("r", "100")])
    def fail(*args):
        raise TimeoutError("unavailable")
    monkeypatch.setattr(de, "read_details", fail)
    bs = {INV: D("100")}
    result, prior, report = de.enrich_pdf_details("unused.pdf", bs)
    assert result == bs and prior is None and report["status"] == "unavailable"


def test_current_and_prior_use_their_own_cells(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [de.SourceRow("r", 2, "T", "merci corrente precedente", (D("70"), D("40")))]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(de, "read_details", lambda *a: de.DetailReading(proposals=[
        proposal(INV, (GOODS, "r", 0)), proposal(INV, (GOODS, "r", 1), period="prior")]))
    current, prior, report = de.enrich_pdf_details("unused", {INV: D("100")}, {INV: D("60")}, fiscal_year=2025)
    assert current[GOODS] == 70 and current[RAW] == 30
    assert prior[GOODS] == 40 and prior[RAW] == 20
    assert set(report["periods"]) == {"current", "prior"}


def test_disabled_pass_does_not_call_reader(monkeypatch):
    monkeypatch.setenv("PDF_DETAIL_ENRICHMENT", "0")
    monkeypatch.setattr(de, "read_details", lambda *a: pytest.fail("reader called"))
    bs = {INV: D("100")}
    assert de.enrich_pdf_details("unused", bs)[0] == bs


def test_ocr_fallback_keeps_numeric_source_cells(tmp_path):
    path = tmp_path / "scan.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(path)
    rows = de.collect_source_rows(str(path), ocr_text="Materie prime 1.234,56\nMerci 2.000,00-")
    assert rows[0].amounts == (D("1234.56"),)
    assert rows[1].amounts == (D("-2000.00"),)


def test_account_codes_and_caption_numbers_are_not_source_amounts(tmp_path):
    path = tmp_path / 'codes.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 50), '102790 000 - Crediti tributari entro 12 mesi 20,00 15,00')
        page.insert_text((40, 70), 'Totale 1) crediti 20,00 15,00')
        doc.save(path)
    rows = de.collect_source_rows(str(path))
    assert rows[0].code == '102790.000'
    assert rows[0].amounts == (D('20'), D('15'))
    assert rows[1].amounts == (D('20'), D('15'))
    assert de._amount('1)') is None
    assert de._amount('(1)') == -1


def test_rotated_ago_rows_and_explicit_ee_oe_are_preserved():
    paths = list((INBOX.parent / 'riptova').glob('budget_623_*.pdf'))
    if not paths:
        pytest.skip('private regression PDF not present')
    rows = de.collect_source_rows(str(paths[0]))
    assert len(rows) > 150
    tax = find(rows, '15100000 - Crediti tributari (EE)')
    assert tax.code == '15100000' and tax.side == 'L'
    assert tax.amounts == (D('18890.15'),) and tax.kinds == ('ledger_final',)
    deferred = find(rows, 'Imposte anticipate (OE)')
    assert de._ledger_maturity(deferred, rows, debt=False) == ('long', 'documented')
    fixed = find(rows, 'Crediti v/altri (EE-immob.)')
    assert not de._credit_source_allowed(fixed, rows)


@pytest.mark.parametrize('failure', ['column', 'schema'])
def test_reader_repairs_invalid_cell_index_or_schema_once(monkeypatch, failure):
    from types import SimpleNamespace
    import anthropic
    calls = []
    def create(**kw):
        calls.append(kw)
        column = 1 if len(calls) == 1 else 0
        reading = de.DetailReading(proposals=[proposal(CREDIT, (TAX, 'p1Tr1', column))])
        payload = reading.model_dump()
        if failure == 'schema' and len(calls) == 1:
            payload['proposals'][0]['period'] = '2025'
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='dettagli_documentati', id='tool1', input=payload)])
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=create)))
    result = de.read_details([row('p1Tr1', '20')], {'current': {CREDIT: D('100')}}, 2025)
    assert len(calls) == 2 and result.proposals[0].items[0].column == 0
    schema = calls[0]['tools'][0]['input_schema']
    assert schema['$defs']['DetailCell']['properties']['row']['enum'] == ['p1Tr1']
    assert calls[1]['messages'][-1]['content'][0]['is_error']


def test_gx10_reader_computes_schema_and_repairs_invalid_row(monkeypatch):
    from importers import llm_provider
    monkeypatch.setenv('PDF_LLM_PROVIDER_DETTAGLI', 'gx10')
    monkeypatch.setenv('GX10_API_KEY', 'chiave-di-prova')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    calls = []

    def fake(system_prompt, messaggi, schema, *, max_tokens, **kwargs):
        calls.append({'messaggi': [dict(m) for m in messaggi], 'schema': schema, 'max_tokens': max_tokens})
        if len(calls) == 1:
            return de.DetailReading(proposals=[proposal(CREDIT, (TAX, 'id-inesistente', 0))]).model_dump()
        return de.DetailReading(proposals=[proposal(CREDIT, (TAX, 'p1Tr1', 0))]).model_dump()

    monkeypatch.setattr(llm_provider, 'chiama_gx10_json', fake)
    result = de.read_details([row('p1Tr1', '20')], {'current': {CREDIT: D('100')}}, 2025)
    assert len(calls) == 2
    assert result.proposals[0].items[0].row == 'p1Tr1'
    schema = calls[0]['schema']
    assert schema['$defs']['DetailCell']['properties']['row']['enum'] == ['p1Tr1']
    assert calls[0]['max_tokens'] == 16384
    second = calls[1]['messaggi']
    assert [m['role'] for m in second] == ['user', 'assistant', 'user']
    assert json.loads(second[1]['content'])['proposals'][0]['items'][0]['row'] == 'id-inesistente'
    assert 'Correggi i riferimenti' in second[2]['content']
    assert 'id-inesistente' in second[2]['content']


def test_gx10_reader_truncated_response_raises_clean_error(monkeypatch):
    from importers import llm_provider
    monkeypatch.setenv('PDF_LLM_PROVIDER_DETTAGLI', 'gx10')
    monkeypatch.setenv('GX10_API_KEY', 'chiave-di-prova')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    def fake(*args, **kwargs):
        raise llm_provider.RispostaTroncata('risposta gx10 troncata')

    monkeypatch.setattr(llm_provider, 'chiama_gx10_json', fake)
    with pytest.raises(de.DetailReadError, match='output_truncated'):
        de.read_details([row('p1Tr1', '20')], {'current': {CREDIT: D('100')}}, 2025)


def test_gx10_provider_lets_enrich_pdf_details_search_without_anthropic_key(monkeypatch):
    monkeypatch.setenv('PDF_LLM_PROVIDER_DETTAGLI', 'gx10')
    monkeypatch.setenv('GX10_API_KEY', 'chiave-di-prova')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    rows = [ledger_row('soci', '40', '31', 'Soci c/finanziamento', 'R'),
            ledger_row('suppliers', '50', '33', 'Fornitori', 'R')]
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: rows)
    calls = []
    monkeypatch.setattr(de, 'read_details', lambda *a: calls.append(1) or de.DetailReading())
    current, prior, report = de.enrich_pdf_details('unused', {DEBT: D('100')}, {DEBT: D('80')})
    assert calls  # search_details ran instead of stopping at "local_only"
    assert report['status'] != 'local_only'


def source_file(name):
    path = INBOX / name
    if not path.exists():
        pytest.skip("private regression PDF not present")
    return str(path)


def find(rows, text, page=None):
    matches = [r for r in rows if r.amounts and text.lower() in r.text.lower() and (page is None or r.page == page)]
    assert len(matches) == 1, [r.text for r in matches]
    return matches[0]


def test_formetal_note_cells_reconstruct_debts_across_pages_and_keep_totals():
    rows = de.collect_source_rows(source_file("FORMETAL_701_Bilancio xbrl 31-12-2025.pdf"))
    # These are source-referenced golden classifications, not a mocked PDF.
    specs = [("sp16b_debiti_altri_finanz_breve", "Debiti verso soci", 18, 3),
             (BANK, "Debiti verso banche", 18, 3),
             (SUPPLIER, "Debiti verso fornitori", 18, 3),
             ("sp16e_debiti_tributari_breve", "Debiti tributari", 19, 3),
             (OTHER, "Altri debiti", 19, 3)]
    cells = [(field, find(rows, text, page).id, col) for field, text, page, col in specs]
    # The previdenza label wraps; its numeric line is located by its printed cells.
    previdenza = next(r for r in rows if r.page == 19 and D("31961") in r.amounts)
    cells.append(("sp16f_debiti_previdenza_breve", previdenza.id, 3))
    long = "sp17_debiti_lungo"
    ps = [proposal(DEBT, *cells), proposal(long, ("sp17a_debiti_banche_lungo", find(rows, "Debiti verso banche", 18).id, 4))]
    initial = {DEBT: D("1255656"), long: D("459080")}
    actual, report = de.apply_details(initial, ps, rows)
    assert actual[DEBT] == 1255656 and actual[long] == 459080
    assert actual[BANK] == 710247 and actual[SUPPLIER] == 364665 and actual[OTHER] == 97624
    assert actual["sp16b_debiti_altri_finanz_breve"] == 34450
    assert sum(actual[f] for f in detail_fields(DEBT)) == initial[DEBT]
    assert not report["rejected"]
    local, local_report = de.apply_details(initial, [p for p in de.note_details(rows)
                                                   if p.period == 'current' and p.aggregate in initial], rows)
    assert local == actual and not local_report['rejected']
    prior, _ = de.apply_details({INV: D('124250')}, [p for p in de.note_details(rows) if p.period == 'prior'], rows)
    assert prior[RAW] == 70835 and prior[GOODS] == 53415


def test_note_movement_and_previous_year_maturity_guesses_are_rejected():
    rows = de.collect_source_rows(source_file("FORMETAL_701_Bilancio xbrl 31-12-2025.pdf"))
    bank = find(rows, 'Debiti verso banche', 18)
    assert bank.kinds == ('opening', 'movement', 'closing', 'short', 'long')
    long = 'sp17_debiti_lungo'
    bs = {long: D('689007')}
    for column in (0, 1, 3, 4):
        p = proposal(long, ('sp17a_debiti_banche_lungo', bank.id, column), period='prior')
        actual, report = de.apply_details(bs, [p], rows)
        assert actual == bs and report['rejected']


def test_formetal_note_reconstructs_credit_types_and_maturities():
    rows = de.collect_source_rows(source_file("FORMETAL_701_Bilancio xbrl 31-12-2025.pdf"))
    initial = {CREDIT: D('579879'), CLIENTS: D('579879'), LONG_CREDIT: D('95428')}
    ps = [p for p in de.note_details(rows) if p.aggregate in (CREDIT, LONG_CREDIT)]
    actual, report = de.apply_details(initial, ps, rows)
    assert [actual[f] for f in (CLIENTS, TAX, DEFERRED, OTHER_CREDIT, LONG_TAX)] == [
        D('455145'), D('97048'), D('5042'), D('22644'), D('95428')]
    for aggregate in (CREDIT, LONG_CREDIT):
        assert actual[aggregate] == initial[aggregate]
        assert sum(actual[f] for f in detail_fields(aggregate)) == initial[aggregate]
        assert D(report['families'][aggregate]['unresolved']) == 0
    assert not report['rejected']
    tax = find(rows, 'Crediti circolante tributari', 14)
    for column in range(len(tax.amounts)):
        prior = {CREDIT: D('391557'), CLIENTS: D('391557')}
        untouched, rejected = de.apply_details(prior, [proposal(CREDIT, (TAX, tax.id, column), period='prior')], rows)
        assert untouched == prior and rejected['rejected']
    for column in (0, 1, 2, 4):
        untouched, rejected = de.apply_details(initial, [proposal(CREDIT, (TAX, tax.id, column))], rows)
        assert untouched == initial and rejected['rejected']


@pytest.mark.parametrize('bucket', [CLIENTS, OTHER_CREDIT])
def test_partial_credit_details_preserve_initial_bucket_and_group_types(bucket):
    initial = {CREDIT: D('100.03'), bucket: D('100.03')}
    fields = (TAX, DEFERRED, 'sp06b_crediti_controllate_breve',
              'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve')
    rows = [row(str(i), '10') for i in range(len(fields))]
    ps = [proposal(CREDIT, *((field, r.id, 0) for field, r in zip(fields, rows)))]
    actual, report = de.apply_details(initial, ps, rows)
    assert all(actual[f] == 10 for f in fields)
    assert actual[bucket] == D('50.03')
    assert actual[CREDIT] == initial[CREDIT]
    assert report['families'][CREDIT]['unresolved'] == '50.03'
    assert de.apply_details(actual, ps, rows)[0] == actual


def ledger_row(id, amount, code, text, side='L'):
    return de.SourceRow(id, 1, side, text, (D(amount),), code, kinds=('ledger_final',))


def test_credit_ledger_opens_mixed_parents_and_excludes_fixed_assets_and_cash():
    rows = [ledger_row('root', '100', '15', 'CREDITI VARI'),
            ledger_row('b', '10', '15.01', 'IMPRESE CONTROLLATE'),
            ledger_row('c', '20', '15.02', 'CREDITI VERSO COLLEGATE'),
            ledger_row('d', '30', '15.03', 'CREDITI VERSO CONTROLLANTI'),
            ledger_row('g', '40', '15.04', 'CREDITI VERSO ALTRI'),
            ledger_row('fixed', '500', '09', 'IMMOBILIZZAZIONI FINANZIARIE'),
            ledger_row('fixed_child', '500', '09.01', 'CREDITI VERSO CONTROLLATE'),
            ledger_row('cash', '1000', '19', 'DISPONIBILITA LIQUIDE'),
            ledger_row('cash_child', '1000', '19.01', 'BANCA DI CREDITO COOPERATIVO')]
    initial = {CREDIT: D('100'), CLIENTS: D('100')}
    ps = de.ledger_details(rows, initial)
    assert {i.row for p in ps for i in p.items} == {'b', 'c', 'd', 'g'}
    actual, report = de.apply_details(initial, ps, rows)
    assert [actual[f] for f in detail_fields(CREDIT)] == list(map(D, ['0', '10', '20', '30', '0', '0', '40']))
    assert not report['rejected']
    # Even an LLM proposal cannot re-use fixed financial receivables as C.II.
    unchanged, rep = de.apply_details(initial, [proposal(CREDIT, (TAX, 'fixed_child', 0))], rows)
    assert unchanged == initial and rep['rejected']


def test_credit_ledger_defaults_to_short_and_explicit_maturity_wins():
    rows = [ledger_row('tax', '50', '35', 'CREDITI TRIBUTARI')]
    initial = {CREDIT: D('100'), LONG_CREDIT: D('60')}
    actual, rep = de.reclassify_ledger_maturities(initial, rows)
    assert actual[CREDIT] == 160 and actual[LONG_CREDIT] == 0 and actual[TAX] == 50
    assert rep['families'][CREDIT]['evidence'][0]['basis'] == 'management_default_short'
    rows = [ledger_row('short', '30', '35.01', 'Crediti tributari entro 12 mesi'),
            ledger_row('long', '40', '35.02', "Crediti tributari oltre l'esercizio successivo")]
    actual, rep = de.reclassify_ledger_maturities(initial, rows)
    assert actual[TAX] == 30 and actual[LONG_TAX] == 40
    assert actual[CREDIT] == 120 and actual[LONG_CREDIT] == 40
    assert all(e['basis'] == 'documented' for e in rep['families'][CREDIT]['evidence'])
    # An unsubstantiated initial long classification also defaults to short.
    all_long = {LONG_CREDIT: D('100')}
    rows = [ledger_row('tax', '50', '35', 'CREDITI TRIBUTARI')]
    actual, _ = de.reclassify_ledger_maturities(all_long, rows)
    assert actual[TAX] == 50 and actual[CREDIT] == 100 and actual[LONG_CREDIT] == 0


def test_financing_defaults_long_explicit_short_wins_and_unknown_residue_stays_short():
    long = 'sp17_debiti_lungo'
    long_bank = 'sp17a_debiti_banche_lungo'
    long_soci = 'sp17b_debiti_altri_finanz_lungo'
    rows = [ledger_row('root', '70', '31', 'FINANZIAMENTI BANCARI', 'R'),
            ledger_row('loan', '50', '31.01', 'Mutui oltre 12 mesi', 'R'),
            ledger_row('quota', '20', '31.02', 'Finanziamento bancario entro 12 mesi', 'R'),
            ledger_row('soci', '10', '32', 'Soci c/finanziamento infruttifero', 'R'),
            ledger_row('other_lender', '5', '34', 'Debiti verso altri finanziatori', 'R'),
            ledger_row('bank', '5', '19', 'Banca c/c', 'R')]
    initial = {DEBT: D('100.03'), OTHER: D('100.03'), 'totale_passivo': D('250')}
    actual, report = de.reclassify_ledger_maturities(initial, rows)
    assert actual[DEBT] == D('35.03') and actual[long] == 65
    assert actual[BANK] == 25 and actual[long_bank] == 50 and actual[long_soci] == 15
    assert actual[OTHER] == D('10.03') and actual['totale_passivo'] == 250
    evidence = {e['row']: e for e in report['families'][DEBT]['evidence']}
    assert evidence['quota']['basis'] == 'documented'
    assert evidence['soci']['basis'] == 'management_financing_long'
    assert evidence['bank']['basis'] == 'management_default_short'
    assert 'root' not in evidence
    assert de.reclassify_ledger_maturities(actual, rows)[0] == actual


def test_explicit_note_maturity_prevents_ledger_default_reclassification():
    initial = {DEBT: D('70'), 'sp17_debiti_lungo': D('30')}
    rows = [ledger_row('soci', '100', '31', 'Soci c/finanziamento', 'R'),
            de.SourceRow('note', 2, 'T', 'Debiti verso soci per finanziamenti',
                         (D('70'), D('30')), kinds=('short', 'long'))]
    actual, report = de.reclassify_ledger_maturities(initial, rows)
    assert actual == initial and not report['families']


def test_local_enrichment_applies_maturity_policy_and_audits_it(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    rows = [ledger_row('soci', '40', '31', 'Soci c/finanziamento', 'R'),
            ledger_row('suppliers', '50', '33', 'Fornitori', 'R')]
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: rows)
    current, prior, report = de.enrich_pdf_details('unused', {DEBT: D('100')}, {DEBT: D('80')})
    assert current[DEBT] == 60 and current['sp17_debiti_lungo'] == 40
    assert current[SUPPLIER] == 50 and current[OTHER] == 10
    assert prior == {DEBT: D('80')}  # current ledger is no evidence for prior year
    assert report['status'] == 'local_only'
    assert report['periods']['current']['maturity']['families'][DEBT]['after'][DEBT] == '60'


def test_credit_gross_clients_do_not_spend_net_aggregate_ignoring_allowance():
    initial = {CREDIT: D('110'), OTHER_CREDIT: D('110')}
    rows = [ledger_row('clients', '100', '11', 'CLIENTI'),
            ledger_row('tax', '20', '35', 'CONTI ERARIALI'),
            ledger_row('fund', '10', '23', 'FONDO SVALUTAZIONE CREDITI', side='R')]
    ps = de.ledger_details(rows, initial)
    ps.append(proposal(CREDIT, (CLIENTS, 'clients', 0)))
    actual, report = de.apply_details(initial, ps, rows)
    assert actual[TAX] == 20 and actual[OTHER_CREDIT] == 90 and actual[CLIENTS] == 0
    assert any('lordi' in r['reason'] for r in report['rejected'])


@pytest.mark.parametrize("filename,debts,retained", [
    ("TM-BUSINESS_590_bilancio 2025.pdf", "447232.83", "395819.39"),
    ("TM-BUSINESS_589_bilancio 2026.pdf", "737374.42", "435874.57"),
])
def test_tm_children_explain_inventory_and_prevent_pn_becoming_debt(filename, debts, retained):
    from importers.situazione_contabile_parser import extract_situazione_contabile
    from importers.pdf_importer import _map_sc_keys
    path = source_file(filename)
    bs, _ = extract_situazione_contabile(path)
    assert bs["sp16"] == D(debts)
    assert bs["sp11"] == 10000 and bs["sp12"] == D(retained) + 2000
    rows = de.collect_source_rows(path)
    cells = [(GOODS, find(rows, "Rimanenze di merci").id, 1),
             (RAW, find(rows, "Riman. mat.prime").id, 1),
             (WIP, find(rows, "Lavori in corso su ordinazione").id, 1)]
    actual, report = de.apply_details({INV: bs["sp05"]}, [proposal(INV, *cells)], rows)
    assert actual[RAW] == 21250 and actual[GOODS] == 170000 and actual[WIP] == 40000
    assert actual[INV] == 231250 and not report["rejected"]
    mapped = _map_sc_keys(bs)
    matured, maturity_report = de.reclassify_ledger_maturities(mapped, rows)
    local, rep = de.apply_details(matured, de.ledger_details(rows, matured), rows)
    assert local[RAW] == 21250 and local[GOODS] == 170000 and local[WIP] == 40000
    expected = ('268242.15', '2455.95', '133144.56', '1971.81', '14300.34', '27118.02') if '590' in filename else (
        '349991.50', '6455.95', '310448.41', '23113.67', '18817.63', '28547.26')
    fields = ('sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo', SUPPLIER, 'sp16e_debiti_tributari_breve',
              'sp16f_debiti_previdenza_breve', OTHER)
    assert [local[f] for f in fields] == list(map(D, expected))
    assert local[DEBT] + local['sp17_debiti_lungo'] == D(debts)
    assert local['sp17_debiti_lungo'] == sum(map(D, expected[:2]))
    assert de.reclassify_ledger_maturities(matured, rows)[0] == matured
    assert not maturity_report['families'][DEBT]['rejected']
    expected_credits = ('271202.44', '129413.95', '6020.18') if '590' in filename else (
        '501823.05', '147807.76', '6020.42')
    assert [local[f] for f in (CLIENTS, TAX, OTHER_CREDIT)] == list(map(D, expected_credits))
    assert sum(local[f] for f in detail_fields(CREDIT)) == mapped[CREDIT]
    assert D(rep['families'][CREDIT]['unresolved']) == 0
    assert not rep['rejected']


def test_import_pipeline_persists_both_years_details_and_provenance(tmp_path, monkeypatch):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer as importer, pdf_extractor_llm as extractor
    from importers import standard_ivcee_parser as standard, bilancio_classifier as classifier

    path = tmp_path / "comparative.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 50), "Stato patrimoniale Attivo 2025 2024")
        page.insert_text((40, 70), "Rimanenze 100,00 60,00")
        page.insert_text((40, 90), "Merci 70,00 40,00")
        page.insert_text((40, 110), "Crediti entro 12 mesi 100,00 60,00")
        page.insert_text((40, 130), "Clienti 70,00 40,00")
        page.insert_text((40, 150), "Crediti tributari entro 12 mesi 20,00 15,00")
        doc.save(path)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(importer, "SessionLocal", sessions)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    current = {INV: D("100"), CREDIT: D("100"), OTHER_CREDIT: D('100'), "sp11_capitale": D("200"), "totale_attivo": D("200"), "totale_passivo": D("200")}
    prior = {INV: D("60"), CREDIT: D("60"), OTHER_CREDIT: D('60'), "sp11_capitale": D("120"), "totale_attivo": D("120"), "totale_passivo": D("120")}
    monkeypatch.setattr(classifier, "classify_bilancio", lambda **kw: classifier.Classification(
        "A", "synthetic", classifier.ROUTE_IVCEE, "test", "high", {}, "test"))
    monkeypatch.setattr(standard, "extract_standard_ivcee_balances", lambda *a, **kw: (None, None))
    monkeypatch.setattr(extractor, "extract_pdf_with_llm", lambda *a, **kw: (dict(current), {"ce01_ricavi_vendite": D("0")}))
    monkeypatch.setattr(extractor, "extract_pdf_both_years_with_llm", lambda *a, **kw: (
        dict(current), {"ce01_ricavi_vendite": D("0")}, dict(prior), {"ce01_ricavi_vendite": D("0")}))
    # This test isolates enrichment; macro acquisition has its own source tests.
    from importers import macro_analysis
    monkeypatch.setattr(macro_analysis, 'analyze_pdf_macros', lambda *a, **kw: (
        dict(current), {'ce01_ricavi_vendite': D(0)}, dict(prior), {'ce01_ricavi_vendite': D(0)},
        {'status': 'verified', 'income_verified': True,
         'prior': {'status': 'verified', 'income_verified': True}}))
    def read(rows, balances, fiscal_year):
        r = find(rows, "Merci")
        clients, tax = find(rows, 'Clienti'), find(rows, 'Crediti tributari')
        return de.DetailReading(proposals=[proposal(INV, (GOODS, r.id, 0)),
            proposal(INV, (GOODS, r.id, 1), period="prior"),
            proposal(CREDIT, (CLIENTS, clients.id, 0), (TAX, tax.id, 0)),
            proposal(CREDIT, (CLIENTS, clients.id, 1), (TAX, tax.id, 1), period='prior')])
    monkeypatch.setattr(de, "read_details", read)
    try:
        result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name="Analytical test")
        assert result["success"] and result["prior_year_imported"]
        with sessions() as db:
            years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
            assert len(years) == 2
            for year, goods, raw in zip(years, [D("70"), D("40")], [D("30"), D("20")]):
                assert year.balance_sheet.sp05d_prodotti_finiti == goods
                assert year.balance_sheet.sp05a_materie_prime == raw
                assert year.balance_sheet.sp06a_crediti_clienti_breve == goods
                assert year.balance_sheet.sp06e_crediti_tributari_breve == (20 if year.year == 2025 else 15)
                assert year.balance_sheet.sp06g_crediti_altri_breve == (10 if year.year == 2025 else 5)
                report = json.loads(year.validation_report)["detail_enrichment"]
                assert report["status"] == "completed"
                assert report["families"][INV]["evidence"][0]["text"].startswith("Merci")
                assert report['families'][CREDIT]['evidence']
            # A later manual edit must not erase the import's source evidence.
            monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
            from app.api.v1 import financial_years as endpoint
            from app.schemas.adjustments import AdjustmentsUpdate
            monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
            before = json.loads(years[0].validation_report)['detail_enrichment']
            endpoint.save_adjustments(
                company_id=result['company_id'], year=2025,
                payload=AdjustmentsUpdate(balance_sheet={}, income_statement={}),
                period_months=None, user_id='test', db=db,
            )
            db.refresh(years[0])
            assert json.loads(years[0].validation_report)['detail_enrichment'] == before
    finally:
        engine.dispose()
