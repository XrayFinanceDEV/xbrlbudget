"""Fase 2, Task 4: il lettore di righe nell'import PDF. Solo diagnosi: nessun numero importato cambia."""
import time
from decimal import Decimal

import pytest

from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

_VOCE = "Debiti verso fornitori"


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
    monkeypatch.delenv("LETTORE_DIAGNOSI", raising=False)
    monkeypatch.delenv("LETTORE_TETTO_SECONDI", raising=False)
    yield s
    engine.dispose()


def _importa(pdf, sessioni, monkeypatch=None, **kw):
    from importers import pdf_importer

    return pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, company_name="LETTORE", create_company=True, sector=1,
        period_months=6, user_id="lettore-test", **kw)


def _pdf_pulito(tmp_path):
    pdf = tmp_path / "pulito.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=6)
    return pdf


def _pdf_squadrato(tmp_path, monkeypatch):
    """Il PDF stampa un passivo che non torna (+100): l'import lo dichiara squadrato. Senza rete."""
    from importers import pdf_extractor_llm
    from importers.standard_ivcee_parser import extract_standard_ivcee_balances, extract_standard_ivcee_income

    pulito = _pdf_pulito(tmp_path)
    bs, _ = extract_standard_ivcee_balances(str(pulito))
    ce, _ = extract_standard_ivcee_income(str(pulito))
    pdf = tmp_path / "squadrato.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=6, passivo_total_delta=Decimal("100"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_with_llm", lambda *a, **k: (dict(bs), dict(ce)))
    return pdf


def _blocco(sezione="SP", voce=_VOCE):
    return {"voce": voce, "codice": "", "sezione": sezione, "lato": "U", "colonna": 0, "fine": "2026-06-30",
            "mesi": 6, "corrente": True, "stampato": "110.00", "somma": "100.00", "scarto": "10.00",
            "pagina": 1, "righe": ["p1r1U", "p1r4U"], "etichette": [], "cercato": False}


def _finta(monkeypatch, blocchi, conta=None):
    from importers.lettore import diagnosi

    def f(*a, **k):
        if conta is not None:
            conta.append(1)
        return {"esito": "ok", "motivo": None, "blocchi_aperti": blocchi, "avvisi": []}
    monkeypatch.setattr(diagnosi, "diagnosi_pdf", f)


def _numeri(sessioni):
    from database.models import FinancialYear

    with sessioni() as db:
        out = []
        for fy in sorted(db.query(FinancialYear).all(), key=lambda f: (f.year, f.period_months or 0)):
            bs = {c.name: getattr(fy.balance_sheet, c.name) for c in fy.balance_sheet.__table__.columns
                  if c.name not in ("id", "financial_year_id", "created_at", "updated_at")}
            ce = {c.name: getattr(fy.income_statement, c.name) for c in fy.income_statement.__table__.columns
                  if c.name not in ("id", "financial_year_id", "created_at", "updated_at")}
            out.append((fy.year, fy.period_months, fy.validation_status, bs, ce))
        return out


def test_numeri_identici_con_e_senza_lettore(tmp_path, sessioni, monkeypatch):
    pdf = _pdf_pulito(tmp_path)
    monkeypatch.setenv("LETTORE_DIAGNOSI", "0")
    r0 = _importa(pdf, sessioni)
    n0 = _numeri(sessioni)
    with sessioni() as db:
        from database.models import Company
        for c in db.query(Company).all():
            db.delete(c)
        db.commit()
    monkeypatch.setenv("LETTORE_DIAGNOSI", "1")
    r1 = _importa(pdf, sessioni)
    n1 = _numeri(sessioni)
    assert n0 and n0 == n1
    for k in ("success", "extraction_method", "prior_year_imported", "prior_period_months", "validation_status"):
        assert r0.get(k) == r1.get(k)
    assert r0["warnings"] == r1["warnings"]


def test_chiave_lettore_dichiarata(tmp_path, sessioni, monkeypatch):
    pdf = _pdf_pulito(tmp_path)
    r = _importa(pdf, sessioni)
    assert r["validation_report"]["lettore"]["esito"] == "ok"
    assert "blocchi_aperti" in r["validation_report"]["lettore"]
    monkeypatch.setenv("LETTORE_DIAGNOSI", "off")
    r = _importa(pdf, sessioni, )
    assert "lettore" not in r["validation_report"]


def test_lettore_che_solleva_non_ferma_l_import(tmp_path, sessioni, monkeypatch):
    from importers.lettore import diagnosi

    def solleva(*a, **k):
        raise RuntimeError("guasto del lettore")
    monkeypatch.setattr(diagnosi, "diagnosi_pdf", solleva)
    r = _importa(_pdf_pulito(tmp_path), sessioni)
    assert r["success"] is True and r["validation_report"]["lettore"]["esito"] == "errore"


def test_sbilancio_nomina_il_blocco(tmp_path, sessioni, monkeypatch):
    pdf = _pdf_squadrato(tmp_path, monkeypatch)
    _finta(monkeypatch, [_blocco()])
    r = _importa(pdf, sessioni)
    assert r["validation_status"] == "unbalanced"
    testo = [w for w in r["warnings"] if "BLOCCHI CHE NON CHIUDONO" in w]
    assert testo and any(_VOCE in w for w in r["warnings"])
    i = next(i for i, w in enumerate(r["warnings"]) if "non quadra prima dell'importazione" in w)
    assert r["warnings"][i + 1].startswith("BLOCCHI CHE NON CHIUDONO")


def test_documento_che_quadra_nessun_avviso_del_lettore(tmp_path, sessioni, monkeypatch):
    _finta(monkeypatch, [_blocco()])
    r = _importa(_pdf_pulito(tmp_path), sessioni)
    assert not any("BLOCCHI CHE NON CHIUDONO" in w or _VOCE in w for w in r["warnings"])
    assert len(r["validation_report"]["lettore"]["blocchi_aperti"]) == 1


def test_sbilancio_senza_blocchi_non_inventa(tmp_path, sessioni, monkeypatch):
    pdf = _pdf_squadrato(tmp_path, monkeypatch)
    _finta(monkeypatch, [])
    r = _importa(pdf, sessioni)
    assert r["validation_status"] == "unbalanced"
    assert not any("BLOCCHI CHE NON CHIUDONO" in w for w in r["warnings"])
    assert r["validation_report"]["lettore"]["blocchi_aperti"] == []


def test_una_sola_diagnosi_per_import(tmp_path, sessioni, monkeypatch):
    conta = []
    _finta(monkeypatch, [])
    _importa(_pdf_pulito(tmp_path), sessioni)
    from importers.lettore import diagnosi
    f = diagnosi.diagnosi_pdf
    monkeypatch.setattr(diagnosi, "diagnosi_pdf", lambda *a, **k: (conta.append(1), f(*a, **k))[1])
    _importa(_pdf_pulito(tmp_path), sessioni)
    assert len(conta) == 1


def test_tetto_di_tempo_nell_import(tmp_path, sessioni, monkeypatch):
    from importers.lettore import diagnosi

    monkeypatch.setenv("LETTORE_TETTO_SECONDI", "0.1")
    monkeypatch.setattr(diagnosi, "leggi_pdf", lambda p: time.sleep(2))
    r = _importa(_pdf_pulito(tmp_path), sessioni)
    assert r["success"] is True and r["validation_report"]["lettore"]["esito"] == "tempo"
