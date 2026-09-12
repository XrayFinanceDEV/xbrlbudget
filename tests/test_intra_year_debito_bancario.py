"""L'infrannuale separa il debito bancario pregresso dal prestito nuovo, con la quota a breve (lotto 3A, Task 4).

Oggi la prima rata di un prestito nuovo azzera il pregresso a breve: con 12.345,67 di pregresso e un prestito di
120.000 / 4 anni / 5% erogato nell'anno, `sp16a` 0,00 e `sp17a` 102.345,67. Dopo: il pregresso resta, il prestito
nuovo mette a breve la rata dell'anno dopo (30.000,00) e a lungo il resto (60.000,00).
"""
from decimal import ROUND_HALF_UP, Decimal as D
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

BREVE = D("12345.67")
NUOVO = dict(financing_amount=D("120000"), financing_duration_years=D("4"), financing_interest_rate=D("5"))
MISTO = [{"name": "Misto", "amount": 120000, "opening_residual": 12345.67, "duration_years": 4, "interest_rate": 5}]
DUE_RIGHE = [
    {"name": "Nuovo", "amount": 120000, "opening_residual": 0, "duration_years": 4, "interest_rate": 5},
    {"name": "Pregresso", "amount": 0, "opening_residual": 12345.67, "duration_years": 4, "interest_rate": 5},
]


def _q(x):
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _base():
    campi = {f: D("0") for f in (
        "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
        "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve",
        "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
        "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
        "sp17g_altri_debiti_lungo", "sp17_debiti_lungo")}
    return SimpleNamespace(sp16a_debiti_banche_breve=BREVE, sp16_debiti_breve=BREVE, **campi)


def _ipotesi(**extra):
    valori = dict(forecast_year=2027, financing_amount=D("0"), financing_duration_years=D("0"),
                  financing_interest_rate=D("0"), financing_loans=None, existing_debt_repayment_years=None,
                  altri_finanz_repayment_years=None)
    valori.update(extra)
    return SimpleNamespace(**valori)


def _rimborso(**extra):
    motore = IntraYearEngine.__new__(IntraYearEngine)
    sp16a, sp17a, sp17b = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**extra))
    return _q(sp16a), _q(sp17a), _q(sp17b)


def test_la_rata_del_prestito_nuovo_non_consuma_il_pregresso_a_breve():
    assert _rimborso(**NUOVO) == (D("42345.67"), D("60000.00"), D("0.00"))


@pytest.mark.parametrize("prestiti", [MISTO, DUE_RIGHE], ids=["contratto misto", "due righe"])
def test_il_contratto_misto_e_le_due_righe_danno_gli_stessi_numeri_giusti(prestiti):
    # Pregresso: rata 12.345,67 / 4 = 3.086,4175 dal breve → 9.259,2525; nuovo: 30.000,00 a breve, 60.000,00 a lungo.
    assert _rimborso(financing_loans=prestiti) == (D("39259.25"), D("60000.00"), D("0.00"))


@pytest.mark.parametrize("piano", [{}, {"existing_debt_repayment_years": D("3")}], ids=["senza piano", "anni di rimborso 3"])
def test_i1_esteso_la_componente_pregressa_e_la_stessa_con_e_senza_prestito_nuovo(piano):
    motore = IntraYearEngine.__new__(IntraYearEngine)
    senza = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**piano))
    con = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**piano, **NUOVO))
    assert _q(con[0] - D("30000.00")) == _q(senza[0])
    assert _q(con[1] - D("60000.00")) == _q(senza[1])


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _proietta(**ipotesi):
    db = _sessione()
    azienda = Company(name="Banca infra", tax_id="BANCA-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    stato = dict(sp09_disponibilita_liquide=D("201000"), sp11_capitale=D("188654.33"),
                 sp16_debiti_breve=BREVE, sp16a_debiti_banche_breve=BREVE)
    for anno, mesi in ((2024, None), (2025, 9)):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp.sp16a_debiti_banche_breve, sp.sp17a_debiti_banche_lungo, sp.sp09_disponibilita_liquide


@pytest.mark.parametrize("ipotesi, attesi", [
    ({}, ("12345.67", "0.00", "201000.00")),
    (NUOVO, ("42345.67", "60000.00", "285000.00")),
    ({"financing_loans": MISTO}, ("39259.25", "60000.00", "281296.30")),
    ({"financing_loans": DUE_RIGHE}, ("39259.25", "60000.00", "281296.30")),
], ids=["solo pregresso", "prestito nuovo", "contratto misto", "due righe"])
def test_la_proiezione_persiste_la_ripartizione_e_la_cassa_non_cambia(ipotesi, attesi):
    """Oggi: prestito nuovo 0,00 / 102.345,67, misto e due righe 0,00 / 99.259,25; cassa 285.000,00 e 281.296,30."""
    assert _proietta(**ipotesi) == tuple(D(v) for v in attesi)


