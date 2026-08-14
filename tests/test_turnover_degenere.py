"""
Un rapporto di rotazione si costruisce dividendo una giacenza per la base
economica che la genera.  ``_safe_divide`` protegge dal denominatore ZERO, non
dal denominatore TRASCURABILE — e sono due cose diverse:

    AIC SRL, anno di riferimento 2025
        ce01_ricavi_vendite     100,92      (il giro d'affari sta su ce04)
        sp06_crediti_breve   1.035.249,26
        rapporto              10.258,12x  = 3,7 milioni di giorni di credito

Moltiplicando i ricavi proiettati per quel rapporto la proiezione produceva
crediti per 166.684.157,69 su un attivo reale di 1,5 M: lo SP persistito non
quadrava (attivo 167.054.466,63 contro passivo 1.572.757,71) e il promote a
budget veniva legittimamente rifiutato.

Un rapporto del genere non descrive l'azienda: descrive una divisione per un
numero prossimo a zero.  Il motore lo tratta come DEGENERE e riporta la
giacenza infrannuale, che è un dato osservato — coerente col principio del
progetto: misurare, mai fabbricare.
"""
from decimal import Decimal as D
from types import SimpleNamespace

from calculations.intra_year_engine import CE_FIELDS, IntraYearEngine


def _zero_projection(**changes):
    projection = {field: D("0") for field, _label in CE_FIELDS}
    projection.update(changes)
    return projection


def _assumption(**changes):
    values = {
        "investments": D("0"),
        "intangible_investments": D("0"),
        "tangible_investments": D("0"),
        "financing_amount": D("0"),
        "existing_debt_repayment_years": None,
        "altri_finanz_repayment_years": None,
        "ce14_override": None,
        "ce15_override": None,
        "ce17_override": None,
        "ce17a_override": None,
        "ce17b_override": None,
        "tax_rate": D("0"),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _scenario_aic():
    """I numeri veri di AIC SRL: ricavi di riferimento ~ zero, crediti reali."""
    partial_bs = SimpleNamespace(
        sp02_immob_immateriali=D("161105.78"),
        sp03_immob_materiali=D("114780.15"),
        sp04_immob_finanziarie=D("195.19"),
        sp05_rimanenze=D("89777.23"),
        sp06_crediti_breve=D("1100048.69"),
        sp07_crediti_lungo=D("0"),
        sp09_disponibilita_liquide=D("0"),
        sp10_ratei_risconti_attivi=D("4450.59"),
        sp11_capitale=D("796159.97"),
        sp12_riserve=D("0"),
        sp14_fondi_rischi=D("0"),
        sp15_tfr=D("83343.04"),
        sp16_debiti_breve=D("814344.65"),
        sp17_debiti_lungo=D("0"),
        sp18_ratei_risconti_passivi=D("4.05"),
    )
    partial_inc = SimpleNamespace(
        ce09a_ammort_immateriali=D("0"),
        ce09b_ammort_materiali=D("0"),
        ce09d_svalutazione_crediti=D("0"),
        ce08a_tfr_accrual=D("0"),
    )
    ref_bs = SimpleNamespace(
        sp05_rimanenze=D("72480"),
        sp06_crediti_breve=D("1035249.26"),
        sp07_crediti_lungo=D("0"),
        sp16_debiti_breve=D("629916.90"),
    )
    ref_inc = SimpleNamespace(
        ce01_ricavi_vendite=D("100.92"),      # <- il denominatore degenere
        ce04_altri_ricavi=D("1252849.27"),
        ce05_materie_prime=D("0"),
        ce06_servizi=D("0"),
        ce07_godimento_beni=D("0"),
    )
    projected_inc = _zero_projection(
        ce01_ricavi_vendite=D("16249"),
        ce04_altri_ricavi=D("1570373"),
    )
    return partial_bs, partial_inc, ref_bs, ref_inc, projected_inc


def test_un_denominatore_trascurabile_non_gonfia_i_crediti():
    partial_bs, partial_inc, ref_bs, ref_inc, projected_inc = _scenario_aic()

    result = IntraYearEngine(None)._project_balance_sheet(
        partial_bs, partial_inc, ref_bs, projected_inc, ref_inc, _assumption(), 9
    )

    # Il valore che il difetto produceva.
    assert result["sp06_crediti_breve"] < D("10000000"), (
        "i crediti proiettati sono esplosi: il rapporto di rotazione è stato "
        "calcolato su un denominatore trascurabile"
    )
    # Il rapporto è degenere -> si riporta la giacenza infrannuale osservata.
    assert result["sp06_crediti_breve"] == D("1100048.69")


def test_lo_stato_patrimoniale_proiettato_quadra():
    partial_bs, partial_inc, ref_bs, ref_inc, projected_inc = _scenario_aic()

    result = IntraYearEngine(None)._project_balance_sheet(
        partial_bs, partial_inc, ref_bs, projected_inc, ref_inc, _assumption(), 9
    )

    attivo = sum(
        result.get(k, D("0")) for k in (
            "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
            "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
            "sp07_crediti_lungo", "sp08_attivita_finanziarie",
            "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi",
        )
    )
    passivo = sum(
        result.get(k, D("0")) for k in (
            "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
            "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve",
            "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
        )
    )
    assert abs(attivo - passivo) <= D("0.01"), f"attivo {attivo} != passivo {passivo}"


def test_un_rapporto_sano_resta_intatto():
    """La guardia deve toccare SOLO i casi degeneri."""
    partial_bs, partial_inc, ref_bs, ref_inc, projected_inc = _scenario_aic()
    # Riferimento sano: 1.000.000 di ricavi, 250.000 di crediti (91 giorni).
    ref_inc.ce01_ricavi_vendite = D("1000000")
    ref_bs.sp06_crediti_breve = D("250000")
    projected_inc["ce01_ricavi_vendite"] = D("1200000")

    result = IntraYearEngine(None)._project_balance_sheet(
        partial_bs, partial_inc, ref_bs, projected_inc, ref_inc, _assumption(), 9
    )

    # 1.200.000 * (250.000 / 1.000.000) = 300.000 — il calcolo normale, invariato.
    assert result["sp06_crediti_breve"] == D("300000")
