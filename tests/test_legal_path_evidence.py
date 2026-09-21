from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import fitz
import pytest

from importers import legal_path_evidence as lp
from importers.detail_enrichment import SourceRow
from importers.iv_cee_hierarchy import check_quadratura


def miniature(tmp_path, monkeypatch, damaged=False):
    path = tmp_path / 'dated.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=750)
        for x, text in [(400, '31/12/2025'), (500, '31/12/2024'), (600, 'Differenza')]:
            page.insert_text((x, 40), text, fontsize=8)
        doc.save(path)
    values = [
        ('Stato patrimoniale attivo', '100'), ('C.II) Crediti', '80'),
        ('C.II.1) verso clienti', '50'), ('C.II.5quater) verso altri', '30'),
        ('C.IV) Disponibilita liquide', '20'), ('Stato patrimoniale passivo', '100'),
        ('A) Patrimonio netto', '40'), ('A.I) Capitale', '30'), ('A.IX) Utile', '10'),
        ('D) Debiti', '60'), ('D.4) verso banche', '60'),
        ('D.4.1) esigibili entro', '60'), ('Conto economico', '0'),
        ('A) Produzione', '100'), ('A.1) Ricavi', '100'), ('B) Costi', '90'),
        ('B.7) Servizi', '90'), ('Risultato prima delle imposte', '10'),
        ('21) Utile esercizio', '10')]
    rows = [SourceRow(str(i), 1, 'T', f'{i+1} '+label,
                      (D(i+1), D(value), D(value), D('999999')),
                      positions=(40, 420, 520, 620)) for i, (label, value) in enumerate(values)]
    if damaged:
        rows[2] = replace(rows[2], amounts=(D(3), D(49), D(50), D('999999')))
    monkeypatch.setattr(lp, 'collect_source_rows', lambda p: rows)
    return path


def test_dated_columns_ignore_row_indices_and_differences(tmp_path, monkeypatch):
    for bs, ce, audit in lp.extract_path_source(miniature(tmp_path, monkeypatch)):
        assert audit['status'] == 'verified'
        assert bs['sp06a_crediti_clienti_breve'] == 50
        assert bs['sp06g_crediti_altri_breve'] == 30
        assert bs['totale_attivo'] == bs['totale_passivo'] == 100
        assert check_quadratura(bs, ce).semantic_valid


def test_incomplete_family_declines_current_without_contaminating_prior(tmp_path, monkeypatch):
    current, prior = lp.extract_path_source(miniature(tmp_path, monkeypatch, damaged=True))
    assert current[0] is None and current[2]['status'] == 'declined'
    assert 'incomplete family: C.II' in current[2]['errors']
    assert prior[2]['status'] == 'verified'


def test_real_qualified_paths_preserve_cents_and_signed_bank_balances():
    corpus = Path(__file__).resolve().parents[1] / 'inbox' / 'check-budget1'
    paths = list(corpus.glob('budget_967_*.pdf'))
    if not paths:
        pytest.skip('private regression PDF not present')
    for (bs, ce, audit), assets, profit, bank in zip(lp.extract_path_source(paths[0]),
            ['1125225.58', '688939.96'], ['32368.64', '220177.52'], ['-63907.40', '-324997.01']):
        assert audit['status'] == 'verified' and audit['income_verified']
        assert bs['totale_attivo'] == D(assets)
        assert le_profit(ce) == bs['sp13_utile_perdita'] == D(profit)
        assert bs['sp16a_debiti_banche_breve'] == D(bank)
        assert check_quadratura(bs, ce).semantic_valid


def le_profit(ce):
    from importers.iv_cee_hierarchy import _net_profit_from_ce
    return _net_profit_from_ce(ce)
