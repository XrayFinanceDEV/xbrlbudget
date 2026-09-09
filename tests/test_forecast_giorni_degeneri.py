"""La guardia sui giorni medi DERIVATI del motore budget (Task 14).

`dso`, `dio` e `dpo` non impostati si deducono dall'anno base. La deduzione non
aveva alcuna guardia: il denominatore era `ce01` con un `or D('1')` di ripiego —
un denominatore inventato — e nulla vietava un risultato fuori da ogni scala.
Un giorno medio cosi' non descrive piu' l'azienda: descrive il proprio
denominatore, e il circolante proiettato lo segue in silenzio.

La soglia e' la stessa del rilievo G1 del banco di sensibilita'
(`scripts/sensibilita_ipotesi.py`) e la stessa nozione del motore infrannuale
(`calculations/intra_year_engine.py::_turnover_ratio`, «piu' di un anno di
giacenza»). Su un giorno degenere il motore riporta il saldo dell'anno base
invece di moltiplicare, e lo DICHIARA.
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database.models import BalanceSheet, FinancialYear, IncomeStatement
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "degeneri"
# base (e2e_kit): ricavi 600.000 · ce05+ce06 350.000 · sp06 = sp06a = 120.000
# · sp05 = sp05a = 50.000 · sp16d = 140.000 → dso 72, dio 30, dpo 144.
MANUAL_TAX = {"sp16e_growth_pct": 0, "sp06e_growth_pct": 0}


def _patch_base(db, company_id, *, bs=None, ce=None):
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    if bs:
        row = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
        for field, value in bs.items():
            setattr(row, field, D(str(value)))
    if ce:
        row = db.query(IncomeStatement).filter(IncomeStatement.financial_year_id == fy.id).one()
        for field, value in ce.items():
            setattr(row, field, D(str(value)))
    db.commit()


def _run(db, company_id, rows):
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="g", base_year=2026,
                             scenario_type="budget"),
        user_id=USER, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
        user_id=USER, db=db)
    assert res["forecast_generated"] is True, res["message"]
    prev = budget_scenarios.preview_forecast_route(
        company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
    assert prev["error"] is None
    return sc, [y["details"] for y in prev["forecast_years"]]


# ── (a) Il difetto: ricavi in ce04, `ce01` a zero ──

def test_a_degenerate_dso_carries_the_base_balance_and_declares_it(monkeypatch):
    """`ce01 = 0` e il fatturato su `ce04`: il denominatore del DSO non esiste.

    Oggi il ripiego `or D('1')` produce 43.200.000 giorni, e il circolante
    proiettato li segue: `forecast_revenue × 43.200.000 / 360` vale ZERO perche'
    anche il numeratore e' zero — i 120.000 di crediti spariscono senza un
    avviso. Con la guardia il saldo dell'anno base viene RIPORTATO, e il nome
    del giorno caduto sta nei details.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # Le rimanenze a zero isolano il DSO: con giacenza nulla nessun
            # giorno va riportato, quindi il DIO non e' degenere ma semplicemente
            # zero — la lista nomina la sola voce davvero riportata.
            _patch_base(db, company_id,
                        bs={"sp05_rimanenze": 0, "sp05a_materie_prime": 0,
                            "sp09_disponibilita_liquide": 80000},
                        ce={"ce01_ricavi_vendite": 0, "ce04_altri_ricavi": 600000})
            rows = [dict(forecast_year=y, revenue_growth_pct=5, **MANUAL_TAX)
                    for y in (2027, 2028)]
            sc, details = _run(db, company_id, rows)

            for det in details:
                assert det["degenerate_turnover_ratio"] == ["dso"]
            for _, bs, _ in read_forecast_maps(db, sc.id):
                assert bs["sp06a_crediti_clienti_breve"] == D("120000.00")
                assert bs["sp06_crediti_breve"] == D("120000.00")
                assert bs["sp05_rimanenze"] == D("0.00")
            # Il giorno DICHIARATO non e' piu' quello degenere: nessun giorno e'
            # stato applicato, il flusso su cui commisurarlo e' zero.
            assert details[0]["dso_applied"] == D("0")
            assert details[0]["dio_applied"] == D("0")
            assert details[0]["dpo_applied"] == D("144")
    finally:
        engine.dispose()


