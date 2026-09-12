"""Le tre regole del debito bancario vivono in `projection_common` e il motore budget le usa (lotto 3A, Task 3).

Numeri: la catena del prestito 100.000,38 / 4 anni / 4,35% erogato nel 2027, misurata sullo snapshot `452112d`
con `projection_common.residuo_prestiti_nuovi` e `forecast_engine._quota_breve_prestiti_nuovi` (il solo dei
due che il motore usa ancora come proprio alias interno -- `_residuo_prestiti_nuovi` era un alias morto,
rimosso in questo task).
"""
from decimal import Decimal as D

import calculations.forecast_engine as motore_budget
import calculations.projection_common as comune

PRESTITO = [{"year": 2027, "amount": D("100000.38"), "duration": D("4"), "rate": D("0.0435")}]


def _funzione(nome):
    fn = getattr(comune, nome, None)
    assert callable(fn), f"projection_common.{nome} non esiste: la regola vive ancora solo nel motore budget"
    return fn


def test_un_contratto_misto_diventa_due_contratti_con_le_stesse_condizioni():
    dividi = _funzione("contratti_da_riga_finanziamento")
    riga = {"name": "Misto", "amount": 120000, "opening_residual": 12345.67, "duration_years": 4,
            "interest_rate": 5, "grace_years": 1, "balloon_pct": 10}
    condizioni = {"year": 2027, "duration": D("4"), "rate": D("0.05"), "grace_years": D("1"), "balloon_pct": D("10")}
    assert dividi(riga, 2027) == [
        {**condizioni, "amount": D("120000"), "opening_residual": D("0")},
        {**condizioni, "amount": D("0"), "opening_residual": D("12345.67")},
    ]
    assert dividi({"amount": 5000, "duration_years": 2}, 2028) == [
        {"year": 2028, "duration": D("2"), "rate": D("0"), "grace_years": D("0"), "balloon_pct": D("0"),
         "amount": D("5000"), "opening_residual": D("0")}]
    assert dividi({"amount": 5000, "opening_residual": 100, "duration_years": 0}, 2028) == []


def test_residuo_e_quota_a_breve_dei_prestiti_nuovi_sono_la_catena_persistita():
    residuo = _funzione("residuo_prestiti_nuovi")
    quota = _funzione("quota_breve_prestiti_nuovi")
    assert [residuo(PRESTITO, anno) for anno in (2026, 2027, 2028, 2029)] == [
        D("0"), D("75000.29"), D("50000.20"), D("25000.11")]
    assert quota(PRESTITO, 2027, D("75000.29")) == D("25000.09")
    assert quota(PRESTITO, 2029, D("25000.11")) == D("25000.09")
    assert quota(PRESTITO, 2027, D("5000.005")) == D("5000.00")


def test_la_separazione_toglie_al_debito_di_apertura_solo_la_catena_dei_nuovi():
    separa = _funzione("separa_prestiti_nuovi")
    assert separa(D("98457.08"), PRESTITO, 2028) == (D("23456.79"), D("75000.29"))
    assert separa(D("40000.00"), PRESTITO, 2028) == (D("0.00"), D("40000.00"))
    assert separa(D("12345.67"), [], 2028) == (D("12345.67"), D("0"))


def test_un_contratto_col_residuo_e_pregresso_uno_nuovo_no():
    pregresso = _funzione("e_contratto_pregresso")
    assert pregresso({"opening_residual": D("0.01")}) is True
    assert pregresso({"amount": D("1000"), "opening_residual": D("0")}) is False


def test_il_motore_budget_usa_le_funzioni_condivise_non_una_copia():
    # `_residuo_prestiti_nuovi` non e' piu' un alias di forecast_engine (Task 7/C, rimosso: zero
    # chiamanti interni). Il kernel si testa qui direttamente, non via un alias del motore budget.
    assert callable(getattr(comune, "residuo_prestiti_nuovi", None))
    assert motore_budget._quota_breve_prestiti_nuovi is getattr(comune, "quota_breve_prestiti_nuovi", None)
    assert motore_budget._e_contratto_pregresso is getattr(comune, "e_contratto_pregresso", None)