def _stato_sp16(**over):
    """Stato patrimoniale minimo per i tre test nuovi (indagine-1-debito-bancario.md):
    solo i campi di sp16/sp17 e il minimo per far quadrare Attivo=Passivo (sp09, sp11)."""
    zero = D("0")
    base = dict(
        sp16_debiti_breve=zero, sp16a_debiti_banche_breve=zero, sp16b_debiti_altri_finanz_breve=zero,
        sp16c_debiti_obbligazioni_breve=zero, sp16d_debiti_fornitori_breve=zero, sp16e_debiti_tributari_breve=zero,
        sp16f_debiti_previdenza_breve=zero, sp16g_altri_debiti_breve=zero,
        sp17_debiti_lungo=zero, sp17a_debiti_banche_lungo=zero, sp17b_debiti_altri_finanz_lungo=zero,
        sp17c_debiti_obbligazioni_lungo=zero, sp17d_debiti_fornitori_lungo=zero, sp17e_debiti_tributari_lungo=zero,
        sp17f_debiti_previdenza_lungo=zero, sp17g_altri_debiti_lungo=zero,
        sp09_disponibilita_liquide=D("500000"), sp11_capitale=D("100000"),
    )
    base.update(over)
    return base


def _proietta_con_riferimento(stato_riferimento, stato_parziale, **ipotesi):
    """Come _proietta, ma con uno stato patrimoniale DIVERSO per l'anno di
    riferimento (2024, pieno) e per il parziale (2025, 9 mesi) -- _proietta usa
    lo stesso stato per entrambi, quindi non puo' esercitare la ripartizione
    reference vs. partial che ha causato indagine-1-debito-bancario.md."""
    db = _sessione()
    azienda = Company(name="Banca infra 2", tax_id="BANCA-INFRA-2", sector=1)
    db.add(azienda)
    db.flush()
    fy_ref = FinancialYear(company_id=azienda.id, year=2024, period_months=None,
                           validation_status="verified", forecastable=True)
    db.add(fy_ref); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_ref.id, **stato_riferimento))
    db.add(IncomeStatement(financial_year_id=fy_ref.id))
    fy_par = FinancialYear(company_id=azienda.id, year=2025, period_months=9,
                           validation_status="verified", forecastable=True)
    db.add(fy_par); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_par.id, **stato_parziale))
    db.add(IncomeStatement(financial_year_id=fy_par.id))
    scenario = BudgetScenario(company_id=azienda.id, name="infra2", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario); db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    result = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp, result['diagnostics']


def test_il_debito_bancario_si_porta_avanti_dal_parziale_quando_il_riferimento_non_ha_dettaglio():
    """indagine-1-debito-bancario.md: un riferimento senza dettaglio finanziario
    (tutto sp16g, il 98% dei bilanci annuali del database) NON deve azzerare il
    debito bancario reale del parziale. Prima della correzione: sp16a 0,00."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16g_altri_debiti_breve=D("100000"),
                       sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("50000"), sp16a_debiti_banche_breve=D("30000"),
                            sp16d_debiti_fornitori_breve=D("20000"), sp09_disponibilita_liquide=D("150000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale)
    assert sp.sp16a_debiti_banche_breve == D("30000.00")
    assert sp.sp16_debiti_breve == D("50000.00")
    codici = [d['code'] for d in diagnostics]
    assert 'reference_financial_debt_undetailed' in codici
    diag = next(d for d in diagnostics if d['code'] == 'reference_financial_debt_undetailed')
    assert diag['aggregate'] == 'sp16'
    assert diag['severity'] == 'warning'
    assert diag['fields'] == {'sp16a_debiti_banche_breve': '30000.00'}


def test_nessuna_regressione_quando_il_riferimento_ha_dettaglio_bancario():
    """Il caso "che funziona" di indagine-1 (fase 2, azienda 21/scenario 4): il
    riferimento ha una propria quota bancaria, diversa da quella del parziale.
    Prima della correzione la quota veniva comunque RISCALATA sulla proporzione
    del riferimento (40% del totale, qui 32.000,00); dopo, il debito bancario
    prende il valore ESATTO del parziale (25.000,00), mai una proporzione presa
    da un anno diverso."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16a_debiti_banche_breve=D("40000"),
                       sp16d_debiti_fornitori_breve=D("60000"), sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("80000"), sp16a_debiti_banche_breve=D("25000"),
                            sp16d_debiti_fornitori_breve=D("55000"), sp09_disponibilita_liquide=D("180000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale)
    assert sp.sp16a_debiti_banche_breve == D("25000.00")
    assert not any(d['code'] == 'reference_financial_debt_undetailed' for d in diagnostics)


def test_il_debito_bancario_scende_della_rata_non_della_rotazione():
    """Riferimento senza dettaglio finanziario + piano di rimborso attivo
    (existing_debt_repayment_years=5): il debito bancario del parziale
    (100.000,00) scende della RATA (100.000,00/5=20.000,00), non della
    proporzione del riferimento (che lo azzererebbe)."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16g_altri_debiti_breve=D("100000"),
                       sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("120000"), sp16a_debiti_banche_breve=D("100000"),
                            sp16d_debiti_fornitori_breve=D("20000"), sp09_disponibilita_liquide=D("220000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale, existing_debt_repayment_years=D("5"))
    assert sp.sp16a_debiti_banche_breve == D("80000.00")
    assert any(d['code'] == 'reference_financial_debt_undetailed' for d in diagnostics)