def test_an_explicit_day_never_goes_through_the_guard(monkeypatch):
    """Un giorno scritto dall'utente e' una scelta, non una derivazione: passa
    intatto anche sullo stesso anno base che fa cadere il DSO automatico."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _patch_base(db, company_id,
                        bs={"sp05_rimanenze": 0, "sp05a_materie_prime": 0,
                            "sp09_disponibilita_liquide": 80000},
                        ce={"ce01_ricavi_vendite": 0, "ce04_altri_ricavi": 600000})
            # 400 giorni: fuori dalla soglia che fa cadere un giorno DEDOTTO, e
            # scritto a mano. La guardia non lo tocca — un giorno esplicito e' una
            # scelta, e correggerla sarebbe il motore che decide al posto dell'utente.
            rows = [dict(forecast_year=2027, revenue_growth_pct=5, dso_days=400, **MANUAL_TAX)]
            sc, details = _run(db, company_id, rows)
            assert details[0]["degenerate_turnover_ratio"] == []
            assert details[0]["dso_applied"] == D("400")
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            # 400 giorni su un fatturato `ce01` nullo valgono zero crediti: se la
            # guardia fosse scattata qui, i crediti sarebbero i 120.000 riportati.
            assert bs["sp06_crediti_breve"] == D("0.00")
    finally:
        engine.dispose()


def test_a_tiny_ce01_carries_both_receivables_and_inventory(monkeypatch):
    """Il caso reale: 10.000 di `ce01` contro 590.000 su `ce04`.

    Qui il denominatore ESISTE — `_safe_divide` non avrebbe nulla da protegge­re —
    ed e' solo trascurabile: 4.320 giorni di credito e 1.800 di magazzino. Il
    rapporto e' ancora un moltiplicatore, e applicato al `ce01` proiettato porta
    crediti e rimanenze dove il fatturato vero non li giustifica. Entrambi i
    giorni cadono, entrambi i saldi vengono riportati, ed entrambi i nomi sono
    nella lista — nell'ordine in cui il motore li deduce.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _patch_base(db, company_id,
                        ce={"ce01_ricavi_vendite": 10000, "ce04_altri_ricavi": 590000})
            rows = [dict(forecast_year=2027, revenue_growth_pct=5, **MANUAL_TAX)]
            sc, details = _run(db, company_id, rows)
            assert details[0]["degenerate_turnover_ratio"] == ["dso", "dio"]
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            # Senza la guardia: 10.500 × 4.320/360 = 126.000 di crediti e
            # 10.500 × 1.800/360 = 52.500 di rimanenze.
            assert bs["sp06_crediti_breve"] == D("120000.00")
            assert bs["sp05_rimanenze"] == D("50000.00")
            # `dpo` non cade: 140.000 su 350.000 di acquisti sono 144 giorni.
            assert details[0]["dpo_applied"] == D("144")
            # I giorni DICHIARATI sono quelli che i saldi riportati valgono sul
            # `ce01` proiettato: l'identita' `saldo = flusso × giorni / 360` regge.
            assert details[0]["dso_applied"] == pytest.approx(120000 / 10500 * 360)
            assert details[0]["dio_applied"] == pytest.approx(50000 / 10500 * 360)
    finally:
        engine.dispose()


def test_a_missing_denominator_is_degenerate_even_when_the_days_would_be_in_scale(monkeypatch):
    """Le due clausole del contratto si sovrappongono quasi ovunque — ma non qui.

    Con `ce01 = 0` il ripiego storico (`or D('1')`) inventava un denominatore, e
    da 1 € di ricavi finti un saldo sopra 1,02 € esce comunque oltre i 365 giorni:
    la clausola «fuori scala» copriva da sola quasi tutto. Sotto quella soglia no.
    1,00 € di crediti danno esattamente 360 giorni — dentro scala, quindi
    plausibili — e il motore li moltiplicherebbe per un fatturato che non esiste,
    azzerandoli. Un denominatore che non c'e' e' degenere perche' non c'e', non
    perche' il numero che produce sembra grande.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _patch_base(db, company_id,
                        bs={"sp05_rimanenze": 0, "sp05a_materie_prime": 0,
                            "sp06_crediti_breve": 1, "sp06a_crediti_clienti_breve": 1,
                            "sp09_disponibilita_liquide": 199999},
                        ce={"ce01_ricavi_vendite": 0, "ce04_altri_ricavi": 600000})
            rows = [dict(forecast_year=2027, revenue_growth_pct=5, **MANUAL_TAX)]
            sc, details = _run(db, company_id, rows)
            assert details[0]["degenerate_turnover_ratio"] == ["dso"]
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            assert bs["sp06_crediti_breve"] == D("1.00")
    finally:
        engine.dispose()


# ── (b) Il denominatore c'e' ma e' troppo piccolo: oltre un anno di giacenza ──

def test_a_dpo_beyond_one_year_carries_the_base_payables(monkeypatch):
    """Acquisti 10.000 contro 140.000 di fornitori: 5.040 giorni.

    Il denominatore e' positivo — `_safe_divide` non protegge da un denominatore
    TRASCURABILE — e moltiplicare gli acquisti proiettati per 5.040/360 gonfia i
    debiti del 10% della crescita dei costi su una massa che non e' un flusso.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # I 340.000 tolti agli acquisti restano fra i costi (`ce12`): il risultato
            # dell'anno base non si muove, quindi il bilancio base resta quadrato.
            _patch_base(db, company_id, ce={"ce05_materie_prime": 0, "ce06_servizi": 10000,
                                            "ce12_oneri_diversi": 345000})
            # Gli acquisti PROIETTATI si muovono (20.000 contro 10.000 dell'anno
            # base): e' cio' che distingue il saldo riportato da quello scalato.
            rows = [dict(forecast_year=2027, revenue_growth_pct=0, ce06_override=20000,
                         **MANUAL_TAX)]
            sc, details = _run(db, company_id, rows)
            assert details[0]["degenerate_turnover_ratio"] == ["dpo"]
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            assert bs["sp16d_debiti_fornitori_breve"] == D("140000.00")
            # Il giorno dichiarato e' quello che il saldo riportato vale DAVVERO
            # sugli acquisti proiettati (20.000): 140.000 / 20.000 × 360 = 2.520.
            # Senza la guardia sarebbero 5.040 giorni e 280.000 di debiti.
            assert details[0]["dpo_applied"] == D("2520")
    finally:
        engine.dispose()


