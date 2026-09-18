"""Gruppo INDICATORI (M2-02D fase 2, v4 pagine 11-18): test Python puri sul
catalogo — nessuna compilazione Typst (quella è coperta da
`test_typst_editorial_plan.py` e `test_pdf_semantic_dossier.py`, entrambi
esercitati manualmente su questo gruppo a ogni pagina aggiunta).
"""
from decimal import Decimal

import pytest

from app.renderers.typst.dossier_catalog import indicatori
from tests.test_final_report_v2 import fixture_report


def _items(pages):
    return [item for page in pages for item in page["items"]]


def _charts(pages):
    return [item for item in _items(pages) if item["kind"] == "chart"]


def _tables(pages):
    return [item for item in _items(pages) if item["kind"] == "table"]


def test_build_returns_the_pages_implemented_so_far():
    """Fase 2 in corso: il gruppo cresce di pagina in pagina (un commit a
    testa) — qui solo l'ordine v4 di ciò che esiste già, mai un conteggio
    fisso che andrebbe aggiornato a ogni pagina aggiunta. Solo "bilancio":
    "startup" ha ricavi e margini tutti a zero su questa fixture sintetica, e
    la pagina "redditivita" (grafico e tabella entrambi vuoti) si toglie dal
    catalogo di conseguenza — vedi `test_a_page_with_no_data_at_all_is_
    dropped_never_shown_blank` qui sotto, che verifica esattamente questo."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    pages = indicatori.build(report)
    assert [page["id"] for page in pages] == ["indicatori", "liquidita", "redditivita", "solidita",
                                               "composizione", "break-even"]


def test_a_page_with_no_data_at_all_is_dropped_never_shown_blank():
    """"Niente pagine vuote" (m2-02d.md): sul fixture "startup" ricavi e
    margini sono tutti a zero/None, quindi "redditivita" (chart+tabella
    entrambi vuoti) sparisce dal catalogo — mai un riquadro bianco."""
    report = fixture_report("startup", [2027, 2028, 2029])
    pages = indicatori.build(report)
    assert "redditivita" not in [page["id"] for page in pages]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_circolante_is_dropped_on_every_synthetic_fixture(workflow):
    """`analytical.activity.*` (DSO/DIO/DPO/ciclo monetario) è sempre
    `source_calculation_unavailable` sulle tre fixture sintetiche — un limite
    del fixture (nessun `calculations.ratios` costruito), non della pagina:
    verificato su AMBIENTA (azienda 575, scenario 18) che la pagina rende
    correttamente coi valori reali (119,0 gg, 125,0 gg, ...)."""
    report = fixture_report(workflow, [2027, 2028, 2029])
    indicator = next(i for i in report.indicator_catalog
                     if i.id == "analytical.activity.receivables_turnover_days")
    assert all(value is None for value in indicator.values)
    pages = indicatori.build(report)
    assert "circolante" not in [page["id"] for page in pages]


def test_kpi_circolante_operativo_sums_the_canonical_statement_rows():
    """Rimanenze + crediti clienti (breve+lungo) − fornitori, sull'ultimo
    periodo con tutt'e quattro le righe valorizzate — sulla fixture
    sintetica tutt'e quattro sono zero (Decimal), quindi il KPI esiste
    (0), non manca (None)."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    periods = indicatori._periods(report)
    kpi = indicatori._kpi_circolante_operativo(report, periods)
    assert kpi is not None
    assert kpi["value"] == "0"
    assert kpi["label"].startswith("circolante operativo · 2029")


def test_liquidita_page_reuses_the_structural_balance_chart_id():
    """`structural_balance` è già dichiarato fra i grafici a barre di
    `chart-layout.json` (e nel catalogo legacy `DOSSIER_CHARTS`, stessi tre
    indicatori CCN/MT/MS): riusarlo qui evita una voce duplicata."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[1]
    assert page["id"] == "liquidita"
    charts = _charts([page])
    assert len(charts) == 1
    assert charts[0]["chart"]["id"] == "structural_balance"
    assert {series["label"] for series in charts[0]["chart"]["series"]} == {"CCN", "Margine di Tesoreria",
                                                                             "Margine di Struttura"}


def test_liquidita_table_omits_current_and_quick_ratio_when_denominator_is_zero():
    """Sulla fixture sintetica (SP tutto a zero) `practice.current_ratio` e
    `practice.quick_ratio` sono `None` per `zero_denominator`: la riga si
    omette, mai un «n.d.» — le altre tre righe restano."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[1]
    table = _tables([page])[0]
    row_labels = [row["cells"][0] for row in table["rows"]]
    assert row_labels == ["Capitale circolante netto", "Margine di tesoreria", "Margine di struttura"]


