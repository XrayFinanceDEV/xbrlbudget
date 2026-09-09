from decimal import Decimal

from backend.app.services.assumptions_service import build_assumption_row
from database import models
from tests.e2e_kit import memory_sessions


def test_row_is_transient_and_carries_every_column_default():
    row = build_assumption_row(7, {"forecast_year": 2027, "revenue_growth_pct": 5})
    assert isinstance(row, models.BudgetAssumptions)
    assert row.scenario_id == 7 and row.forecast_year == 2027
    assert row.revenue_growth_pct == 5
    # default del bulk, non dello schema: 27.9, 40, 20 — confrontati come
    # Decimal, non come float: la riga esce normalizzata alla scala della
    # colonna (Numeric(10,6)), e Decimal('27.900000') != float 27.9 (27.9 non
    # ha una rappresentazione binaria esatta).
    assert row.tax_rate == Decimal("27.9")
    assert row.fixed_materials_percentage == 40.0
    assert row.depreciation_rate == 20.0
    assert row.financing_amount == 0.0            # null -> 0
    assert row.cash_sweep_enabled is False
    assert row.ce05_override is None
    # nessuna colonna e' rimasta None fra quelle NOT NULL del modello
    for col in models.BudgetAssumptions.__table__.columns:
        if not col.nullable and col.name not in ("id", "created_at", "updated_at"):
            assert getattr(row, col.name) is not None, col.name


def test_json_fields_are_encoded_like_the_bulk():
    row = build_assumption_row(7, {
        "forecast_year": 2027,
        "financing_loans": [{"amount": Decimal("1000"), "duration_years": 5}],
        "sp_overrides": {"sp09_disponibilita_liquide": Decimal("12.5")},
    })
    assert row.financing_loans == [{"amount": 1000.0, "duration_years": 5}]
    assert row.sp_overrides == {"sp09_disponibilita_liquide": 12.5}


# Le quattro coppie sotto sono MISURATE, non trascritte: `Decimal("%.2f" % float(v))`
# contro `Decimal(v).quantize(Decimal("0.01"))`, e per tre di esse i due
# arrotondamenti danno numeri diversi.
#   1234.565 -> format 1234.57 / quantize 1234.56
#   0.005    -> format    0.01 / quantize    0.00
#   2.675    -> format    2.67 / quantize    2.68   (l'errore non ha un verso solo)
#   0.125    -> format    0.12 / quantize    0.12   (qui coincidono: il caso che
#                                                    NON discrimina, tenuto per
#                                                    non dedurre una regola da
#                                                    soli valori che divergono)
_ROUNDING_CASES = [
    (Decimal("1234.565"), Decimal("1234.57"), Decimal("1234.56")),
    (Decimal("0.005"), Decimal("0.01"), Decimal("0.00")),
    (Decimal("2.675"), Decimal("2.67"), Decimal("2.68")),
    (Decimal("0.125"), Decimal("0.12"), Decimal("0.12")),
]


def test_la_riga_transitoria_arrotonda_come_il_bind_sqlite_non_come_quantize():
    """La regola piu' delicata di `_normalize_numeric_fields`, senza rete finora.

    Il docstring della funzione dichiara che la quantizzazione alla scala della
    colonna usa la FORMATTAZIONE del bind SQLite e non `.quantize()`, che
    arrotonda diversamente. E' quella scelta a garantire «stessi numeri fra
    anteprima e salvataggio»: l'anteprima costruisce una riga transitoria che
    non tocca mai il DB, il salvataggio fa INSERT + SELECT. Se le due
    arrotondassero in modo diverso, la stessa ipotesi darebbe due previsionali
    diversi a seconda del pulsante premuto — e nessun controllo se ne
    accorgerebbe.

    Sostituendo il format con `.quantize()` questo test cade su tre dei quattro
    valori (`test_forecast_preview.py` restava invece tutto verde).
    """
    for value, atteso_format, da_quantize in _ROUNDING_CASES:
        row = build_assumption_row(1, {"forecast_year": 2027, "tangible_investments": value})
        assert row.tangible_investments == atteso_format, (
            f"{value}: la riga transitoria deve arrotondare come la formattazione "
            f"del bind SQLite ({atteso_format}); .quantize() darebbe {da_quantize}"
        )


def test_lanteprima_e_il_salvataggio_arrotondano_allo_stesso_modo():
    """L'altra meta' della stessa regola, misurata contro il DB vero.

    Non basta pinnare il numero che la funzione produce oggi: cio' che conta e'
    che coincida con quello che SQLite restituisce dopo un giro completo. Se
    qualcuno cambia arrotondamento, e' questo confronto a dire che i due
    percorsi si sono separati.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = models.Company(name="round", tax_id="ROUND", sector=1, user_id="round")
            db.add(company)
            db.flush()
            scenario = models.BudgetScenario(company_id=company.id, name="s", base_year=2026)
            db.add(scenario)
            db.flush()
            for i, (value, _atteso, _q) in enumerate(_ROUNDING_CASES):
                db.add(models.BudgetAssumptions(
                    scenario_id=scenario.id, forecast_year=2027 + i, tangible_investments=value))
            db.commit()
            db.expire_all()

            for i, (value, _atteso, da_quantize) in enumerate(_ROUNDING_CASES):
                persistito = db.query(models.BudgetAssumptions).filter_by(
                    forecast_year=2027 + i).one().tangible_investments
                transitorio = build_assumption_row(
                    1, {"forecast_year": 2027 + i, "tangible_investments": value}).tangible_investments
                assert transitorio == persistito, (
                    f"{value}: l'anteprima arrotonda a {transitorio} e il salvataggio a "
                    f"{persistito}. L'arrotondamento della riga transitoria deve essere "
                    f"quello della formattazione del bind SQLite, non .quantize() "
                    f"(che darebbe {da_quantize})"
                )
    finally:
        engine.dispose()
