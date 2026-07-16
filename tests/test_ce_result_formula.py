from decimal import Decimal

from calculations.ce_result import calculate_ce_result
from database.models import ForecastIncomeStatement, IncomeStatement


D = Decimal


def test_canonical_formula_includes_ce03a_ce11b_and_legacy_ce17():
    result = calculate_ce_result({
        "ce01_ricavi_vendite": D("100"),
        "ce02_variazioni_rimanenze": D("10"),
        "ce03_lavori_interni": D("20"),
        "ce03a_incrementi_immobilizzazioni": D("30"),
        "ce04_altri_ricavi": D("40"),
        "ce05_materie_prime": D("50"),
        "ce09_ammortamenti": D("5"),
        "ce11b_altri_accantonamenti": D("7"),
        "ce13_proventi_partecipazioni": D("11"),
        "ce14_altri_proventi_finanziari": D("13"),
        "ce15_oneri_finanziari": D("17"),
        "ce16_utili_perdite_cambi": D("19"),
        "ce17_rettifiche_attivita_fin": D("23"),
        "ce18_proventi_straordinari": D("29"),
        "ce19_oneri_straordinari": D("31"),
        "ce20_imposte": D("37"),
    })

    assert result.production_value == D("200")
    assert result.production_cost == D("62")
    assert result.ebitda == D("143")
    assert result.ebit == D("138")
    assert result.financial_result == D("26")
    assert result.value_adjustments == D("23")
    assert result.value_adjustments_source == "aggregate"
    assert result.extraordinary_result == D("-2")
    assert result.profit_before_tax == D("185")
    assert result.net_profit == D("148")


def test_ce17_detail_has_precedence_and_is_not_double_counted():
    result = calculate_ce_result({
        "ce17_rettifiche_attivita_fin": D("999"),
        "ce17a_rivalutazioni": D("80"),
        "ce17b_svalutazioni": D("30"),
    })

    assert result.value_adjustments == D("50")
    assert result.value_adjustments_source == "detail"
    assert result.net_profit == D("50")


def test_ce17_aggregate_is_fallback_when_details_are_zero_or_none():
    result = calculate_ce_result({
        "ce17_rettifiche_attivita_fin": D("12.34"),
        "ce17a_rivalutazioni": None,
        "ce17b_svalutazioni": D("0"),
    })

    assert result.value_adjustments == D("12.34")
    assert result.value_adjustments_source == "aggregate"


def test_missing_and_none_values_are_zero_without_mutating_input():
    source = {"ce01_ricavi_vendite": D("10"), "ce20_imposte": None}
    snapshot = dict(source)

    result = calculate_ce_result(source)

    assert result.net_profit == D("10")
    assert source == snapshot


def test_income_statement_properties_use_canonical_formula():
    statement = IncomeStatement(
        ce01_ricavi_vendite=D("100"),
        ce03a_incrementi_immobilizzazioni=D("20"),
        ce11b_altri_accantonamenti=D("5"),
        ce17_rettifiche_attivita_fin=D("500"),
        ce17a_rivalutazioni=D("40"),
        ce17b_svalutazioni=D("10"),
        ce20_imposte=D("15"),
    )

    assert statement.profit_before_tax == D("145")
    assert statement.net_profit == D("130")


def test_forecast_income_statement_properties_use_canonical_formula():
    statement = ForecastIncomeStatement(
        ce01_ricavi_vendite=D("100"),
        ce03a_incrementi_immobilizzazioni=D("20"),
        ce11b_altri_accantonamenti=D("5"),
        ce17_rettifiche_attivita_fin=D("30"),
        ce20_imposte=D("15"),
    )

    assert statement.profit_before_tax == D("145")
    assert statement.net_profit == D("130")
