"""Report intermedio dell'infrannuale, provato sui bilanci veri del DB locale.

Regola del proprietario (2026-09-21): questi test girano solo sui bilanci gia'
importati, non su bilanci inventati. Il DB (`financial_analysis.db` nella
radice, o `BUDGET_REAL_DB`) viene COPIATO in una cartella temporanea e letto da
li': l'originale non si tocca. Senza DB, o senza un infrannuale con la
proiezione, i test si saltano — come quelli del corpus di import.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.renderers.typst.intermedio_catalog import COVER_SECTIONS, build_inventory  # noqa: E402
from app.services.extra_accounting_alerts_service import (  # noqa: E402
    EXTRA_ACCOUNTING_ALERT_KEYS, EXTRA_ACCOUNTING_ALERT_LABELS,
)

_DB = Path(os.environ.get("BUDGET_REAL_DB", ROOT / "financial_analysis.db"))


def test_le_etichette_dei_segnali_sono_quelle_dello_schermo():
    """Il PDF e la Stampa devono dire lo stesso testo per ogni segnale."""
    ts = (ROOT / "frontend/lib/pratica-codes.ts").read_text(encoding="utf-8")
    blocco = ts[ts.index("export const EXTRA_ALERT_DEFS"):]
    blocco = blocco[:blocco.index("];")]
    coppie = re.findall(r'key:\s*"([^"]+)",\s*label:\s*"([^"]+)"', blocco)
    assert [k for k, _ in coppie] == list(EXTRA_ACCOUNTING_ALERT_KEYS)
    assert dict(coppie) == EXTRA_ACCOUNTING_ALERT_LABELS


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    if not _DB.is_file():
        pytest.skip(f"DB locale assente ({_DB}): i test girano solo sui bilanci gia' importati")
    copia = tmp_path_factory.mktemp("intermedio") / "db.sqlite"
    shutil.copyfile(_DB, copia)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{copia}")
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _scenari(db):
    from sqlalchemy.exc import OperationalError
    from database.models import BudgetScenario
    try:
        scenari = [s for s in db.query(BudgetScenario).filter(BudgetScenario.scenario_type == "infrannuale")
                   if s.forecast_years and s.period_months != 12]
    except OperationalError:
        pytest.skip("DB locale senza tabelle: nessun bilancio importato")
    usabili = []
    from app.services.intermedio_report_service import assemble_intermedio
    for scenario in scenari:
        try:
            usabili.append((scenario, assemble_intermedio(db, scenario)))
        except ValueError:
            continue  # bilanci del periodo non importati: il report non esiste
    if not usabili:
        pytest.skip("nessun infrannuale con proiezione nel DB locale")
    return usabili


@pytest.fixture(scope="module")
def modelli(db):
    return _scenari(db)


def _dec(value) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


def test_le_colonne_sono_quelle_dei_bilanci(db, modelli):
    from calculations.intra_year_engine import IntraYearEngine
    for scenario, model in modelli:
        parziale, riferimento = IntraYearEngine(db)._load_financial_years(scenario)
        fattore = Decimal(12) / Decimal(model.period_months)
        assert model.colonna_ce("storico").ricavi == _dec(riferimento.income_statement.ce01_ricavi_vendite)
        assert model.colonna_ce("infrannuale").ricavi == _dec(parziale.income_statement.ce01_ricavi_vendite)
        assert model.colonna_ce("annualizzato").ricavi == _dec(parziale.income_statement.ce01_ricavi_vendite) * fattore
        # Lo SP e' puntuale: l'infrannuale non si annualizza mai.
        assert model.colonna_sp("infrannuale").totale_attivo == _dec(parziale.balance_sheet.total_assets)


def test_i_prospetti_completi_chiudono_sulle_sintesi(modelli):
    """Il prospetto completo (righe del report finale) e le tabelle di sintesi
    leggono gli stessi bilanci: EBITDA, risultato e totale attivo coincidono."""
    for _, model in modelli:
        ce = {r.id: r for r in model.prospetto_ce.rows}
        sp = {r.id: r for r in model.prospetto_sp.rows}
        ebitda = next(r for r in ce.values() if r.code == "ebitda" or r.label.startswith("EBITDA"))
        attivo = next(r for r in sp.values() if r.label == "TOTALE ATTIVO")
        for periodo, valore in zip(model.prospetto_ce.periods, ebitda.values):
            assert valore == model.colonna_ce(periodo.id).ebitda
        for periodo, valore in zip(model.prospetto_sp.periods, attivo.values):
            assert valore == model.colonna_sp(periodo.id).totale_attivo


def test_gli_indicatori_della_crisi_sono_quelli_dello_schermo(db, modelli):
    """Il report legge la stessa risposta di `GET .../infrannuale/crisi`."""
    from app.services.crisi_service import crisi_infrannuale
    for scenario, model in modelli:
        assert model.crisi.model_dump() == crisi_infrannuale(db, scenario)


def test_il_catalogo_ha_una_voce_per_pagina_e_indice_coerente(modelli):
    for _, model in modelli:
        pagine = build_inventory(model)
        ids = [p["id"] for p in pagine]
        assert ids[:9] == ["cover", "sintesi", "ce-confronto", "sp-confronto", "ce-proiezione",
                           "sp-proiezione", "crisi-quadro", "crisi-indicatori", "segnali"]
        assert all(i.startswith("allegato-") for i in ids[9:])
        assert len(ids) == len(set(ids))
        indice = {e["label"]: e["page"] for e in pagine[0]["toc"]}
        for numero, pagina in enumerate(pagine, start=1):
            if pagina["id"] in COVER_SECTIONS:
                assert indice[pagina["title"]] == numero


def test_il_pdf_ha_una_pagina_per_voce_del_catalogo(modelli):
    """Compila davvero, con il renderer del report finale; nessun trabocco su
    nessun infrannuale del DB (commenti lunghi, ricavi quasi nulli compresi)."""
    from app.renderers.typst.intermedio_renderer import IntermedioRenderer
    from app.renderers.typst.runtime import RendererUnavailable
    renderer = IntermedioRenderer.from_project(ROOT)
    for _, model in modelli:
        try:
            pdf = renderer.render_intermedio(model, document_state="final")
        except RendererUnavailable:
            pytest.skip("compilatore Typst o sandbox non disponibili")
        assert pdf.pages == len(build_inventory(model))
        assert pdf.data.startswith(b"%PDF")
