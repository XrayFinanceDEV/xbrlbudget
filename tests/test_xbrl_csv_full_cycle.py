"""Full cycle over the XBRL and CSV import routes (committed fixtures).

Task 4 of the "generi diversi" test matrix: the existing suite
(tests/test_standard_ivcee_parser.py and friends) only drives the PDF import
route end-to-end. This module drives the same import -> scenario ->
2-year-forecast cycle over the two other import routes.

These tests also PIN the fix for the two product gaps this matrix originally
surfaced (see docs/PIANO-TEST-E2E-BILANCIO-2026-07-20.md, Round 2). Both the
bilancio abbreviato XBRL and the TEBE CSV publish only the legal AGGREGATES
(sp04/sp05/sp06/sp07/sp12/sp14/sp16/sp17, ce08/ce09) with no typed sub-fields.
The forecast engine's forecastability gate
(calculations/intra_year_engine.py::_validate_forecast_source) needs each family
to reconcile against its detail. Both importers now call
importers.iv_cee_hierarchy.reconcile_source_detail, which books the unexplained
aggregate-minus-detail remainder into each family's "altri" bucket (aggregate and
balance untouched), so a real abbreviato XBRL / TEBE CSV company IS forecastable:

* legacy/sample_data/ISTANZA02353550391.xbrl (a real deposited XBRL, Wolters
  Kluwer "Bilancio Genya", taxonomy 2018-11-04) imports, balances, and now
  completes a full 2-year budget cycle — previously it was refused with
  "aggregate/detail mismatch: sp04_immob_finanziarie, sp14_fondi_rischi".

* A synthetic TEBE CSV carrying real stock / trade receivables / payables /
  depreciation (all published as aggregates only) now imports and forecasts —
  the reconcile fills sp05e/sp06g/sp16g and splits ce09 into ce09a/ce09b in
  proportion to the intangible/tangible asset base.

Honest-failure contracts that are NOT changed by the fix:

* legacy/sample_data/sample_data.csv (TEBE) is NOT balanced at source (Attivo
  615,000 != Passivo 645,000 — a 30,000 gap baked into the committed data; the
  sibling sample_data.xbrl encodes the same numbers and fails identically).
  import_csv_file must still refuse it (CSVImportError "BILANCIO NON QUADRATO"),
  not import a silently-plugged sheet.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from importers.iv_cee_hierarchy import check_quadratura
from tests.e2e_kit import memory_sessions, read_forecast_maps

REPO = Path(__file__).resolve().parents[1]
XBRL_FIXTURE = REPO / "legacy" / "sample_data" / "ISTANZA02353550391.xbrl"
CSV_FIXTURE = REPO / "legacy" / "sample_data" / "sample_data.csv"
USER = "route-xbrl-csv"

# A minimal, internally-consistent single-year itcc-ci-2018-11-04 XBRL instance.
# Attivo = Passivo = 150,000 (immob.immat 30,000 + immob.mat 90,000 + cassa
# 30,000 = capitale 100,000 + utile 20,000 + TFR 30,000). The income statement
# independently derives the same 20,000 net profit via calculations.ce_result,
# so the CE<->SP identity check_quadratura performs also holds.
_SYNTHETIC_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:itcc-ci="http://www.infocamere.it/itnn/fr/itcc/ci/2018-11-04" xmlns:itcc-ci-ese="http://www.infocamere.it/itnn/fr/itcc/ci/ese/2018-11-04" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.xbrl.org/2003/instance" xsi:schemaLocation="http://xbrl.org/2006/xbrldi http://www.xbrl.org/2006/xbrldi-2006.xsd">
  <link:schemaRef xlink:href="itcc-ci-ese-2018-11-04.xsd" xlink:type="simple" />
  <context id="I_20301231">
    <entity>
      <identifier scheme="http://www.infocamere.it">99999999999</identifier>
    </entity>
    <period>
      <instant>2030-12-31</instant>
    </period>
  </context>
  <context id="D_20301231">
    <entity>
      <identifier scheme="http://www.infocamere.it">99999999999</identifier>
    </entity>
    <period>
      <startDate>2030-01-01</startDate>
      <endDate>2030-12-31</endDate>
    </period>
  </context>
  <unit id="EUR"><measure>iso4217:EUR</measure></unit>

  <itcc-ci:DatiAnagraficiDenominazione contextRef="I_20301231">SYNTHETIC XBRL TEST SRL</itcc-ci:DatiAnagraficiDenominazione>
  <itcc-ci:DatiAnagraficiCodiceFiscale contextRef="I_20301231">99999999999</itcc-ci:DatiAnagraficiCodiceFiscale>

  <itcc-ci:TotaleImmobilizzazioniImmateriali contextRef="I_20301231" decimals="0" unitRef="EUR">30000</itcc-ci:TotaleImmobilizzazioniImmateriali>
  <itcc-ci:TotaleImmobilizzazioniMateriali contextRef="I_20301231" decimals="0" unitRef="EUR">90000</itcc-ci:TotaleImmobilizzazioniMateriali>
  <itcc-ci:TotaleDisponibilitaLiquide contextRef="I_20301231" decimals="0" unitRef="EUR">30000</itcc-ci:TotaleDisponibilitaLiquide>

  <itcc-ci:PatrimonioNettoCapitale contextRef="I_20301231" decimals="0" unitRef="EUR">100000</itcc-ci:PatrimonioNettoCapitale>
  <itcc-ci:PatrimonioNettoUtilePerditaEsercizio contextRef="I_20301231" decimals="0" unitRef="EUR">20000</itcc-ci:PatrimonioNettoUtilePerditaEsercizio>
  <itcc-ci:TrattamentoFineRapportoLavoroSubordinato contextRef="I_20301231" decimals="0" unitRef="EUR">30000</itcc-ci:TrattamentoFineRapportoLavoroSubordinato>

  <itcc-ci:ValoreProduzioneRicaviVenditePrestazioni contextRef="D_20301231" decimals="0" unitRef="EUR">200000</itcc-ci:ValoreProduzioneRicaviVenditePrestazioni>
  <itcc-ci:CostiProduzioneServizi contextRef="D_20301231" decimals="0" unitRef="EUR">100000</itcc-ci:CostiProduzioneServizi>
  <itcc-ci:CostiProduzioneGodimentoBeniTerzi contextRef="D_20301231" decimals="0" unitRef="EUR">10000</itcc-ci:CostiProduzioneGodimentoBeniTerzi>
  <itcc-ci:CostiProduzionePersonaleTotaleCostiPersonale contextRef="D_20301231" decimals="0" unitRef="EUR">50000</itcc-ci:CostiProduzionePersonaleTotaleCostiPersonale>
  <itcc-ci:CostiProduzioneOneriDiversiGestione contextRef="D_20301231" decimals="0" unitRef="EUR">5000</itcc-ci:CostiProduzioneOneriDiversiGestione>
  <itcc-ci:ProventiOneriFinanziariInteressiAltriOneriFinanziariTotaleInteressiAltriOneriFinanziari contextRef="D_20301231" decimals="0" unitRef="EUR">5000</itcc-ci:ProventiOneriFinanziariInteressiAltriOneriFinanziariTotaleInteressiAltriOneriFinanziari>
  <itcc-ci:ImposteRedditoEsercizioCorrentiDifferiteAnticipateTotaleImposteRedditoEsercizioCorrentiDifferiteAnticipate contextRef="D_20301231" decimals="0" unitRef="EUR">10000</itcc-ci:ImposteRedditoEsercizioCorrentiDifferiteAnticipateTotaleImposteRedditoEsercizioCorrentiDifferiteAnticipate>
</xbrl>
"""

