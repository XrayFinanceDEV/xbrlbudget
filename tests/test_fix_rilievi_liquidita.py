"""C05 (lotto 2 fix rilievi, 2026-09-26): un solo current ratio, quick ratio e CCN, simmetrici sui
ratei. Prima della correzione la sezione 8 (`calculations/report_indicators.py`) e l'Allegato E
(`calculations/ratios.py`) usavano due perimetri diversi di attivo/passivo corrente — sp07 dentro
o fuori, sp10/sp18 dentro o fuori — e lo stesso bilancio pubblicava due current ratio diversi nello
stesso documento (oracolo in `tests/test_rilievi_ambienta.py::test_C05_un_solo_current_ratio_nel_documento`).

Qui: test unitari delle due funzioni condivise (`attivo_corrente`/`passivo_corrente`) e verifica che
`FinancialRatiosCalculator` (Allegato E) e `indicator_results` (sezione 8) diano lo stesso numero
sullo stesso bilancio. `BalanceSheet.current_assets`/`working_capital_net` (Altman, FGPMI) non si
toccano in questo lotto: un test lo fissa.
"""
from decimal import Decimal as D

from tests.rilievi_kit import BASE_BS, BASE_CE
from calculations.ratios import FinancialRatiosCalculator
from calculations.report_indicators import attivo_corrente, indicator_results, passivo_corrente


def _getter(**valori):
    return lambda field: valori.get(field, D("0"))


def _statements(bs_over=None, ce_over=None):
    """`BalanceSheet`/`IncomeStatement` con i default di colonna applicati da un commit reale su un
    DB in memoria, base AMBIENTA (`tests/rilievi_kit.BASE_BS`/`BASE_CE`) più eventuali ritocchi —
    niente bilanci inventati (stesso pattern di `tests/test_fix_rilievi_report.py::_statements`)."""
    from tests.e2e_kit import memory_sessions
    from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="UNIT", tax_id="UNIT-C05", sector=1, user_id="unit")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None)
            db.add(fy); db.flush()
            bs = BalanceSheet(financial_year_id=fy.id, **{**BASE_BS, **(bs_over or {})})
            inc = IncomeStatement(financial_year_id=fy.id, **{**BASE_CE, **(ce_over or {})})
            db.add(bs); db.add(inc); db.commit()
            db.refresh(bs); db.refresh(inc)
            db.expunge(bs); db.expunge(inc)
            return bs, inc
    finally:
        engine.dispose()


# ===========================================================================
# Le due funzioni condivise
# ===========================================================================

def test_attivo_corrente_esclude_i_crediti_oltre_12_mesi_e_include_i_ratei_attivi():
    """sp07 (crediti oltre 12 mesi) fuori dall'attivo corrente; sp10 (ratei attivi) dentro."""
    v = _getter(sp05_rimanenze=D("287312.00"), sp06_crediti_breve=D("1294367.10"),
                sp07_crediti_lungo=D("62356.48"), sp08_attivita_finanziarie=D("0"),
                sp09_disponibilita_liquide=D("54.82"), sp10_ratei_risconti_attivi=D("216226.30"))
    atteso = D("287312.00") + D("1294367.10") + D("54.82") + D("216226.30")
    assert attivo_corrente(v) == atteso


def test_passivo_corrente_include_i_ratei_passivi():
    """sp18 (ratei passivi) dentro il passivo corrente, simmetrico all'attivo che conta già sp10."""
    v = _getter(sp16_debiti_breve=D("1400851.61"), sp18_ratei_risconti_passivi=D("38663.00"))
    assert passivo_corrente(v) == D("1400851.61") + D("38663.00")


def test_passivo_corrente_senza_ratei_e_il_solo_debito_a_breve():
    v = _getter(sp16_debiti_breve=D("500000"))
    assert passivo_corrente(v) == D("500000")


# ===========================================================================
# Sezione 8 (report_indicators) e Allegato E (ratios.py): un solo numero
# ===========================================================================

def test_sezione_8_e_allegato_e_danno_lo_stesso_current_ratio():
    """Stesso bilancio (BASE_BS, con sp07/sp10/sp18 tutti non nulli): sezione 8 e Allegato E devono
    pubblicare lo stesso current ratio — l'oracolo del triage C05."""
    bs, inc = _statements()
    analytical = {"liquidity": {
        "current_ratio": FinancialRatiosCalculator(bs, inc).calculate_liquidity_ratios().current_ratio,
        "quick_ratio": FinancialRatiosCalculator(bs, inc).calculate_liquidity_ratios().quick_ratio,
        "acid_test": D("0"),
    }}
    bs_dict = dict(BASE_BS)
    res = indicator_results(bs_dict, dict(BASE_CE), analytical)
    sez8 = res["practice.current_ratio"].value
    all_e = res["analytical.liquidity.current_ratio"].value
    assert sez8 is not None and all_e is not None
    assert abs(sez8 - all_e) < D("0.01"), (sez8, all_e)


