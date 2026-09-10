"""Il rendiconto non conta piu' la riclassifica sp17a<->sp16a come flusso
operativo (Task 17, giro di correzione 1, F1).

**Il difetto** (revisione, rilievo Important I1). `cashflow_detailed.py:186`
metteva TUTTA la variazione di `sp16_debiti_breve` (fornitori E banche insieme)
nel capitale circolante, e il finanziario prendeva solo il debito bancario a
lungo. Con la quota a breve del prestito nuovo (Task 17), la riclassifica fra
`sp17a` e `sp16a` attraversava il confine operativo/finanziario: caso A 2027,
operativo 76.191,19 -> 101.191,28, finanziario 75.000,29 -> 50.000,20. La
stessa cosa succedeva, per un motivo diverso, in `cashflow.py` (anni storici):
`delta_payables` prendeva tutto `sp16` (come sopra) E `delta_debt` prendeva
`total_debt` (`sp16+sp17` interi): il debito bancario a breve finiva contato
DUE volte, una nell'operativo e una nel finanziario.

**La correzione.** `delta_payables` porta solo il debito OPERATIVO
(`BalanceSheet.operating_debt_total`: fornitori, tributari, previdenziali,
altri debiti, breve e lungo — mai le banche, gli altri finanziatori, le
obbligazioni). In `cashflow_detailed.py` il finanziario resta un RESIDUO
(quello che serve a far quadrare la cassa: `debt_net = variazione_cassa -
operativo - investimenti - mezzi propri`) — che ora lo assorbe SENZA doppio
conteggio perche' il debito finanziario non e' piu' nel circolante. In
`cashflow.py` il finanziario non e' un residuo, e' additivo
(`financing_cf = delta_debt + delta_equity`): li' `delta_debt` deve usare
`financial_debt_total` (banche + altri finanziatori + obbligazioni, breve E
lungo), mai `total_debt` (che risomma anche il debito operativo gia' contato
in `delta_payables`).

**Perche' l'invariante «cassa rendiconto = variazione sp09» non prova nulla**
(precisazione del coordinatore durante questo giro): il finanziario di
`cashflow_detailed.py` e' un residuo PER COSTRUZIONE — quadra sempre, con
qualunque classificazione di `delta_payables`, quindi un test su quell'
uguaglianza passerebbe anche su `6773a20` senza correzione. L'invariante che
prova qualcosa e' che il residuo coincida con la variazione MISURATA del
debito finanziario (`financial_debt_short + financial_debt_long`): se non
coincide, il rendiconto sta nascondendo nel finanziario un movimento di stato
patrimoniale che non classifica da nessuna parte.

Misurato sul banco (`scripts/parita_motore.py`, 60 scenari, 4 fixture di base
x 10 profili, seme 20260910, 4 anni): lo scarto e' ESATTAMENTE zero su 192
celle anno-scenario (fixture `base`, `base_scala_a`, `base_scala_b`, `banca`,
meno 2 scenari che il motore rifiuta per fabbisogno scoperto, non collegati a
questo giro), e vale una costante indipendente dall'anno e dal profilo SOLO
sui fixture `holding`/`holding_scala` (30.000,00 e 32.194,80 — esattamente
`ce13_proventi_partecipazioni` dell'anno base, scalato). Causa: riga ~227 di
`cashflow_detailed.py`, `dividends_received = Decimal("0")`, che non rimette
mai da nessuna parte i dividendi sottratti all'operativo alla riga ~120
(`profit_before_adjustments`). E' un difetto preesistente e indipendente dal
debito bancario (il fixture holding non ha ne' `sp16a/b/c` ne' `sp17` non
zero), fuori dal perimetro di F1: dichiarato qui, non corretto.
"""
from decimal import Decimal as D

from backend.app.calculations.cashflow import CashFlowCalculator
from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear, ForecastYear, IncomeStatement
from tests.e2e_kit import BASE_CE, memory_sessions, seed_base_year

BREVE, LUNGO = D("12345.67"), D("23456.79")
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}
A3 = (2027, 2028, 2029)