# A TEBE CSV carrying REAL working capital and depreciation, published only as
# aggregates (the TEBE schema has no typed sub-fields). Attivo = Passivo =
# 440,000 (immat 20,000 + mat 180,000 + rimanenze 60,000 + crediti 140,000 +
# cassa 40,000 = capitale 100,000 + riserve 80,000 + utile 20,000 + TFR 30,000 +
# debiti breve 150,000 + debiti lungo 60,000). Net profit 20,000 = ricavi 600,000
# - materie 200,000 - servizi 150,000 - personale 120,000 - ammortamenti 40,000 -
# oneri diversi 42,000 - godimento 4,000 - imposte 24,000 = sp13 20,000.
# reconcile_source_detail at import fills sp05e/sp06g/sp16g/sp17g/sp12e and
# splits ce09 into ce09a (immateriali) / ce09b (materiali), so the year clears
# the forecast engine's aggregate/detail gate.
_SYNTHETIC_CSV = """BILANCIO ESERCIZIO;Anno 2030;Anno 2029;Tag;Euro
Dati anagrafici;;;;
Crediti verso soci;0;0;SP01;€
Immobilizzazioni immateriali;20 000;20 000;SP02;€
Immobilizzazioni materiali;180 000;180 000;SP03;€
Immobilizzazioni finanziarie;0;0;SP04;€
Rimanenze;60 000;60 000;SP05;€
Crediti - esigibili entro;140 000;140 000;SP06;€
Crediti - esigibili oltre;0;0;SP07;€
Attività finanziarie;0;0;SP08;€
Disponibilità liquide;40 000;40 000;SP09;€
Ratei e risconti attivi;0;0;SP10;€
Capitale;100 000;100 000;SP11;€
Riserve;80 000;80 000;SP12;€
Utile (perdita);20 000;20 000;SP13;€
Fondi per rischi;0;0;SP14;€
Trattamento di fine rapporto;30 000;30 000;SP15;€
Debiti - esigibili entro;150 000;150 000;SP16;€
Debiti - esigibili oltre;60 000;60 000;SP17;€
Ratei e risconti passivi;0;0;SP18;€
Ricavi delle vendite;600 000;600 000;CE01;€
Variazioni delle rimanenze;0;0;CE02;€
Incrementi di immobilizzazioni;0;0;CE03;€
Altri ricavi e proventi;0;0;CE04;€
Materie prime;200 000;200 000;CE05;€
Servizi;150 000;150 000;CE06;€
Godimento di beni;4 000;4 000;CE07;€
Costi per il personale;120 000;120 000;CE08;€
Ammortamenti;40 000;40 000;CE09;€
Variazioni delle rimanenze di materie;0;0;CE10;€
Accantonamenti;0;0;CE11;€
Oneri diversi;42 000;42 000;CE12;€
Proventi da partecipazioni;0;0;CE13;€
Altri proventi finanziari;0;0;CE14;€
Interessi e altri oneri finanziari;0;0;CE15;€
Utili e perdite su cambi;0;0;CE16;€
Rettifiche di valore;0;0;CE17;€
Proventi straordinari;0;0;CE18;€
Oneri straordinari;0;0;CE19;€
Imposte;24 000;24 000;CE20;€
"""


