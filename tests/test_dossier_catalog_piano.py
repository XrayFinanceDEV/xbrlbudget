"""Gruppo PIANO E RISULTATI (v4 pagine 7-10): ipotesi, CE, SP e flussi
previsionali. Solo Python, nessuna compilazione Typst — quella è coperta da
`test_typst_editorial_plan.py`/`test_pdf_semantic_dossier.py` (invarianti
generali) e dalla verifica visiva su AMBIENTA (ricevuta SDD del lotto).

`test_dossier_catalog.py` copre l'ordine del catalogo e il vincolo delle 5
colonne per l'intero pacchetto: qui solo ciò che è specifico di «ipotesi»,
«sp» e «flussi» — struttura, valori derivati, e la correzione dei due KPI di
«ce» che mancavano su un report reale (v. la nota sopra `kpi_statement` in
`shared.py`).
"""
from decimal import Decimal

import pytest

from app.renderers.typst.dossier_catalog import build_inventory, piano, shared
from tests.test_final_report_v2 import fixture_report


def _page(report, page_id):
    return next(page for page in piano.build(report) if page["id"] == page_id)


def _table(page, table_id):
    return next(item for item in page["items"] if item["kind"] == "table" and item["id"] == table_id)


def _kpi_map(page):
    """`{label: value}` da dove i KPI vivono davvero (in cima alla pagina se
    non c'è grafico, dentro il blocco grafico se c'è — mai i due insieme, per
    costruzione: v. `_ce`/`_sp`/`_flussi`, `"kpis": [] if block is not None
    else kpis`)."""
    if page["kpis"]:
        return {kpi["label"]: kpi["value"] for kpi in page["kpis"]}
    chart = next((item for item in page["items"] if item["kind"] == "chart"), None)
    return {kpi["label"]: kpi["value"] for kpi in chart["kpis"]} if chart else {}


def _set_cashflow_row(report, code, values):
    """Sovrascrive i valori (sugli anni di piano) di una riga di
    `detailed_statements['cashflow']` — la fixture di test non passa mai un
    `DossierSource.cashflow` popolato (tutte le pagine dei flussi restano
    «n.d.» sulle fixture condivise), quindi qui si inietta un rendiconto
    minimo, sulle sole righe che le pagine di questo gruppo leggono."""
    statement = shared.statement_by_id(report, "cashflow")
    periods = shared.forecast_periods(statement)
    row_obj = shared.statement_row(statement, code)
    by_id = {period.id: value for period, value in zip(statement.periods, row_obj.values)}
    by_id.update({period.id: value for period, value in zip(periods, values)})
    row_obj.values = [by_id[period.id] for period in statement.periods]
    row_obj.unavailable_reasons = [None if by_id[period.id] is not None else "source_field_unavailable"
                                   for period in statement.periods]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_piano_group_builds_four_pages_in_v4_order(workflow):
    report = fixture_report(workflow, [2027, 2028, 2029])
    ids = [page["id"] for page in piano.build(report)]
    assert ids == ["ipotesi", "ce", "sp", "flussi"]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_all_four_pages_use_plan_years_only_never_the_closing_anchor(workflow):
    """CE/SP/Flussi devono rendere identici sui tre workflow — solo
    l'infrannuale ha un periodo di chiusura, e usarlo come ancora (come fa la
    v4 dimostrativa) romperebbe bilancio/startup. `forecast_periods`, mai
    `select_periods` (m2-02d-catalogo.md)."""
    report = fixture_report(workflow, [2027, 2028, 2029])
    statement = shared.statement_by_id(report, "income_statement")
    expected_years = [period.year for period in shared.forecast_periods(statement)]
    for page_id in ("ce", "sp", "flussi"):
        page = _page(report, page_id)
        table = next(item for item in page["items"] if item["kind"] == "table")
        years = [column for column in table["columns"][1:]]
        assert len(years) == len(expected_years)
        for year, column in zip(expected_years, years):
            assert str(year) in column


