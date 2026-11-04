"""La durata della colonna dell'anno precedente di un infrannuale, dalle date stampate (testi sintetici)."""
from importers.durata_comparato import mesi_del_comparato


def test_stesso_periodo_dell_anno_prima():
    testo = "Periodo fino al 30/06/2026   Bilancio infrannuale al 30/06/2025"
    assert mesi_del_comparato(testo, 2026) == 6


def test_anno_prima_intero():
    testo = "dal 01/01/2026 al 31/05/2026   dal 01/01/2025 al 31/12/2025"
    assert mesi_del_comparato(testo, 2026) == 12


def test_date_coi_trattini_come_lo_schema_xbrl():
    assert mesi_del_comparato("Esercizio 01-01-2026 31-12-2026  30-09-2026  30-09-2025", 2026) == 9


def test_nessuna_data_dell_anno_prima_e_ignota():
    assert mesi_del_comparato("dal 01/01/2026 al 30/09/2026 COMPARATO CON SALDO ANNO PRECEDENTE", 2026) is None


def test_due_chiusure_diverse_sono_ignote():
    assert mesi_del_comparato("al 30/06/2025 ... saldo al 31/12/2025", 2026) is None


def test_una_data_che_non_chiude_un_mese_non_conta():
    # la data di una delibera o di una stampa non e' la chiusura di una colonna
    assert mesi_del_comparato("approvato il 15/04/2025   al 31/12/2025", 2026) == 12
    assert mesi_del_comparato("approvato il 15/04/2025", 2026) is None


def test_un_codice_che_somiglia_a_una_data_non_conta():
    assert mesi_del_comparato("conto 01.20.03  30/06/2025", 2026) == 6


def test_febbraio_bisestile():
    assert mesi_del_comparato("al 29/02/2024", 2025) == 2
    assert mesi_del_comparato("al 28/02/2024", 2025) is None


# --- import completo su un infrannuale a due colonne sintetico --------------------------------

from decimal import Decimal

import pytest

from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf


@pytest.fixture
def sessioni(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", s)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield s
    engine.dispose()


@pytest.fixture
def due_anni_dal_modello(tmp_path, monkeypatch):
    """Il modello che legge le due colonne, senza rete: corrente e precedente sono le cifre del
    prospetto a una colonna, che il lettore deterministico legge da solo."""
    from importers import pdf_extractor_llm
    from importers.standard_ivcee_parser import extract_standard_ivcee_balances, extract_standard_ivcee_income

    def finto(mesi):
        pulito = tmp_path / f"una-colonna-{mesi}.pdf"
        _write_compact_infrannual_pdf(pulito, period_months=mesi)
        bs, _ = extract_standard_ivcee_balances(str(pulito))
        ce, _ = extract_standard_ivcee_income(str(pulito))
        assert bs is not None and ce is not None
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        import anthropic

        def nessuna_rete(*a, **k):                  # le fasi col modello falliscono senza uscire
            raise RuntimeError("rete vietata nel test")
        monkeypatch.setattr(anthropic, "Anthropic", nessuna_rete)
        monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_both_years_with_llm",
                            lambda *a, **k: (dict(bs), dict(ce), dict(bs), dict(ce)))
        monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_with_llm", lambda *a, **k: (dict(bs), dict(ce)))
    return finto


def _importa(pdf, *, period_months, company_id=None):
    from importers import pdf_importer

    return pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), company_id=company_id, fiscal_year=2026, company_name="DURATA COMPARATO",
        create_company=company_id is None, sector=1, period_months=period_months, user_id="durata-test",
    )


def _anni(sessioni):
    from database.models import FinancialYear

    with sessioni() as db:
        return sorted(((fy.year, fy.period_months) for fy in db.query(FinancialYear).all()),
                      key=lambda a: (a[0], a[1] or 0))


def test_semestre_su_semestre_salva_il_precedente_come_semestre(tmp_path, sessioni, due_anni_dal_modello):
    due_anni_dal_modello(6)
    pdf = tmp_path / "giugno-su-giugno.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=6, comparato="30/06/2025")
    r = _importa(pdf, period_months=6)
    assert r["success"] is True and r["prior_year_imported"] is True
    assert r["prior_period_months"] == 6
    assert _anni(sessioni) == [(2025, 6), (2026, 6)]
    assert any("ANNO PRECEDENTE PARZIALE [2025, 6 mesi]" in w for w in r["warnings"])


def test_confronto_con_l_anno_intero_resta_anno_intero(tmp_path, sessioni, due_anni_dal_modello):
    due_anni_dal_modello(6)
    pdf = tmp_path / "giugno-su-dicembre.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=6, comparato="31/12/2025")
    r = _importa(pdf, period_months=6)
    assert r["prior_year_imported"] is True and r["prior_period_months"] is None
    assert _anni(sessioni) == [(2025, None), (2026, 6)]


def test_il_semestre_non_sostituisce_l_anno_intero_gia_importato(tmp_path, sessioni, due_anni_dal_modello):
    from database.models import FinancialYear

    due_anni_dal_modello(6)
    intero = tmp_path / "giugno-su-dicembre.pdf"
    _write_compact_infrannual_pdf(intero, period_months=6, comparato="31/12/2025")
    primo = _importa(intero, period_months=6)
    with sessioni() as db:
        id_intero = db.query(FinancialYear).filter_by(year=2025, period_months=None).one().id

    semestre = tmp_path / "giugno-su-giugno.pdf"
    _write_compact_infrannual_pdf(semestre, period_months=6, comparato="30/06/2025")
    _importa(semestre, period_months=6, company_id=primo["company_id"])
    assert _anni(sessioni) == [(2025, None), (2025, 6), (2026, 6)]
    with sessioni() as db:
        assert db.query(FinancialYear).filter_by(year=2025, period_months=None).one().id == id_intero


def test_un_bilancio_annuale_salva_sempre_il_precedente_intero(tmp_path, sessioni, due_anni_dal_modello):
    due_anni_dal_modello(None)
    pdf = tmp_path / "annuale.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=None, comparato="31/12/2025")
    r = _importa(pdf, period_months=None)
    assert r["prior_year_imported"] is True and r["prior_period_months"] is None
    assert _anni(sessioni) == [(2025, None), (2026, None)]