def test_sezione_8_e_allegato_e_danno_lo_stesso_quick_ratio():
    bs, inc = _statements()
    analytical = {"liquidity": {
        "current_ratio": D("0"),
        "quick_ratio": FinancialRatiosCalculator(bs, inc).calculate_liquidity_ratios().quick_ratio,
        "acid_test": D("0"),
    }}
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), analytical)
    sez8 = res["practice.quick_ratio"].value
    all_e = res["analytical.liquidity.quick_ratio"].value
    assert sez8 is not None and all_e is not None
    assert abs(sez8 - all_e) < D("0.01"), (sez8, all_e)


def test_current_ratio_allegato_e_diverge_dalla_vecchia_formula_su_ambienta():
    """Regressione: la vecchia formula (sp07 dentro l'attivo, niente sp18 nel passivo) dava 1,17×
    su AMBIENTA; la formula simmetrica ne dà uno diverso, a riprova che il fix è entrato in vigore."""
    bs, inc = _statements()
    nuovo = FinancialRatiosCalculator(bs, inc).calculate_liquidity_ratios().current_ratio
    vecchio = (bs.current_assets / bs.current_liabilities).quantize(D("0.0001"))
    assert nuovo != vecchio, (nuovo, vecchio)


def test_ccn_allegato_e_e_sezione_8_coincidono():
    bs, inc = _statements()
    ccn_allegato_e = FinancialRatiosCalculator(bs, inc).calculate_working_capital_metrics().ccn
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), {})
    ccn_sez8 = res["practice.ccn"].value
    assert ccn_sez8 is not None
    assert abs(ccn_sez8 - ccn_allegato_e) < D("0.01"), (ccn_sez8, ccn_allegato_e)


def test_ccn_e_simmetrico_sui_ratei():
    """CCN = attivo corrente (con ratei attivi) - passivo corrente (con ratei passivi): non basta
    sommare i ratei da un solo lato."""
    v = _getter(sp05_rimanenze=D("100"), sp06_crediti_breve=D("200"), sp09_disponibilita_liquide=D("50"),
                sp10_ratei_risconti_attivi=D("30"), sp16_debiti_breve=D("120"), sp18_ratei_risconti_passivi=D("10"))
    atteso = (D("100") + D("200") + D("50") + D("30")) - (D("120") + D("10"))
    assert attivo_corrente(v) - passivo_corrente(v) == atteso


# ===========================================================================
# Passivo corrente a zero: indefinito, non zero
# ===========================================================================

def test_current_ratio_practice_none_con_passivo_corrente_zero():
    bs_dict = {**BASE_BS, "sp16_debiti_breve": D("0"), "sp18_ratei_risconti_passivi": D("0")}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.current_ratio"]
    assert r.value is None and r.reason == "zero_denominator", r


def test_quick_ratio_practice_none_con_passivo_corrente_zero():
    bs_dict = {**BASE_BS, "sp16_debiti_breve": D("0"), "sp18_ratei_risconti_passivi": D("0")}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.quick_ratio"]
    assert r.value is None and r.reason == "zero_denominator", r


def test_ccn_practice_resta_un_importo_anche_con_passivo_corrente_zero():
    """CCN è un importo (`amount`, non `ratio`): con passivo corrente zero resta l'intero attivo
    corrente, non `None` — nessuna divisione in gioco."""
    bs_dict = {**BASE_BS, "sp16_debiti_breve": D("0"), "sp18_ratei_risconti_passivi": D("0")}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.ccn"]
    assert r.value is not None
    assert r.value == attivo_corrente(lambda f: D(str(bs_dict.get(f, D("0")))))


# ===========================================================================
# Guardia: Altman e FGPMI restano sulla vecchia perimetrazione (non si toccano in questo lotto)
# ===========================================================================