def test_ce_kpi_band_finds_ebitda_and_net_profit_via_detailed_statements():
    """Regressione: `kpi_forecast(report, "income_statement", ("ebitda",), ...)`
    non trova mai un codice "ebitda" fra le righe grezze di `forecast.years`
    (solo colonne persistite vere, mai una `@property` come `ebitda`/
    `net_profit`) — su un report reale il riquadro KPI di «ce» mostrava così
    solo 2 dei 4 KPI dichiarati (misurato su AMBIENTA/575, scenario 18).
    `kpi_statement` legge da `detailed_statements`, dove l'aggregato è già
    calcolato: qui si verifica che compaia, con il valore giusto."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = _page(report, "ce")
    by_label = _kpi_map(page)
    statement = shared.statement_by_id(report, "income_statement")
    periods = shared.forecast_periods(statement)
    ebitda_row = shared.statement_row(statement, "ebitda")
    net_profit_row = shared.statement_row(statement, "net_profit")
    expected_ebitda = shared.values_for_periods(ebitda_row, statement, periods)[-1]
    expected_net_profit = shared.values_for_periods(net_profit_row, statement, periods)[-1]
    assert Decimal(by_label[f"EBITDA · {periods[-1].year}"]) == expected_ebitda
    assert Decimal(by_label[f"utile netto · {periods[-1].year}"]) == expected_net_profit


def test_ipotesi_driver_table_has_six_rows_and_aree_table_has_seven():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = _page(report, "ipotesi")
    driver = _table(page, "driver")
    assert [row["cells"][0] for row in driver["rows"]] == [
        "Ricavi · crescita annua", "Costi operativi / ricavi", "Ammortamenti",
        "Investimenti", "Rimborso debito", "Imposte / risultato ante imposte",
    ]
    aree = _table(page, "aree-piano")
    assert len(aree["rows"]) == 7
    assert [row["cells"][0] for row in aree["rows"]] == [section.title for section in report.assumption_sections]
    # Nessuna colonna tecnica (Provenienza/Attiva/Indisponibilità), solo Area
    # e una descrizione editoriale — vincolo del proprietario, 2026-09-17.
    assert aree["columns"] == ["Area", "Ipotesi da documentare"]


def test_ipotesi_revenue_growth_kpi_and_table_row_read_the_same_assumption():
    # La fixture "infrannuale" (a differenza di "bilancio"/"startup", con le
    # sette sezioni tutte vuote) dichiara `revenue_growth_pct` con 3 valori —
    # la stessa lunghezza degli anni di piano richiesti qui, quindi nessun
    # troncamento/padding entra in gioco: verifica la lettura diretta.
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    fatturato = shared.assumption_section_by_key(report, "fatturato")
    growth = shared.assumption_value(fatturato, "revenue_growth_pct")
    assert growth is not None and len(growth.values) == 3
    page = _page(report, "ipotesi")
    driver = _table(page, "driver")
    row = next(r for r in driver["rows"] if r["cells"][0] == "Ricavi · crescita annua")
    assert row["cells"][1:] == [shared.exact(v) for v in growth.values]
    growth_kpi = next(kpi for kpi in page["kpis"] if kpi["label"] == "crescita ricavi")
    assert growth_kpi["series"] == [shared.exact(v) for v in growth.values]


def test_ipotesi_assumption_values_truncated_when_longer_than_plan_years():
    """Nessun `model_validator` in `final_report.py` lega `AssumptionValue.values`
    al numero di `forecast.years`: la fixture "infrannuale" dichiara 3 valori
    per `revenue_growth_pct` a prescindere dagli anni richiesti — con solo 2
    anni di piano la riga deve troncare ai primi 2, mai far saltare la pagina
    (prima di questo fix: `ValueError: dossier table rows must follow
    columns`, perché la riga aveva 3 celle e le colonne solo 2)."""
    report = fixture_report("infrannuale", [2027, 2028])
    fatturato = shared.assumption_section_by_key(report, "fatturato")
    growth = shared.assumption_value(fatturato, "revenue_growth_pct")
    assert len(growth.values) == 3  # la fixture grezza non si adegua a `years`
    page = _page(report, "ipotesi")
    driver = _table(page, "driver")
    for row in driver["rows"]:
        assert len(row["cells"]) == len(driver["columns"]) == 3  # Voce + 2 anni
    growth_row = next(r for r in driver["rows"] if r["cells"][0] == "Ricavi · crescita annua")
    assert growth_row["cells"][1:] == [shared.exact(v) for v in growth.values[:2]]


def test_ipotesi_assumption_values_padded_when_the_field_is_entirely_absent():
    """La fixture "bilancio" ha le sette sezioni vuote: una riga del driver
    table la cui ipotesi non esiste affatto resta «n.d.» per ogni anno, mai
    un `AttributeError`."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = _page(report, "ipotesi")
    driver = _table(page, "driver")
    growth_row = next(r for r in driver["rows"] if r["cells"][0] == "Ricavi · crescita annua")
    assert growth_row["cells"][1:] == [None, None, None]