def _genera(db, user, rows):
    """Caso A del Task 17: pregresso bancario 12.345,67 breve / 23.456,79
    lungo, prestito nuovo 100.000,38/4 anni al 4,35%, erogato nel 2027."""
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    delta_lungo = LUNGO - b.sp17a_debiti_banche_lungo
    b.sp16a_debiti_banche_breve = BREVE
    b.sp16_debiti_breve += BREVE
    b.sp17a_debiti_banche_lungo = LUNGO
    b.sp17_debiti_lungo += delta_lungo
    b.sp09_disponibilita_liquide += BREVE + delta_lungo
    db.commit()
    sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
    assert res["forecast_generated"] is True, f"{user}: {res['message']}"
    return fy, sc


def _righe(anni, per_anno=None):
    rows = [dict(forecast_year=y, revenue_growth_pct=3.33, tax_rate=27.9) for y in anni]
    for i, extra in (per_anno or {}).items():
        rows[i].update(extra)
    return rows


def _cf(db, sc, anno, bs_prev):
    fy = db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id, ForecastYear.year == anno).one()
    cf = DetailedCashFlowCalculator.calculate(
        bs_current=fy.balance_sheet, bs_previous=bs_prev, inc_current=fy.income_statement, year=anno,
    )
    return cf, fy.balance_sheet


def test_caso_a_2027_torna_ai_valori_di_5197929():
    """Operativo 76.191,19, finanziario 75.000,29: i numeri che `5197929`
    (prima del Task 17) dava per questo scenario, misurati dalla revisione
    (I1). 2028/2029: la quota e' costante (25.000,09/anno, nessuna nuova
    erogazione), quindi il finanziario e' -25.000,09 ogni anno successivo."""
    engine, Session_ = memory_sessions()
    db = Session_()
    rows = _righe(A3, per_anno={0: PRESTITO})
    fy_base, sc = _genera(db, "casoA", rows)

    cf2027, bs2027 = _cf(db, sc, 2027, fy_base.balance_sheet)
    assert cf2027.operating_activities.total_operating_cashflow == D("76191.19")
    assert cf2027.financing_activities.third_party_funds.net == D("75000.29")
    assert cf2027.financing_activities.total_financing_cashflow == D("75000.29")
    assert cf2027.cash_reconciliation.verification_ok is True

    cf2028, bs2028 = _cf(db, sc, 2028, bs2027)
    assert cf2028.financing_activities.total_financing_cashflow == D("-25000.09")
    cf2029, _ = _cf(db, sc, 2029, bs2028)
    assert cf2029.financing_activities.total_financing_cashflow == D("-25000.09")


def test_spostare_la_quota_fra_sp16a_e_sp17a_non_cambia_operativo_ne_finanziario():
    """Invariante 2 del brief: a totale invariato, la riclassifica breve/lungo
    del debito bancario non deve mai attraversare il confine operativo /
    finanziario."""
    engine, Session_ = memory_sessions()
    db = Session_()
    rows = _righe(A3, per_anno={0: PRESTITO})
    fy_base, sc = _genera(db, "spostamento", rows)
    fy2027 = db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id, ForecastYear.year == 2027).one()

    prima, _ = _cf(db, sc, 2027, fy_base.balance_sheet)
    op_prima = prima.operating_activities.total_operating_cashflow
    fin_prima = prima.financing_activities.total_financing_cashflow

    spostamento = D("5000.00")
    fy2027.balance_sheet.sp16a_debiti_banche_breve += spostamento
    fy2027.balance_sheet.sp16_debiti_breve += spostamento
    fy2027.balance_sheet.sp17a_debiti_banche_lungo -= spostamento
    fy2027.balance_sheet.sp17_debiti_lungo -= spostamento
    db.commit()

    dopo, _ = _cf(db, sc, 2027, fy_base.balance_sheet)
    assert dopo.operating_activities.total_operating_cashflow == op_prima
    assert dopo.financing_activities.total_financing_cashflow == fin_prima


