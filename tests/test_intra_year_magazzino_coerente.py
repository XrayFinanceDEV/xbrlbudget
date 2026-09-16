"""La variazione di magazzino a conto economico discende dal movimento dello
stato patrimoniale (decisione del proprietario, 2026-09-16).

Prima le due grandezze non si parlavano: lo stato patrimoniale portava il
magazzino dove lo stimava il rapporto di rotazione, il conto economico
annualizzava la variazione del parziale, e la differenza — 43.353 € su AMBIENTA
2026/6M — spariva nel tappo di cassa senza che nulla la dichiarasse.
"""
from decimal import Decimal as D

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)


def _proiezione(*, riferimento, parziale, ipotesi=None):
    """Riferimento 2024 pieno + parziale 2025 a 9 mesi, settore Industria.

    Il rapporto di rotazione è volutamente degenere (magazzino oltre l'anno di
    acquisti): la giacenza osservata viene riportata, quindi il magazzino di
    chiusura è un numero noto e il test misura la VARIAZIONE, non la stima.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Magazzino coerente", tax_id="MAGAZZINO-COERENTE", sector=1)
    db.add(azienda)
    db.flush()
    for anno, mesi, stato, conto in (
        (2024, None, riferimento, dict(ce05_materie_prime=D("40000"), ce01_ricavi_vendite=D("200000"))),
        (2025, 9, parziale, dict(ce05_materie_prime=D("30000"), ce01_ricavi_vendite=D("150000"))),
    ):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             **(ipotesi or {})))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    anno = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one()
    return anno.balance_sheet, anno.income_statement, esito["diagnostics"]


# Riferimento: 100.000 di magazzino (60.000 materie + 40.000 lavori in corso).
_RIF = dict(sp05_rimanenze=D("100000"), sp05a_materie_prime=D("60000"), sp05c_lavori_in_corso=D("40000"),
            sp11_capitale=D("200000"), sp13_utile_perdita=D("160000"), sp09_disponibilita_liquide=D("260000"))
# Parziale: 130.000 (91.000 materie + 39.000 lavori in corso).
_PAR = dict(sp05_rimanenze=D("130000"), sp05a_materie_prime=D("91000"), sp05c_lavori_in_corso=D("39000"),
            sp11_capitale=D("200000"), sp13_utile_perdita=D("120000"), sp09_disponibilita_liquide=D("190000"))


def test_la_variazione_segue_il_movimento_voce_per_voce():
    sp, ce, _ = _proiezione(riferimento=_RIF, parziale=_PAR)
    assert sp.sp05_rimanenze == D("130000.00")
    # Materie 60.000 → 91.000: +31.000, che a conto economico è un costo NEGATIVO.
    # Lavori in corso 40.000 → 39.000: −1.000, che è un ricavo negativo.
    assert ce.ce10_var_rimanenze_mat_prime == D("-31000.00")
    assert ce.ce02_variazioni_rimanenze == D("-1000.00")
    # E insieme spiegano tutto il movimento: nulla resta da assorbire alla cassa.
    movimento = sp.sp05_rimanenze - _RIF["sp05_rimanenze"]
    assert ce.ce02_variazioni_rimanenze - ce.ce10_var_rimanenze_mat_prime == movimento


def test_la_composizione_viene_dal_parziale_non_dal_riferimento():
    """Il riferimento porta solo l'aggregato (il caso normale: 98% dei bilanci
    annuali non ha il dettaglio). Prendendo la composizione da lì, le sotto-voci
    del magazzino proiettato uscivano tutte a zero."""
    sp, _ce, _ = _proiezione(
        riferimento=dict(sp05_rimanenze=D("100000"), sp11_capitale=D("200000"),
                         sp13_utile_perdita=D("160000"), sp09_disponibilita_liquide=D("260000")),
        parziale=_PAR,
    )
    assert (sp.sp05a_materie_prime, sp.sp05c_lavori_in_corso) == (D("91000.00"), D("39000.00"))


def test_senza_composizione_da_nessuna_parte_si_divide_a_meta_e_si_dichiara():
    sp, ce, diagnostici = _proiezione(
        riferimento=dict(sp05_rimanenze=D("100000"), sp11_capitale=D("200000"),
                         sp13_utile_perdita=D("160000"), sp09_disponibilita_liquide=D("260000")),
        parziale=dict(sp05_rimanenze=D("130000"), sp11_capitale=D("200000"),
                      sp13_utile_perdita=D("120000"), sp09_disponibilita_liquide=D("190000")),
    )
    assert sp.sp05_rimanenze == D("130000.00")
    assert ce.ce10_var_rimanenze_mat_prime == D("-15000.00")
    assert ce.ce02_variazioni_rimanenze == D("15000.00")
    dichiarazioni = [d for d in diagnostici if d["code"] == "variazione_magazzino_ripartita_a_meta"]
    assert len(dichiarazioni) == 1
    assert "30.000,00" in dichiarazioni[0]["message"]


def test_un_override_vince_e_lo_scarto_si_dichiara():
    """L'override di CE resta l'ultima parola dell'utente, come su ogni altra
    riga — ma allora il conto economico torna a non spiegare il magazzino, e
    quella differenza va detta, non corretta di nascosto."""
    sp, ce, diagnostici = _proiezione(riferimento=_RIF, parziale=_PAR,
                                      ipotesi=dict(ce10_override=D("5000")))
    assert ce.ce10_var_rimanenze_mat_prime == D("5000.00")
    assert sp.sp05_rimanenze == D("130000.00")
    dichiarazioni = [d for d in diagnostici if d["code"] == "variazione_magazzino_forzata"]
    assert len(dichiarazioni) == 1
    # 5.000 forzati contro i −31.000 dedotti: 36.000 senza contropartita.
    assert dichiarazioni[0]["amount"] == "36000.00"


def test_un_magazzino_fermo_non_scrive_nessuna_variazione():
    fermo = dict(sp05_rimanenze=D("100000"), sp05a_materie_prime=D("60000"), sp05c_lavori_in_corso=D("40000"),
                 sp11_capitale=D("200000"), sp13_utile_perdita=D("120000"), sp09_disponibilita_liquide=D("220000"))
    _sp, ce, diagnostici = _proiezione(riferimento=_RIF, parziale=fermo)
    assert (ce.ce10_var_rimanenze_mat_prime, ce.ce02_variazioni_rimanenze) == (D("0.00"), D("0.00"))
    assert not [d for d in diagnostici
                if d["code"] in ("variazione_magazzino_forzata", "variazione_magazzino_ripartita_a_meta")]
