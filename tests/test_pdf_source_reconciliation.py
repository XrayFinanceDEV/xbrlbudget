from decimal import Decimal

import fitz

from importers.pdf_extractor_llm import (
    _declared_control_totals,
    _detached_value_page_texts,
    _filter_difference_columns,
    _reconcile_blank_current_ce_cells,
    _reconcile_blank_current_sp_cells,
    _reconcile_ce09_from_source_details,
    _reconcile_credit_aggregates_from_source,
    _reconcile_global_ce_thousand_scale,
    _reconcile_isolated_ce_cost_signs,
    _reconcile_trial_to_declared,
)
from importers.pdf_mapper import IVCEEMapper


D = Decimal


def _budget_594_extraction():
    return {
        "sp01_crediti_soci": D("0"),
        "sp02_immob_immateriali": D("1901.12"),
        "sp03_immob_materiali": D("6917443.77"),
        "sp04_immob_finanziarie": D("0"),
        "sp05_rimanenze": D("0"),
        # Stochastic arithmetic error reproduced on the real PDF.
        "sp06_crediti_breve": D("152288.26"),
        "sp07_crediti_lungo": D("26912.00"),
        "sp08_attivita_finanziarie": D("0"),
        "sp09_disponibilita_liquide": D("448356.68"),
        "sp10_ratei_risconti_attivi": D("13453.70"),
        "sp11_capitale": D("10000"),
        "sp12_riserve": D("0"),
        "sp13_utile_perdita": D("30077.21"),
        "sp14_fondi_rischi": D("0"),
        "sp15_tfr": D("0"),
        "sp16_debiti_breve": D("906001.61"),
        "sp17_debiti_lungo": D("6550280.96"),
        "sp18_ratei_risconti_passivi": D("64017.75"),
        "totale_attivo": D("7560377.53"),
        "totale_passivo": D("7560377.53"),
        "totale_crediti": D("179222.26"),
        "sp06e_crediti_tributari_breve": D("108239.00"),
        "sp06f_imposte_anticipate_breve": D("40434.16"),
        "sp06g_crediti_altri_breve": D("3637.10"),
        "sp07e_crediti_tributari_lungo": D("26912.00"),
    }


def test_budget_594_credit_details_repair_the_aggregate_without_a_plug():
    extracted = _budget_594_extraction()
    assert not IVCEEMapper().validate_balance(extracted)

    reconciled = _reconcile_credit_aggregates_from_source(extracted, "budget_594")

    assert reconciled["sp06_crediti_breve"] == D("152310.26")
    assert reconciled["sp07_crediti_lungo"] == D("26912.00")
    assert IVCEEMapper().validate_balance(reconciled)


def test_credit_aggregate_is_not_changed_when_details_do_not_confirm_source_total():
    extracted = _budget_594_extraction()
    extracted["sp06f_imposte_anticipate_breve"] = D("0")

    reconciled = _reconcile_credit_aggregates_from_source(extracted, "partial")

    assert reconciled["sp06_crediti_breve"] == D("152288.26")


def test_explicit_credit_detail_can_close_the_exact_declared_total_residual():
    extracted = {
        "sp06_crediti_breve": D("1063918"),
        "sp07_crediti_lungo": D("0"),
        "sp06f_imposte_anticipate_breve": D("9044"),
        "totale_crediti": D("1072962"),
    }

    reconciled = _reconcile_credit_aggregates_from_source(extracted, "budget_400")

    assert reconciled["sp06_crediti_breve"] == D("1072962")
    assert reconciled["sp07_crediti_lungo"] == D("0")


def test_credit_aggregate_that_matches_source_total_wins_over_rounded_details():
    extracted = {
        "sp06_crediti_breve": D("467656"),
        "sp07_crediti_lungo": D("0"),
        "sp06a_crediti_clienti_breve": D("467655"),
        "totale_crediti": D("467656"),
    }

    reconciled = _reconcile_credit_aggregates_from_source(extracted, "budget_394")

    assert reconciled["sp06_crediti_breve"] == D("467656")


def test_ce09_detail_rollup_requires_independent_sp_result_confirmation():
    income = {
        "ce01_ricavi_vendite": D("1000"),
        "ce09_ammortamenti": D("500"),
        "ce09a_ammort_immateriali": D("30"),
        "ce09b_ammort_materiali": D("20"),
        "ce20_imposte": D("50"),
    }

    reconciled = _reconcile_ce09_from_source_details(
        income, {"sp13_utile_perdita": D("900")}, "budget_413"
    )
    unconfirmed = _reconcile_ce09_from_source_details(
        income, {"sp13_utile_perdita": D("850")}, "partial"
    )

    assert reconciled["ce09_ammortamenti"] == D("50")
    assert reconciled["_ce09_source_reconciled"] == D("450")
    assert unconfirmed["ce09_ammortamenti"] == D("500")