def test_il_residuo_dei_mezzi_di_terzi_uguaglia_il_debito_finanziario_misurato():
    """L'invariante che prova qualcosa, al posto di «cassa = variazione sp09»
    (un residuo quadra sempre, con qualunque classificazione): il netto dei
    mezzi di terzi deve coincidere con Delta(financial_debt_short +
    financial_debt_long). Su questo scenario (nessun provento da
    partecipazioni) lo scarto e' zero in ogni anno — vedi il docstring del
    modulo per dove NON lo e' (fixture holding, fuori perimetro)."""
    engine, Session_ = memory_sessions()
    db = Session_()
    rows = _righe(A3, per_anno={0: PRESTITO})
    fy_base, sc = _genera(db, "scarto", rows)

    bs_prev = fy_base.balance_sheet
    for anno in A3:
        cf, bs_cur = _cf(db, sc, anno, bs_prev)
        residuo = cf.financing_activities.third_party_funds.net
        misurato = (
            D(str(bs_cur.financial_debt_short)) + D(str(bs_cur.financial_debt_long))
            - D(str(bs_prev.financial_debt_short)) - D(str(bs_prev.financial_debt_long))
        )
        assert residuo == misurato, f"{anno}: residuo {residuo} != misurato {misurato}"
        bs_prev = bs_cur


def test_gli_anni_storici_non_contano_due_volte_il_debito_finanziario_a_breve():
    """`cashflow.py` (anni storici): stessa regola di `cashflow_detailed.py`.
    Prima della correzione `delta_payables` portava tutto `sp16` (operativo +
    finanziario, aggregato), e gia' catturava per intero il rimborso a breve
    dentro `total_debt` = `sp16 + sp17` (finanziario): lo stesso movimento
    finiva sottratto DUE volte. Qui si rimborsano 3.000 di debito bancario a
    breve e 5.000 a lungo (nessun fornitore si muove, patrimonio netto
    invariato, aggregati `sp16`/`sp17` coerenti coi dettagli come in un
    bilancio vero): l'operativo non deve vedere nulla, il finanziario deve
    vedere -8.000 esatti."""
    engine, Session_ = memory_sessions()
    db = Session_()

    company_id, fy_prev_id = seed_base_year(db, user_id="storico", year=2025)
    fy_prev = db.query(FinancialYear).get(fy_prev_id)
    # sp17_debiti_lungo (aggregato) non e' nel fixture BASE_BS: lo si allinea
    # a sp17a (unico dettaglio non zero), come in un bilancio vero.
    fy_prev.balance_sheet.sp16a_debiti_banche_breve = D("5000.00")
    fy_prev.balance_sheet.sp16_debiti_breve += D("5000.00")
    fy_prev.balance_sheet.sp17_debiti_lungo = fy_prev.balance_sheet.sp17a_debiti_banche_lungo
    db.commit()

    fy_cur = FinancialYear(company_id=company_id, year=2026, period_months=None,
                            validation_status="verified", forecastable=True)
    db.add(fy_cur)
    db.flush()
    from tests.e2e_kit import BASE_BS
    cur_vals = dict(BASE_BS)
    cur_vals["sp16a_debiti_banche_breve"] = D("2000.00")  # -3.000 rispetto al prev
    cur_vals["sp16_debiti_breve"] = BASE_BS["sp16_debiti_breve"] + D("2000.00")
    cur_vals["sp17a_debiti_banche_lungo"] = BASE_BS["sp17a_debiti_banche_lungo"] - D("5000.00")
    cur_vals["sp17_debiti_lungo"] = cur_vals["sp17a_debiti_banche_lungo"]
    db.add(BalanceSheet(financial_year_id=fy_cur.id, **cur_vals))
    db.add(IncomeStatement(financial_year_id=fy_cur.id, **BASE_CE))
    db.commit()
    db.refresh(fy_cur)

    result = CashFlowCalculator.calculate(
        fy_cur.balance_sheet, fy_prev.balance_sheet, fy_cur.income_statement, ebitda=D("0"),
    )
    assert result.components.delta_payables == D("0.00")
    assert result.components.delta_debt == D("-8000.00")
    assert result.components.financing_cf == result.components.delta_debt + result.components.delta_equity