def test_sp_summary_table_has_eleven_rows_and_assets_equal_liabilities():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = _page(report, "sp")
    table = _table(page, "sp-summary")
    assert [row["cells"][0] for row in table["rows"]] == [
        "Immobilizzazioni nette", "Rimanenze", "Crediti commerciali", "Disponibilità liquide",
        "Altre attività", "Totale attivo", "Patrimonio netto", "Debiti finanziari",
        "Debiti commerciali", "Altre passività", "Totale passivo e netto",
    ]
    # La fixture minima non è un bilancio vero (un solo campo di SP è
    # popolato: `sp09_disponibilita_liquide`), quindi attivo e passivo NON
    # tornano qui — l'identità contabile si verifica sui dati reali
    # (AMBIENTA, ricevuta SDD), non su questa fixture. Qui si verifica solo
    # che le due righe leggano esattamente le righe canoniche attese.
    statement = shared.statement_by_id(report, "balance_sheet")
    periods = shared.forecast_periods(statement)
    expected_total_assets = shared.values_for_periods(
        shared.statement_row(statement, "total_assets"), statement, periods)
    expected_total_liabilities = shared.values_for_periods(
        shared.statement_row(statement, piano._SP_TOTAL_LIABILITIES_CODE), statement, periods)
    totale_attivo = next(r for r in table["rows"] if r["cells"][0] == "Totale attivo")
    totale_passivo = next(r for r in table["rows"] if r["cells"][0] == "Totale passivo e netto")
    assert totale_attivo["cells"][1:] == [shared.exact(v) for v in expected_total_assets]
    assert totale_passivo["cells"][1:] == [shared.exact(v) for v in expected_total_liabilities]
    # Nessun sottotitolo su «sp»: senza, la pagina non entra nel vincolo di
    # una pagina fisica con l'11esima riga (v. il commit che l'ha tolto).
    assert page["subtitle"] is None


def test_sp_commercial_receivables_row_is_the_sum_of_short_and_long():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    statement = shared.statement_by_id(report, "balance_sheet")
    periods = shared.forecast_periods(statement)
    short_row = shared.statement_row(statement, "sp06a_crediti_clienti_breve")
    long_row = shared.statement_row(statement, "sp07a_crediti_clienti_lungo")
    short_values = shared.values_for_periods(short_row, statement, periods)
    long_values = shared.values_for_periods(long_row, statement, periods)
    expected = [shared.exact(a + b) for a, b in zip(short_values, long_values)]
    page = _page(report, "sp")
    table = _table(page, "sp-summary")
    row = next(r for r in table["rows"] if r["cells"][0] == "Crediti commerciali")
    assert row["cells"][1:] == expected