def test_isolated_negative_cost_is_preserved_only_when_sp_result_confirms_it():
    raw = {
        "ce01_ricavi_vendite": D("10000"),
        "ce12_oneri_diversi": D("-1239"),
    }
    normalized = dict(raw)
    normalized["ce12_oneri_diversi"] = D("1239")

    reconciled = _reconcile_isolated_ce_cost_signs(
        normalized, raw, {"sp13_utile_perdita": D("11239")}, "budget_253"
    )
    unconfirmed = _reconcile_isolated_ce_cost_signs(
        normalized, raw, {"sp13_utile_perdita": D("9000")}, "partial"
    )

    assert reconciled["ce12_oneri_diversi"] == D("-1239")
    assert unconfirmed["ce12_oneri_diversi"] == D("1239")


def test_global_ce_thousand_scale_requires_sp_result_confirmation():
    scaled = {
        "ce01_ricavi_vendite": D("1000000000"),
        "ce05_materie_prime": D("500000000"),
        "ce06_servizi": D("300000000"),
        "ce20_imposte": D("100000000"),
    }

    reconciled = _reconcile_global_ce_thousand_scale(
        scaled, {"sp13_utile_perdita": D("100000")}, "budget_305"
    )
    unconfirmed = _reconcile_global_ce_thousand_scale(
        scaled, {"sp13_utile_perdita": D("90000")}, "partial"
    )

    assert reconciled["ce01_ricavi_vendite"] == D("1000000")
    assert reconciled["_ce_scale_reconciled"] == D("1000")
    assert unconfirmed["ce01_ricavi_vendite"] == D("1000000000")


def test_teamsystem_hyphenated_total_is_read_as_the_control_total():
    text = """
    C TOTALE ATTIVO CIRCOLANTE
    627.578,94
    TOTALE STATO PATRIMONIALE - ATTIVO
    7.560.377,53
    TOTALE STATO PATRIMONIALE - PASSIVO
    7.560.377,53
    """

    totals = _declared_control_totals("unused.pdf", text=text)

    assert totals["attivo"] == D("7560377.53")
    assert totals["passivo"] == D("7560377.53")


def test_section_heading_amount_is_a_control_total_without_totale_keyword():
    text = """
    2
    Stato patrimoniale attivo
    1.075.486,51
    44
    B) Immobilizzazioni
    154.948,27
    1834
    Stato patrimoniale passivo
    1.067.475,73
    1850
    A) Patrimonio netto
    211.742,99
    """

    totals = _declared_control_totals("unused.pdf", text=text)

    assert totals["attivo"] == D("1075486.51")
    assert totals["passivo"] == D("1067475.73")


def test_plain_section_header_does_not_capture_first_detail_as_total():
    text = """
    Stato patrimoniale attivo
    B) Immobilizzazioni
    154.948,27
    Stato patrimoniale passivo
    A) Patrimonio netto
    211.742,99
    """

    totals = _declared_control_totals("unused.pdf", text=text)

    assert totals["attivo"] is None
    assert totals["passivo"] is None


def test_geometry_recovers_explicit_trial_result_and_requires_ce_confirmation(tmp_path):
    pdf_path = tmp_path / "two-column-trial.pdf"
    doc = fitz.open()
    page = doc.new_page(width=800)
    # Insert the amount first to reproduce a content stream whose linear text
    # does not place a number after the left-hand label.
    page.insert_text((600, 150), "200,00")
    page.insert_text((500, 150), "Utile d'esercizio")
    page.insert_text((600, 200), "200,00")
    page.insert_text((500, 200), "Utile d'esercizio")
    doc.save(pdf_path)
    doc.close()

    declared = _declared_control_totals(str(pdf_path))
    assert declared["utile"] == D("200")

    statement = {
        "sp09_disponibilita_liquide": D("1000"),
        "sp16_debiti_breve": D("800"),
        "sp13_utile_perdita": D("0"),
        "totale_attivo": D("1000"),
        "totale_passivo": D("800"),
        "_plug_residual": D("200"),
    }
    recovered = _reconcile_trial_to_declared(
        statement, declared, "trial", ce_result=D("200")
    )
    rejected = _reconcile_trial_to_declared(
        statement, declared, "trial", ce_result=D("150")
    )

    assert recovered["sp13_utile_perdita"] == D("200")
    assert recovered["totale_passivo"] == D("1000")
    assert recovered["_plug_residual"] == D("0")
    assert rejected["sp13_utile_perdita"] == D("0")


