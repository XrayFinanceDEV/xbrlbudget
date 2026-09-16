"""Al 31/12 l'infrannuale lascia il saldo d'imposta dell'anno (lotto 3A, Task 5, decisione 4 del
proprietario) PIÙ il credito tributario aperto alla data del parziale, che dal 2026-09-16 non si
assume più incassato entro l'anno: gonfiava la cassa proiettata di un importo che nessuno aveva
deciso. Il debito aperto continua invece a uscire di cassa."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import calculations.projection_common as comune
from backend.app.services import assumptions_service, forecast_preview_service
from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

APERTURA = D("1150949.04")


def _kernel():
    fn = getattr(comune, "posizione_tributaria_fine_anno", None)
    assert callable(fn), "projection_common.posizione_tributaria_fine_anno non esiste"
    return fn


def test_i_numeri_della_sonda_sono_quelli_del_kernel_budget():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("0"), explicit_advances=D("99247.26"))
    assert (p.closing_debt, p.closing_credit, p.acconti, p.cash_out) == (
        D("20752.74"), D("0"), D("99247.26"), D("1250196.30"))
    budget = comune.tax_settlement_saldo_acconto(opening_credit=0, saldo_due=APERTURA, rate_due=0,
                                                 current_tax=D("120000"), previous_tax=0, acconto_pct=D("100"),
                                                 explicit_advances=D("99247.26"))
    assert (budget.generated_debt, budget.cash_out) == (p.closing_debt, p.cash_out)


@pytest.mark.parametrize("dichiarati", [D("0"), D("-5")], ids=["zero", "negativo"])
def test_acconti_non_dichiarati_valgono_il_cento_per_cento_dell_imposta_di_riferimento(dichiarati):
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("80000"), explicit_advances=dichiarati)
    assert (p.acconti, p.closing_debt, p.cash_out) == (D("80000"), D("40000"), D("1230949.04"))


def test_una_posizione_negativa_diventa_credito():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("150000"), explicit_advances=0)
    assert (p.closing_credit, p.closing_debt, p.cash_out) == (D("30000"), D("0"), D("1300949.04"))


def test_il_credito_di_apertura_e_l_imposta_gia_maturata_non_si_ripagano():
    con_credito = _kernel()(opening_credit=D("50000"), opening_debt=0, remaining_current_tax=D("120000"),
                            current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (con_credito.closing_debt, con_credito.cash_out) == (D("20752.74"), D("49247.26"))
    maturata = _kernel()(opening_credit=0, opening_debt=D("30000"), remaining_current_tax=D("30000"),
                         current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (maturata.closing_debt, maturata.cash_out) == (D("20752.74"), D("39247.26"))


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _infrannuale(db, imposta_riferimento, acconti):
    """Riferimento 2024 con imposta R e 1.000.000 di debito tributario; parziale 2025 (9 mesi) con 1.150.949,04."""
    azienda = Company(name="Imposte infra", tax_id="IMPOSTE-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    anni = (
        (2024, None, dict(sp11_capitale=D("1000"), sp13_utile_perdita=-imposta_riferimento,
                          sp16_debiti_breve=D("1000000"), sp16e_debiti_tributari_breve=D("1000000"),
                          sp09_disponibilita_liquide=D("1000") - imposta_riferimento + D("1000000")),
         dict(ce20_imposte=imposta_riferimento)),
        (2025, 9, dict(sp11_capitale=D("2000000"), sp13_utile_perdita=D("0"), sp16_debiti_breve=APERTURA,
                       sp16e_debiti_tributari_breve=APERTURA, sp09_disponibilita_liquide=D("2000000") + APERTURA), {}),
    )
    for anno, mesi, stato, conto in anni:
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
                             ce20_override=D("120000"), tax_advances_paid=acconti))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    return azienda, scenario


@pytest.mark.parametrize("riferimento, acconti, attesi", [
    (D("80000"), D("0"), ("40000.00", "0.00", "1920000.00")),
    (D("150000"), D("0"), ("0.00", "30000.00", "1850000.00")),
    (D("80000"), D("99247.26"), ("20752.74", "0.00", "1900752.74")),
], ids=["acconti non dichiarati", "posizione a credito", "acconti dichiarati"])
def test_la_proiezione_persiste_il_solo_saldo_e_paga_il_resto_di_cassa(riferimento, acconti, attesi):
    db = _sessione()
    _azienda, scenario = _infrannuale(db, riferimento, acconti)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    assert (sp.sp16e_debiti_tributari_breve, sp.sp06e_crediti_tributari_breve, sp.sp09_disponibilita_liquide) == tuple(
        D(v) for v in attesi)


def test_il_budget_nato_dal_promote_non_eredita_il_debito_dell_anno_prima():
    db = _sessione()
    azienda, scenario = _infrannuale(db, D("80000"), D("99247.26"))
    promote_projection_to_financial_year(db, scenario.id)
    budget = BudgetScenario(company_id=azienda.id, name="budget", base_year=2025, scenario_type="budget")
    db.add(budget)
    db.commit()
    righe = [{"forecast_year": 2026, "revenue_growth_pct": 0, "tax_rate": 27.9}]
    esito = assumptions_service.bulk_upsert_assumptions(db, budget.id, [dict(r) for r in righe], auto_generate=True)
    assert esito["forecast_generated"] is True, esito["message"]
    anteprima = forecast_preview_service.preview_forecast(db, budget.id, [dict(r) for r in righe])
    assert D(str(anteprima["forecast_years"][0]["details"]["imposte"]["saldo_paid"])) == D("20752.74")


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 (ondata finale di correzioni) — il conguaglio fiscale è un flusso
# dichiarato, e la sua contropartita è il lato che si è davvero mosso.
#
# La fixture `_infrannuale` qui sopra concentra TUTTO `sp16` in `sp16e`, quindi la
# quota-riferimento che la rotation posa su `sp16e` coincide col vero debito di
# apertura del parziale: su quel fixture il conguaglio vale zero PRIMA e DOPO, e
# non dimostrerebbe nulla. I casi sotto variano quella quota a parità di
# `cash_out`, che è la sola cosa che la cassa deve registrare.
#
# Le rotazioni del ramo col riferimento sono volutamente a rapporto 1 (costi del
# riferimento = costi proiettati, crescita 0): così `x` è esattamente il
# `sp16e` del riferimento e ogni importo è calcolabile a mano.
# ─────────────────────────────────────────────────────────────────────────────

_RIF_COSTI = D("1000000")          # ce01 = ce05: utile del riferimento a zero
_SP16_DETAIL = ('sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                'sp16g_altri_debiti_breve')
_SP17_DETAIL = ('sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                'sp17g_altri_debiti_lungo')
_SP06_DETAIL = ('sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                'sp06g_crediti_altri_breve')
_SP07_DETAIL = ('sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                'sp07g_crediti_altri_lungo')
_ATTIVO = ('sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
           'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
           'sp07_crediti_lungo', 'sp08_attivita_finanziarie', 'sp10_ratei_risconti_attivi')
_PASSIVO = ('sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita', 'sp14_fondi_rischi',
            'sp15_tfr', 'sp16_debiti_breve', 'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi')


def _stato(**campi):
    """Stato patrimoniale minimo che quadra: gli aggregati sono la somma dei loro
    dettagli (su `sp16`/`sp17` il motore la pretende: `_validate_forecast_source`)
    e `sp09` è il plug, calcolato qui perché la fonte non ne abbia uno suo."""
    d = {k: D(str(v)) for k, v in campi.items()}
    for agg, dettagli in (('sp16_debiti_breve', _SP16_DETAIL), ('sp17_debiti_lungo', _SP17_DETAIL),
                          ('sp06_crediti_breve', _SP06_DETAIL), ('sp07_crediti_lungo', _SP07_DETAIL)):
        d[agg] = sum((d.get(f, D('0')) for f in dettagli), D('0'))
    d.setdefault('sp11_capitale', D('1000'))
    d.setdefault('sp13_utile_perdita', D('0'))
    attivo = sum((d.get(f, D('0')) for f in _ATTIVO), D('0'))
    passivo = sum((d.get(f, D('0')) for f in _PASSIVO), D('0'))
    d['sp09_disponibilita_liquide'] = passivo - attivo
    return d


def _infrannuale_grezzo(db, *, riferimento=True, rif=None, parziale=None,
                        acconti=D('0'), current_tax=D('0'), imposta_riferimento=D('0')):
    """Riferimento 2024 pieno + parziale 2025 (9 mesi), oppure il solo parziale:
    senza anno pieno il motore prende `_project_balance_sheet_annualized`."""
    azienda = Company(name="Conguaglio infra", tax_id="CONGUAGLIO-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    if riferimento:
        fy = FinancialYear(company_id=azienda.id, year=2024, period_months=None,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **_stato(**(rif or {}))))
        db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=_RIF_COSTI,
                               ce05_materie_prime=_RIF_COSTI, ce20_imposte=imposta_riferimento))
    fy = FinancialYear(company_id=azienda.id, year=2025, period_months=9,
                       validation_status="verified", forecastable=True)
    db.add(fy)
    db.flush()
    db.add(BalanceSheet(financial_year_id=fy.id, **_stato(**(parziale or {}))))
    db.add(IncomeStatement(financial_year_id=fy.id))
    scenario = BudgetScenario(company_id=azienda.id, name="conguaglio", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D('0'),
                             fixed_materials_percentage=D('0'), fixed_services_percentage=D('0'),
                             ce20_override=current_tax, tax_advances_paid=acconti))
    db.commit()
    return azienda, scenario


def _proietta(db, scenario):
    result = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp, result


_RIF_MISTO = dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                  sp16g_altri_debiti_breve=D("200000"))
_RIF_MISTOSENZAG = dict(sp16a_debiti_banche_breve=D("600000"),
                        sp16e_debiti_tributari_breve=D("200000"),
                        sp16d_debiti_fornitori_breve=D("200000"))


def test_la_posizione_tributaria_non_partecipa_alla_rotazione_dei_debiti_operativi():
    """La capienza di un secchio del riferimento non governa più il pagamento.

    Il parziale apre con 600.000 di debito tributario e nessun debito operativo;
    il riferimento contiene 200.000 di fornitori e 200.000 tributari. A fine anno
    restano i soli 200.000 di fornitori proiettati: il debito tributario si chiude
    per intero e la cassa registra −600.000 + 200.000, indipendentemente da sp16g.
    """
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db, rif=_RIF_MISTOSENZAG,
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("600000")))
    sp, result = _proietta(db, scenario)
    assert sp.sp09_disponibilita_liquide == D("2800000.00")
    assert sp.sp16e_debiti_tributari_breve == D("0.00")
    assert sp.sp16d_debiti_fornitori_breve == D("200000.00")
    assert sp.sp16g_altri_debiti_breve == D("0.00")
    assert sp.sp16a_debiti_banche_breve == D("600000.00")
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']


def test_il_credito_tributario_aperto_resta_in_bilancio():
    """Il credito fiscale aperto alla data del parziale NON si assume incassato
    entro l'anno (decisione del proprietario, 2026-09-16, che rivede quella del
    lotto 3A: «l'incasso dei tributari a breve è meglio toglierlo, complica
    troppo»). Prima quei 300.000 diventavano cassa; ora restano dove sono, e la
    cassa proiettata è inferiore dello stesso importo. Il debito aperto invece
    continua a pagarsi: è il lato prudente dei due.
    """
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                 sp16g_altri_debiti_breve=D("200000"),
                 sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"),
                      sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("200000"),
                      sp06a_crediti_clienti_breve=D("400000"),
                      sp06e_crediti_tributari_breve=D("300000"),
                      sp06g_crediti_altri_breve=D("200000")))
    sp, result = _proietta(db, scenario)
    assert sp.sp09_disponibilita_liquide == D("1500000.00")
    assert sp.sp16g_altri_debiti_breve == D("200000.00")
    assert sp.sp06g_crediti_altri_breve == D("333333.33")
    assert sp.sp06e_crediti_tributari_breve == D("300000.00")
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']


def test_senza_riferimento_il_cash_out_deriva_dalla_posizione_e_dal_ce():
    """Sul ramo annualizzato il movimento completo nasce già da utile e saldi
    fiscali: −100.000 di imposta residua, −100.000 di debito chiuso e +200.000
    di credito finale producono i −400.000 dichiarati dal kernel, senza plug.
    """
    db = _sessione()
    T5PAR = dict(sp11_capitale=D("2000000"),
                 sp16a_debiti_banche_breve=D("100000"),
                 sp16e_debiti_tributari_breve=D("100000"),
                 sp16g_altri_debiti_breve=D("100000"),
                 sp06a_crediti_clienti_breve=D("200000"))
    _, scenario = _infrannuale_grezzo(
        db, riferimento=False, parziale=T5PAR,
        acconti=D("300000"), current_tax=D("100000")
    )
    sp, result = _proietta(db, scenario)
    assert sp.sp09_disponibilita_liquide == D("1700000.00")
    assert sp.sp16g_altri_debiti_breve == D("100000.00")
    assert sp.sp06e_crediti_tributari_breve == D("200000.00")
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']


def test_la_posizione_di_apertura_si_dichiara():
    """Che fine fa la posizione tributaria aperta alla data del parziale — il
    debito pagato, il credito riportato — si dichiara, invece di lasciarlo
    dedurre dal confronto fra due colonne."""
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                 sp16g_altri_debiti_breve=D("200000"),
                 sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"),
                      sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("200000"),
                      sp06a_crediti_clienti_breve=D("400000"),
                      sp06e_crediti_tributari_breve=D("300000"),
                      sp06g_crediti_altri_breve=D("200000")))
    sp, result = _proietta(db, scenario)
    assert sp.sp06e_crediti_tributari_breve == D("300000.00")
    dichiarazioni = [d for d in result['diagnostics']
                     if d['code'] == 'posizione_tributaria_apertura']
    assert len(dichiarazioni) == 1
    dichiarazione = dichiarazioni[0]
    assert dichiarazione['amount'] == "300000.00"
    assert "300.000,00" in dichiarazione['message']
    assert "resta in bilancio" in dichiarazione['message']
    assert "200.000,00" in dichiarazione['message']


def test_senza_posizione_aperta_non_si_dichiara_nulla():
    """Un controllo che non scatta tace: un «nessun problema» ad ogni proiezione
    non è una diagnostica."""
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp06a_crediti_clienti_breve=D("400000")))
    _sp, result = _proietta(db, scenario)
    assert not [d for d in result['diagnostics']
                if d['code'] == 'posizione_tributaria_apertura']