def test_balance_sheet_current_assets_e_working_capital_net_non_si_toccano():
    """`BalanceSheet.current_assets` (con sp07, senza sp10) e `working_capital_net` restano quelli
    di sempre: li usano Altman e FGPMI, fuori dal perimetro di C05."""
    bs, inc = _statements()
    vecchio_current_assets = (BASE_BS["sp05_rimanenze"] + BASE_BS["sp06_crediti_breve"]
                               + BASE_BS["sp07_crediti_lungo"] + BASE_BS.get("sp08_attivita_finanziarie", D("0"))
                               + BASE_BS["sp09_disponibilita_liquide"])
    assert bs.current_assets == vecchio_current_assets
    assert bs.current_liabilities == BASE_BS["sp16_debiti_breve"]
    assert bs.working_capital_net == bs.current_assets - bs.current_liabilities


# ===========================================================================
# F6 (Importante, revisione finale lotto 2, 2026-09-26): un solo Margine di Tesoreria.
# Prima del fix, `report_indicators.py` toglieva solo `sp16` (non il passivo corrente
# simmetrico di C05) e `ratios.py` usava una TERZA formula (sp06+sp07+sp09, coi crediti
# oltre 12 mesi dentro) — tre numeri diversi per lo stesso indicatore nello stesso
# documento/app. Ora: MT = attivo corrente - rimanenze - passivo corrente, in entrambi i
# punti, con la stessa `passivo_corrente()` di CCN/current ratio/quick ratio.
# ===========================================================================

def test_mt_practice_usa_attivo_corrente_meno_rimanenze_meno_passivo_corrente():
    """Sezione 8: MT = attivo corrente - rimanenze - passivo corrente (debiti a breve + ratei
    passivi), non attivo corrente - rimanenze - soli debiti a breve."""
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), {})
    v = _getter(**BASE_BS)
    atteso = attivo_corrente(v) - BASE_BS["sp05_rimanenze"] - passivo_corrente(v)
    r = res["practice.mt"]
    assert r.value is not None and r.value == atteso, (r.value, atteso)


def test_mt_practice_diverge_dalla_vecchia_formula_su_ambienta():
    """Regressione: la vecchia formula (solo sp16 al denominatore, senza sp18) dava un MT diverso
    su AMBIENTA — a riprova che il fix è entrato in vigore."""
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), {})
    v = _getter(**BASE_BS)
    vecchio = attivo_corrente(v) - BASE_BS["sp05_rimanenze"] - BASE_BS["sp16_debiti_breve"]
    r = res["practice.mt"]
    assert r.value != vecchio, (r.value, vecchio)


def test_mt_allegato_e_usa_la_stessa_formula_di_sezione_8():
    """`FinancialRatiosCalculator.calculate_working_capital_metrics().mt` (pagina Indici) dà lo
    stesso numero della sezione 8 sullo stesso bilancio — non più la terza formula
    (sp06+sp07+sp09-passivo) che includeva i crediti oltre 12 mesi."""
    bs, inc = _statements()
    mt_indici = FinancialRatiosCalculator(bs, inc).calculate_working_capital_metrics().mt
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), {})
    mt_sez8 = res["practice.mt"].value
    assert mt_sez8 is not None
    assert abs(mt_sez8 - mt_indici) < D("0.01"), (mt_sez8, mt_indici)


def test_mt_e_simmetrico_sui_ratei_come_il_ccn():
    """Stessa guardia di `test_ccn_e_simmetrico_sui_ratei`, per il MT: un rateo attivo entra
    nell'attivo corrente, un rateo passivo nel passivo corrente — non basta sommarne uno solo."""
    v = _getter(sp05_rimanenze=D("100"), sp06_crediti_breve=D("200"), sp09_disponibilita_liquide=D("50"),
                sp10_ratei_risconti_attivi=D("30"), sp16_debiti_breve=D("120"), sp18_ratei_risconti_passivi=D("10"))
    atteso = (attivo_corrente(v) - D("100")) - passivo_corrente(v)
    assert atteso == (D("200") + D("50") + D("30")) - (D("120") + D("10"))


def test_acid_test_resta_una_definizione_diversa_dal_quick_ratio():
    """F6 (nota del rilievo): l'acid test di `ratios.py` include i crediti oltre 12 mesi al
    numeratore e solo `sp16` (non `sp18`) al denominatore — una definizione classica diversa
    dal quick ratio pratica (`current_ratio`/`quick_ratio`, C05), non un refuso da allineare.
    Decisione dichiarata nel rapporto di questo giro: resta così, non si tocca."""
    bs, inc = _statements()
    calc = FinancialRatiosCalculator(bs, inc)
    quick = calc.calculate_liquidity_ratios().quick_ratio
    acid = calc.calculate_liquidity_ratios().acid_test
    assert quick != acid, (quick, acid)
