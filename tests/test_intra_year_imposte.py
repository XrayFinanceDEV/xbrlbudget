"""Al 31/12 l'infrannuale lascia solo il saldo d'imposta dell'anno (lotto 3A, Task 5, decisione 4 del proprietario)."""
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


def _proietta(db, scenario, *, con_conguaglio=True):
    """Esegue la proiezione; `con_conguaglio=False` neutralizza SOLO il blocco del
    Task 3, cioè la stessa identica proiezione di prima di questo change. Sul codice
    precedente il metodo non esiste: la corsa "senza" è allora identica a quella
    "con", e l'asserzione differenziale cade sul numero — prova rossa pulita."""
    originale = getattr(IntraYearEngine, '_applica_conguaglio_tributario', None)
    if not con_conguaglio and originale is not None:
        IntraYearEngine._applica_conguaglio_tributario = (
            lambda self, sp16g, sp06g, correzione: (sp16g, sp06g))
    try:
        result = IntraYearEngine(db).generate_projection(scenario.id)
    finally:
        if originale is not None:
            IntraYearEngine._applica_conguaglio_tributario = originale
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp, result


_RIF_MISTO = dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                  sp16g_altri_debiti_breve=D("200000"))
_RIF_MISTOSENZAG = dict(sp16a_debiti_banche_breve=D("600000"),
                        sp16e_debiti_tributari_breve=D("200000"),
                        sp16d_debiti_fornitori_breve=D("200000"))


def test_il_conguaglio_riporta_la_cassa_a_cash_out_anche_con_sp16_a_composizione_mista():
    """Debito di riferimento 200.000,00 tributari + 200.000,00 altri; quello vero del
    parziale 400.000,00. La rotation posa su `sp16e` la quota del riferimento
    (x = 200.000,00), il kernel la sostituisce con 0 e `cash_out` dice 400.000,00:
    prima di questo change la cassa si muoveva di −200.000,00 (solo la sostituzione
    di riga), gli altri 200.000,00 sparivano nel plug senza alcun flusso."""
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db, rif=_RIF_MISTO,
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("400000")))
    cassa_senza, _ = _proietta(db, scenario, con_conguaglio=False)
    db2 = _sessione()
    _, scenario2 = _infrannuale_grezzo(
        db2, rif=_RIF_MISTO,
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("400000")))
    sp, result = _proietta(db2, scenario2)
    cash_out = D("400000")                       # kernel: apertura 400.000, niente imposta nuova
    x = D("200000")                              # quota-riferimento su sp16e
    assert sp.sp09_disponibilita_liquide == cassa_senza.sp09_disponibilita_liquide + (
        -cash_out - (D("0") - x))
    assert sp.sp16e_debiti_tributari_breve == D("0.00")
    assert sp.sp16g_altri_debiti_breve == D("0.00")          # il conguaglio se l'è presa tutta
    assert sp.sp16a_debiti_banche_breve == D("600000.00")    # il finanziario non si tocca (Task 1)
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']


def test_il_credito_tributario_d_apertura_esce_dagli_altri_crediti_mai_da_un_passivita():
    """Apertura: debito tributario 200.000,00 e credito tributario 300.000,00, nessuna
    imposta nuova → `cash_out` = −100.000,00, un INCASSO. Il conguaglio viene positivo
    e la contropartita giusta è l'attivo (`sp06g`, dove il Task 2 ha riclassificato la
    massa del credito), non un aumento di `sp16g`: la prima stesura del brief faceva
    quello e su uno scenario reale fabbricava 144.188,46 di passività (ruling del
    coordinatore, 2026-09-12)."""
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
    cassa_senza, _ = _proietta(db, scenario, con_conguaglio=False)
    db2 = _sessione()
    _, scenario2 = _infrannuale_grezzo(
        db2,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                 sp16g_altri_debiti_breve=D("200000"),
                 sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"),
                      sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("200000"),
                      sp06a_crediti_clienti_breve=D("400000"),
                      sp06e_crediti_tributari_breve=D("300000"),
                      sp06g_crediti_altri_breve=D("200000")))
    sp, result = _proietta(db2, scenario2)
    # con - senza = il solo conguaglio = -cash_out - (chiusura - x) = +300.000,00
    assert sp.sp09_disponibilita_liquide == cassa_senza.sp09_disponibilita_liquide + (
        D("100000") - (D("0") - D("200000")))
    assert sp.sp16g_altri_debiti_breve == D("200000.00")    # nessuna passività inventata
    assert sp.sp06g_crediti_altri_breve == D("33333.33")    # 1.000.000 * 200/600 - 300.000
    assert sp.sp06_crediti_breve == D("700000.00")          # aggregato ridotto di 300.000
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']