def test_indicatori_page_has_chart_and_summary_table():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[0]
    assert page["family"] == "Piano e risultati"
    assert page["title"] == "Indicatori e rischi"
    charts = _charts([page])
    assert len(charts) == 1
    chart = charts[0]["chart"]
    assert chart["id"] == "indicatori-debito-cassa-pfn"
    assert chart["unit"] == "eur"
    assert {series["label"] for series in chart["series"]} == {"Debiti finanziari", "Cassa", "PFN"}
    tables = _tables([page])
    assert len(tables) == 1
    row_labels = [row["cells"][0] for row in tables[0]["rows"]]
    assert row_labels == ["PFN", "PFN / EBITDA", "EBITDA margin", "Circolante operativo (CCN)"]


def test_indicatori_kpis_move_into_the_chart_block_not_the_page_strip():
    """Stesso pattern di `piano.py::_ce`: quando la pagina ha un grafico, i
    KPI stanno nella colonna a fianco del grafico (`item["kpis"]`), non nella
    striscia orizzontale di testa (`page["kpis"]`) — altrimenti sarebbero
    duplicati a schermo."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[0]
    assert page["kpis"] == []
    chart_item = _charts([page])[0]
    assert len(chart_item["kpis"]) >= 1


def test_debt_cash_pfn_chart_mixes_three_independent_sources():
    """Il grafico di pagina 11 combina una serie di `structure_series`
    (debiti finanziari), una riga di prospetto (cassa) e un indicatore (PFN):
    nessuno dei tre costruttori di `shared.py`, che leggono una sola fonte,
    può bastare da solo (`_chart`, helper locale del gruppo)."""
    report = fixture_report("bilancio", [2027])
    page = indicatori.build(report)[0]
    chart = _charts([page])[0]["chart"]
    assert len(chart["categories"]) == 1
    for series in chart["series"]:
        assert len(series["values"]) == 1


def test_kpi_delta_needs_at_least_two_periods():
    report = fixture_report("bilancio", [2027])
    periods = indicatori._periods(report)
    assert indicatori._kpi_delta(report, "practice.ccn", "assorbimento circolante", "eur", periods) is None
    report3 = fixture_report("bilancio", [2027, 2028, 2029])
    periods3 = indicatori._periods(report3)
    delta = indicatori._kpi_delta(report3, "practice.ccn", "assorbimento circolante", "eur", periods3)
    assert delta is not None and delta["label"].startswith("assorbimento circolante · 2027-2029")


def test_redditivita_merges_two_v4_panels_into_one_four_series_chart():
    """La v4 affianca due grafici (ROI/ROE; OF/ricavi e OF/MOL) con
    `panel_grid`, un componente che non esiste fuori da questo file e che le
    regole della fase vietano di aggiungere a `pagine/comuni.typ`: qui
    restano un solo grafico a 4 serie percentuali (il tetto `max_series: 4`
    del layout lo permette esattamente) — nessuna pagina KPI in testa, come
    nella v4."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = next(p for p in indicatori.build(report) if p["id"] == "redditivita")
    assert page["kpis"] == []
    charts = _charts([page])
    assert len(charts) == 1
    assert charts[0]["chart"]["unit"] == "percent"
    assert len(charts[0]["chart"]["series"]) <= 4