def _run_budget_cycle(db, company_id, base_year):
    """Create a budget scenario, generate a 2-year forecast and verify it.

    Mirrors the assertions of the PDF-route matrix test
    (tests/test_standard_ivcee_parser.py): every forecast year must balance
    exactly, and check_quadratura must consider it semantically valid (the
    single source of truth for CE<->SP consistency).
    """
    scenario = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name=f"budget {base_year}",
                             base_year=base_year, scenario_type="budget"),
        user_id=USER, db=db,
    )
    result = budget_scenarios.bulk_upsert_assumptions(
        company_id, scenario.id,
        request={"assumptions": [
            {"forecast_year": base_year + 1, "revenue_growth_pct": 5, "tax_rate": 24},
            {"forecast_year": base_year + 2, "revenue_growth_pct": 3, "tax_rate": 24},
        ], "auto_generate": True},
        user_id=USER, db=db,
    )
    assert result["forecast_generated"] is True, result["message"]
    rows = read_forecast_maps(db, scenario.id)
    assert len(rows) == 2
    for _year, bs, ce in rows:
        assert bs["_total_assets"] == bs["_total_liabilities"]
        validation = check_quadratura(bs, ce)
        assert validation.semantic_valid, validation.warnings
    return scenario


def test_xbrl_route_full_cycle(monkeypatch, tmp_path):
    """A real deposited abbreviato XBRL now imports, balances AND forecasts.

    Before reconcile_source_detail, the source's aggregate-only
    sp04_immob_finanziarie / sp14_fondi_rischi failed the forecast gate. Now the
    remainder is booked into each family's "altri" bucket at import, so the full
    2-year budget cycle runs. The happy path is additionally exercised on a
    synthetic self-consistent XBRL over the same route/DB.
    """
    from database.models import FinancialYear
    from importers import xbrl_parser_enhanced

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    monkeypatch.setattr(xbrl_parser_enhanced, "SessionLocal", sessions)
    try:
        result = xbrl_parser_enhanced.import_xbrl_file_enhanced(
            str(XBRL_FIXTURE), create_company=True, sector=1, user_id=USER
        )
        assert result["success"] is True, result
        with sessions() as db:
            fy = (
                db.query(FinancialYear)
                .order_by(FinancialYear.year.desc())
                .first()
            )
            assert fy is not None
            bs = fy.balance_sheet
            assert bs.total_assets == bs.total_liabilities
            assert bs.total_assets > 0

            # The fix: the aggregate-only sp04/sp14 were reconciled into their
            # "altri" bucket at import, so the family now reconstructs the
            # aggregate and the year is forecastable.
            assert (
                (bs.sp04d_altri_titoli or Decimal("0"))
                + (bs.sp04a_partecipazioni or Decimal("0"))
                + (bs.sp04b_crediti_immob_breve or Decimal("0"))
                + (bs.sp04c_crediti_immob_lungo or Decimal("0"))
                + (bs.sp04e_strumenti_derivati_attivi or Decimal("0"))
                == bs.sp04_immob_finanziarie
            )
            # The whole real-world 2-year budget cycle now completes.
            _run_budget_cycle(db, fy.company_id, fy.year)

        # A synthetic, fully self-consistent XBRL over the same route/DB also
        # completes the whole import -> scenario -> forecast cycle.
        synthetic_path = tmp_path / "synthetic.xbrl"
        synthetic_path.write_text(_SYNTHETIC_XBRL, encoding="utf-8")
        synth_result = xbrl_parser_enhanced.import_xbrl_file_enhanced(
            str(synthetic_path), create_company=True, sector=1, user_id=USER
        )
        assert synth_result["success"] is True, synth_result
        with sessions() as db:
            synth_fy = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == synth_result["company_id"])
                .order_by(FinancialYear.year.desc())
                .first()
            )
            assert synth_fy is not None
            synth_bs = synth_fy.balance_sheet
            assert synth_bs.total_assets == synth_bs.total_liabilities
            assert synth_bs.total_assets == Decimal("150000.00")
            _run_budget_cycle(db, synth_fy.company_id, synth_fy.year)
    finally:
        engine.dispose()