def test_la_capienza_insufficiente_lato_passivo_si_dichiara_e_non_si_inventa():
    """`sp16g` del riferimento è a zero (la massa sta sui fornitori): il conguaglio di
    −400.000,00 non ha dove posarsi. Si applica quel che ci sta (nulla), si dichiara il
    residuo, e la cassa resta dov'era — una passività negativa sarebbe massa inventata,
    e un secondo bersaglio è il vecchio plug."""
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db, rif=_RIF_MISTOSENZAG,
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("600000")))
    cassa_senza, _ = _proietta(db, scenario, con_conguaglio=False)
    db2 = _sessione()
    _, scenario2 = _infrannuale_grezzo(
        db2, rif=_RIF_MISTOSENZAG,
        parziale=dict(sp11_capitale=D("2000000"), sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("600000")))
    sp, result = _proietta(db2, scenario2)
    assert sp.sp09_disponibilita_liquide == cassa_senza.sp09_disponibilita_liquide
    assert sp.sp16g_altri_debiti_breve == D("0.00")
    guardia = [d for d in result['diagnostics'] if d['code'] == 'tax_settlement_reclass_below_zero']
    assert len(guardia) == 1 and D(guardia[0]['amount']) == D("-400000.00")
    assert guardia[0]['field'] == 'sp16g_altri_debiti_breve'


def test_la_capienza_insufficiente_lato_attivo_si_dichiara_e_non_si_inventa():
    """Stesso meccanismo sul lato credito: il conguaglio positivo di 300.000,00 trova
    solo 16.666,67 di `sp06g` (la composizione del parziale è quasi tutta clienti).
    Si azzera quel campo, il residuo si dichiara, e nessun debito sale."""
    db = _sessione()
    _, scenario = _infrannuale_grezzo(
        db,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                 sp16g_altri_debiti_breve=D("200000"),
                 sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"),
                      sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("200000"),
                      sp06a_crediti_clienti_breve=D("590000"),
                      sp06e_crediti_tributari_breve=D("300000"),
                      sp06g_crediti_altri_breve=D("10000")))
    cassa_senza, _ = _proietta(db, scenario, con_conguaglio=False)
    db2 = _sessione()
    _, scenario2 = _infrannuale_grezzo(
        db2,
        rif=dict(sp16a_debiti_banche_breve=D("600000"), sp16e_debiti_tributari_breve=D("200000"),
                 sp16g_altri_debiti_breve=D("200000"),
                 sp06a_crediti_clienti_breve=D("1000000")),
        parziale=dict(sp11_capitale=D("2000000"),
                      sp16a_debiti_banche_breve=D("600000"),
                      sp16e_debiti_tributari_breve=D("200000"),
                      sp06a_crediti_clienti_breve=D("590000"),
                      sp06e_crediti_tributari_breve=D("300000"),
                      sp06g_crediti_altri_breve=D("10000")))
    sp, result = _proietta(db2, scenario2)
    assert sp.sp06g_crediti_altri_breve == D("0.00")
    assert sp.sp16g_altri_debiti_breve == D("200000.00")
    guardia = [d for d in result['diagnostics'] if d['code'] == 'tax_settlement_reclass_below_zero']
    assert len(guardia) == 1
    assert abs(D(guardia[0]['amount']) - D("283333.33")) <= D("0.01")   # l'importo non è ancora quantizzato ai centesimi
    assert guardia[0]['field'] == 'sp06g_crediti_altri_breve'


def test_senza_riferimento_il_conguaglio_guarda_anche_il_lato_credito():
    """Ramo annualizzato (nessun anno pieno importato): qui il Task 2 non è passato e
    la riga combinata `sp06e, sp16e = ...` gira dopo i riassorbimenti, quindi perde
    massa su ENTRAMBI i lati. Il conguaglio deve misurarsi su tutti e due (forma della
    bozza originale, `credito_pre_swap`): con la sola quota debito la cassa si
    muoverebbe di −300.000,00 invece dei −400.000,00 dichiarati da `cash_out`."""
    db = _sessione()
    T5PAR = dict(sp11_capitale=D("2000000"),
                 sp16a_debiti_banche_breve=D("100000"),
                 sp16e_debiti_tributari_breve=D("100000"),
                 sp16g_altri_debiti_breve=D("100000"),
                 sp06a_crediti_clienti_breve=D("200000"))
    _, scenario = _infrannuale_grezzo(db, riferimento=False, parziale=T5PAR,
                                      acconti=D("300000"), current_tax=D("100000"))
    cassa_senza, _ = _proietta(db, scenario, con_conguaglio=False)
    db2 = _sessione()
    _, scenario2 = _infrannuale_grezzo(db2, riferimento=False, parziale=T5PAR,
                                       acconti=D("300000"), current_tax=D("100000"))
    sp, result = _proietta(db2, scenario2)
    # cash_out = 400.000,00; righe: debito -100.000,00 e credito +200.000,00 => -300.000,00
    # di implicito: il conguaglio che manca \u00e8 -100.000,00, non -300.000,00.
    assert sp.sp09_disponibilita_liquide == cassa_senza.sp09_disponibilita_liquide - D("100000")
    assert sp.sp16g_altri_debiti_breve == D("0.00")
    assert sp.sp06e_crediti_tributari_breve == D("200000.00")
    assert sp.total_assets == sp.total_liabilities
    assert not [d for d in result['diagnostics']
                if d['code'] == 'tax_settlement_reclass_below_zero']