def _flussi_report():
    """La fixture condivisa non passa mai un `DossierSource.cashflow`
    popolato (ogni riga del rendiconto resta «n.d.» su bilancio/infrannuale/
    startup): qui si inietta un rendiconto minimo sulle sole righe che
    `_flussi` legge, per verificare somme e segno senza dipendere da un
    fixture DB reale (quello è AMBIENTA, coperto dalla verifica visiva)."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    _set_cashflow_row(report, "operating.total_operating_cashflow",
                      [Decimal("100000"), Decimal("120000"), Decimal("150000")])
    _set_cashflow_row(report, "investing.total_investing_cashflow",
                      [Decimal("-50000"), Decimal("0"), Decimal("0")])
    _set_cashflow_row(report, "financing.total_financing_cashflow",
                      [Decimal("30000"), Decimal("-20000"), Decimal("-20000")])
    _set_cashflow_row(report, "financing.third_party_funds.decreases",
                      [Decimal("0"), Decimal("20000"), Decimal("20000")])
    _set_cashflow_row(report, "financing.own_funds.decreases",
                      [Decimal("0"), Decimal("0"), Decimal("0")])
    _set_cashflow_row(report, "cash_reconciliation.cash_beginning",
                      [Decimal("10"), Decimal("50010"), Decimal("150010")])
    _set_cashflow_row(report, "cash_reconciliation.cash_ending",
                      [Decimal("50010"), Decimal("150010"), Decimal("280010")])
    _set_cashflow_row(report, "cash_reconciliation.total_cashflow",
                      [Decimal("50000"), Decimal("100000"), Decimal("130000")])
    return report


def test_flussi_table_has_six_rows_and_kpis_match_the_underlying_sums():
    report = _flussi_report()
    page = _page(report, "flussi")
    table = _table(page, "cf-summary")
    assert [row["cells"][0] for row in table["rows"]] == [
        "Cassa iniziale", "Flusso operativo", "Flusso di investimento",
        "Flusso finanziario", "Variazione di cassa", "Cassa finale",
    ]
    by_label = _kpi_map(page)
    assert Decimal(by_label["flussi operativi"]) == Decimal("370000")
    assert Decimal(by_label["investimenti"]) == Decimal("-50000")
    # Cassa finale dell'ultimo anno meno cassa iniziale del primo, non la
    # somma dei flussi netti annui — le due coincidono qui per costruzione
    # della fixture, ma la formula è quella dichiarata dalla mappatura v4.
    assert Decimal(by_label["variazione di cassa"]) == Decimal("280010") - Decimal("10")


def test_flussi_repayments_kpi_is_negated_from_the_decrease_sub_lines():
    """Le due righe di dettaglio (`third_party_funds.decreases`,
    `own_funds.decreases`) sono una magnitudine positiva di decremento, non
    il flusso netto già firmato — il segno si inverte per mostrarle come
    un'uscita (mappatura v4 pagina 10, nota «segno da verificare in resa»)."""
    report = _flussi_report()
    page = _page(report, "flussi")
    by_label = _kpi_map(page)
    # third_party_funds.decreases somma 40.000, own_funds.decreases 0: la
    # riga «rimborsi» deve essere il negativo della somma, un'uscita.
    assert Decimal(by_label["rimborsi"]) == Decimal("-40000")


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_five_column_constraint_holds_with_five_plan_years(workflow):
    report = fixture_report(workflow, list(range(2027, 2032)))
    for page in piano.build(report):
        for item in page["items"]:
            if item["kind"] == "table":
                assert len(item["columns"]) - 1 <= 5, (page["id"], item["id"])


def test_expected_content_inventory_includes_the_three_new_pages():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    ids = [page["id"] for page in build_inventory(report)]
    assert ids.index("sintesi") < ids.index("ipotesi") < ids.index("ce") < ids.index("sp") < ids.index("flussi") < ids.index("allegati")