def test_csv_route_full_cycle(monkeypatch, tmp_path):
    """A TEBE CSV with real working capital and depreciation now forecasts.

    The committed sample_data.csv is unbalanced at source and must still be
    refused honestly. The happy path then runs on a synthetic TEBE CSV that
    carries non-zero rimanenze/crediti/debiti/ammortamenti (aggregates only) —
    reconcile_source_detail fills the "altri" buckets and splits ce09 at import,
    so the year clears the forecast gate and the 2-year budget cycle completes.
    """
    from database.models import Company, FinancialYear
    from importers import csv_importer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    monkeypatch.setattr(csv_importer, "SessionLocal", sessions)
    try:
        with sessions() as db:
            company = Company(name="CSV ROUTE SRL", tax_id="CSV1", sector=1,
                              user_id=USER)
            db.add(company)
            db.commit()
            company_id = company.id

        # Honest contract (unchanged by the fix): the committed sample CSV does
        # not balance at the source, so the importer must refuse it rather than
        # import a plugged/unbalanced balance sheet.
        with pytest.raises(csv_importer.CSVImportError) as excinfo:
            csv_importer.import_csv_file(str(CSV_FIXTURE), company_id)
        assert "BILANCIO NON QUADRATO" in str(excinfo.value)

        # Happy path: a TEBE CSV with real WC + depreciation (aggregates only)
        # now imports, has its detail reconciled, and forecasts end-to-end.
        with sessions() as db:
            synth_company = Company(name="CSV SYNTH SRL", tax_id="CSVSYNTH",
                                    sector=1, user_id=USER)
            db.add(synth_company)
            db.commit()
            synth_company_id = synth_company.id

        synthetic_path = tmp_path / "synthetic.csv"
        synthetic_path.write_text(_SYNTHETIC_CSV, encoding="utf-8")
        synth_result = csv_importer.import_csv_file(str(synthetic_path), synth_company_id)
        assert synth_result["success"] is True, synth_result
        with sessions() as db:
            fy = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == synth_company_id)
                .order_by(FinancialYear.year.desc())
                .first()
            )
            assert fy is not None
            bs = fy.balance_sheet
            assert bs.total_assets == bs.total_liabilities
            assert bs.total_assets == Decimal("440000.00")
            # The reconcile booked the aggregate-only detail into "altri" buckets
            # at import (proof the fix ran on the CSV route).
            assert bs.sp05e_acconti == Decimal("60000.00")
            assert bs.sp06g_crediti_altri_breve == Decimal("140000.00")
            assert bs.sp16g_altri_debiti_breve == Decimal("150000.00")
            # ce09 split proportional to the 20k/180k intangible/tangible base.
            inc = fy.income_statement
            assert inc.ce09a_ammort_immateriali == Decimal("4000.00")
            assert inc.ce09b_ammort_materiali == Decimal("36000.00")
            _run_budget_cycle(db, synth_company_id, fy.year)
    finally:
        engine.dispose()