# ── (c) Parita': su un'azienda sana la guardia non scatta mai ──

def test_the_normal_base_year_declares_an_empty_list_and_todays_days(monkeypatch):
    """L'`e2e_kit` normale: la lista e' vuota e i tre giorni sono quelli di oggi.

    E' il punto su cui la guardia si gioca: non deve scattare mai su un'azienda
    sana, o cambierebbe numeri che nessuno le ha chiesto di toccare.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=5, **MANUAL_TAX)
                    for y in (2027, 2028, 2029)]
            sc, details = _run(db, company_id, rows)
            for det in details:
                assert det["degenerate_turnover_ratio"] == []
                assert det["dso_applied"] == D("72")
                assert det["dio_applied"] == D("30")
                assert det["dpo_applied"] == D("144")
    finally:
        engine.dispose()


# ── (d) La guardia e lo scadenziamento non contano due volte la stessa massa ──

def test_the_guard_and_a_runoff_plan_do_not_count_the_same_mass_twice(monkeypatch):
    """Un giorno degenere riporta uno STOCK; un piano scadenzia lo stesso stock.

    `validate_pregresso` impone che la massa dichiarata sia quella del bilancio
    base, quindi il saldo riportato dalla guardia E' il pregresso: sommarci il
    residuo del piano lo conterebbe due volte e il debito non calerebbe mai.
    Vale la regola gia' scritta per gli altri saldi (`_net_of_pregresso`, e il
    Ruling 17 dell'indicizzazione): il piano governa la massa che ha dichiarato,
    il generato parte dalla base scorporata.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # I 340.000 tolti agli acquisti restano fra i costi (`ce12`): il risultato
            # dell'anno base non si muove, quindi il bilancio base resta quadrato.
            _patch_base(db, company_id, ce={"ce05_materie_prime": 0, "ce06_servizi": 10000,
                                            "ce12_oneri_diversi": 345000})
            rows = [dict(forecast_year=y, revenue_growth_pct=0, ce06_override=20000, **MANUAL_TAX)
                    for y in (2027, 2028)]
            rows[0]["pregresso"] = {
                "debiti_fornitori": {"opening": 140000, "amounts": [100000, 40000]}
            }
            sc, details = _run(db, company_id, rows)
            assert details[0]["degenerate_turnover_ratio"] == ["dpo"]
            rows_out = read_forecast_maps(db, sc.id)
            # Anno 1: pagati 100.000, i 40.000 dovuti l'anno DOPO restano a breve,
            # nulla oltre. Anno 2: il piano si chiude e il saldo con lui — nessun
            # generato ci si sovrappone, ne' i 140.000 della guardia ne' i 280.000
            # che il giorno degenere avrebbe prodotto.
            _, bs1, _ = rows_out[0]
            assert bs1["sp16d_debiti_fornitori_breve"] == D("40000.00")
            assert bs1["sp17d_debiti_fornitori_lungo"] == D("0.00")
            _, bs2, _ = rows_out[1]
            assert bs2["sp16d_debiti_fornitori_breve"] == D("0.00")
            assert bs2["sp17d_debiti_fornitori_lungo"] == D("0.00")
            assert details[1]["dpo_applied"] == D("0")
    finally:
        engine.dispose()