def test_detached_amount_pages_are_rejoined_from_matching_coordinates(tmp_path):
    pdf_path = tmp_path / "detached-values.pdf"
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()

    for page_index in range(2):
        label_page = doc[page_index]
        value_page = doc[page_index + 2]
        for row in range(20):
            y = 60 + row * 30
            if page_index == 0 and row == 18:
                label = "TOTALE STATO PATRIMONIALE ATTIVO"
                amount = "2.005.349,48"
            elif page_index == 1 and row == 18:
                label = "TOTALE STATO PATRIMONIALE PASSIVO"
                amount = "2.005.349,48"
            elif page_index == 1 and row == 19:
                label = "Utile dell'esercizio"
                amount = "105.199,81"
            else:
                label = f"Voce contabile {page_index + 1}.{row + 1}"
                amount = f"{row + 1}.000,00"
            label_page.insert_text((50, y), label)
            label_page.insert_text((450, y), "0,00")
            value_page.insert_text((80, y), amount)

    doc.save(pdf_path)
    doc.close()

    with fitz.open(pdf_path) as reopened:
        merged = _detached_value_page_texts(reopened)

    assert len(merged) == 2
    assert "TOTALE STATO PATRIMONIALE ATTIVO 2.005.349,48" in merged[0]
    assert "TOTALE STATO PATRIMONIALE PASSIVO 2.005.349,48" in merged[1]

    totals = _declared_control_totals(str(pdf_path))
    assert totals["attivo"] == D("2005349.48")
    assert totals["passivo"] == D("2005349.48")
    assert totals["utile"] == D("105199.81")


def test_prior_only_ce_cell_is_not_copied_into_current_year(tmp_path):
    pdf_path = tmp_path / "comparative-ce.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((410, 80), "31/12/2025")
    page.insert_text((500, 80), "31/12/2024")
    page.insert_text((70, 150), "11) Variazioni delle rimanenze di materie prime")
    page.insert_text((500, 155), "(300.567)")
    page.insert_text((70, 190), "12) Accantonamento per rischi")
    doc.save(pdf_path)
    doc.close()

    current, prior = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {"ce10_var_rimanenze_mat_prime": D("-300567")},
        {"ce10_var_rimanenze_mat_prime": D("0")},
    )

    assert current["ce10_var_rimanenze_mat_prime"] == D("0")
    assert prior["ce10_var_rimanenze_mat_prime"] == D("-300567")


def test_prior_only_sp_cell_ignores_values_on_the_next_row(tmp_path):
    pdf_path = tmp_path / "comparative-sp.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((410, 80), "31/12/2025")
    page.insert_text((500, 80), "31/12/2024")
    page.insert_text((70, 150), "B) Fondi per rischi e oneri")
    page.insert_text((500, 150), "686.076")
    page.insert_text((70, 163), "C) Trattamento di fine rapporto")
    page.insert_text((410, 163), "394.030")
    doc.save(pdf_path)
    doc.close()

    current, prior = _reconcile_blank_current_sp_cells(
        str(pdf_path),
        {"sp14_fondi_rischi": D("686076")},
        {"sp14_fondi_rischi": D("0")},
    )
    unrelated, _ = _reconcile_blank_current_sp_cells(
        str(pdf_path), {"sp14_fondi_rischi": D("123")}
    )

    assert current["sp14_fondi_rischi"] == D("0")
    assert prior["sp14_fondi_rischi"] == D("686076")
    assert unrelated["sp14_fondi_rischi"] == D("123")


def test_prior_only_ce_aggregate_uses_its_source_row_not_child_details(tmp_path):
    pdf_path = tmp_path / "comparative-ce-details.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((410, 80), "31/12/2025")
    page.insert_text((500, 80), "31/12/2024")
    page.insert_text((70, 150), "20) Imposte sul reddito dell'esercizio")
    page.insert_text((500, 150), "114.561")
    page.insert_text((70, 165), "20.a) Imposte correnti")
    page.insert_text((500, 165), "114.561")
    page.insert_text((70, 180), "IRES")
    page.insert_text((500, 180), "74.181")
    page.insert_text((70, 220), "B.12) Accantonamento per rischi")
    page.insert_text((500, 220), "17.000")
    doc.save(pdf_path)
    doc.close()

    current, prior = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {"ce20_imposte": D("114561"), "ce11_accantonamenti": D("17000")},
        {"ce20_imposte": D("0"), "ce11_accantonamenti": D("0")},
    )

    assert current["ce20_imposte"] == D("0")
    assert prior["ce20_imposte"] == D("114561")
    assert current["ce11_accantonamenti"] == D("0")
    assert prior["ce11_accantonamenti"] == D("17000")


def test_difference_and_percentage_columns_are_removed_by_geometry(tmp_path):
    pdf_path = tmp_path / "four-columns.pdf"
    doc = fitz.open()
    page = doc.new_page(width=700)
    page.insert_text((330, 70), "ESERCIZIO")
    page.insert_text((330, 85), "2025")
    page.insert_text((400, 70), "ESERCIZIO")
    page.insert_text((400, 85), "2024")
    page.insert_text((500, 70), "DIFFERENZA")
    page.insert_text((600, 70), "SCOST.")
    page.insert_text((70, 130), "TOTALE ATTIVO")
    page.insert_text((350, 130), "0,00")
    page.insert_text((420, 130), "259.152,86")
    page.insert_text((520, 130), "259.152,86-")
    page.insert_text((620, 130), "100,000-")
    doc.save(pdf_path)
    doc.close()

    with fitz.open(pdf_path) as reopened:
        filtered = _filter_difference_columns(reopened[0])

    assert filtered is not None
    assert "TOTALE ATTIVO 0,00 259.152,86" in filtered
    assert "259.152,86-" not in filtered
    assert "100,000-" not in filtered