def test_solidita_table_row_spec_leaves_the_dscr_label_to_the_catalog():
    """`build_indicator_catalog` rinomina `practice.dscr` in "DSCR — proxy
    della pratica" (la sola eccezione all'etichetta del catalogo, per
    l'avvertenza che la v4 richiama esplicitamente): la riga della tabella
    "solidita" passa `display_label=None` apposta, per non riscrivere quel
    testo a mano e perdere l'avvertenza. Il DSCR è `None` su tutte e tre le
    fixture sintetiche (oneri finanziari a zero -> denominatore nullo), quindi
    qui si controlla l'ordine `rows_spec`, non la riga effettivamente resa."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = next(p for p in indicatori.build(report) if p["id"] == "solidita")
    dscr_indicator = next(i for i in report.indicator_catalog if i.id == "practice.dscr")
    assert "proxy della pratica" in dscr_indicator.label
    assert dscr_indicator.values == [None, None, None]
    table = _tables([page])[0]
    assert all("DSCR" not in row["cells"][0] for row in table["rows"])


def test_composizione_uses_at_most_one_table_not_two_separate_ones():
    """Due tabelle separate (impieghi + fonti, come nella v4) non stanno sulla
    stessa pagina fisica insieme al grafico — misurato su AMBIENTA (azienda
    575, scenario 18): la seconda tabella spillava su una pagina senza
    intestazione. Restano unite in un'unica tabella a 6 righe. Sulla fixture
    sintetica "bilancio" (SP tutto a zero) le quote sono tutte
    `zero_denominator`, quindi qui la tabella è assente del tutto — quella
    fusione si osserva sui dati reali, verificati manualmente."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = next(p for p in indicatori.build(report) if p["id"] == "composizione")
    assert len(_tables([page])) <= 1


def test_composizione_chart_uses_only_first_and_last_period():
    """Sostituisce il dumbbell della v4 (confronto chiusura -> fine piano)
    con un grafico a linea limitato a due periodi — stesso disegno visivo,
    nessun componente nuovo."""
    report = fixture_report("bilancio", [2027, 2028, 2029, 2030, 2031])
    page = next((p for p in indicatori.build(report) if p["id"] == "composizione"), None)
    if page is None:
        pytest.skip("cost_incidence assente su questa fixture")
    chart = _charts([page])[0]["chart"]
    assert len(chart["categories"]) == 2


def test_break_even_table_shows_a_negative_safety_margin_without_clamping():
    """Sulla fixture sintetica il margine di contribuzione è nullo/negativo
    (nessuna ipotesi di piano -> quota fissa di default): il "ricavo di
    pareggio" può restare assente, ma quando c'è la tabella non deve mai
    troncare un valore negativo (v. nota della mappatura: la v4 dimostrativa
    ha sempre margine positivo, i dati reali no)."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    group = indicatori._structure_group(report, "break_even")
    safety = indicatori._structure_series(group, "safety_margin_pct")
    negative = [v for v in safety.values if v is not None and v < 0]
    if not negative:
        pytest.skip("nessun margine negativo su questa fixture")
    page = next(p for p in indicatori.build(report) if p["id"] == "break-even")
    table = _tables([page])[0]
    margin_row = next(row for row in table["rows"] if row["cells"][0] == "Margine di sicurezza")
    assert any(cell is not None and cell.startswith("-") for cell in margin_row["cells"][1:])


def test_indicator_table_display_label_none_uses_the_catalog_label():
    """Verifica diretta del meccanismo che `solidita` usa per `practice.dscr`
    (`display_label=None`), su un indicatore presente (`practice.pfn`) cosicché
    la riga risultante si possa davvero leggere."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    periods = indicatori._periods(report)
    pfn = next(i for i in report.indicator_catalog if i.id == "practice.pfn")
    table = indicatori._indicator_table("t", "Titolo", report, periods, [("practice.pfn", None)])
    assert table["rows"][0]["cells"][0] == pfn.label


def test_indicator_table_omits_missing_identifiers_and_drops_when_all_missing():
    report = fixture_report("bilancio", [2027])
    periods = indicatori._periods(report)
    table = indicatori._indicator_table("t", "Titolo", report, periods,
        [("practice.pfn", "PFN"), ("practice.non_existent", "Fantasma")])
    assert table is not None
    assert [row["cells"][0] for row in table["rows"]] == ["PFN"]
    empty = indicatori._indicator_table("t", "Titolo", report, periods, [("practice.non_existent", "Fantasma")])
    assert empty is None
