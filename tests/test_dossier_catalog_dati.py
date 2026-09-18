"""Gruppo DATI del catalogo fisso v4 (M2-02D fase 2): v4 pagine 3-6, bilancio
infrannuale e fonti · rettifiche apportate · dall'infrannuale alla chiusura ·
indicatori dell'infrannuale. Python puro (nessuna compilazione Typst): la
resa fisica è coperta da `test_typst_editorial_plan.py`/`test_pdf_semantic_dossier.py`.

Il fixture `_infrannuale_report` costruisce un report v2 con basi
`observed`/`adjusted`/`closing` reali (non solo `forecast`, a differenza di
`tests.test_final_report_v2.fixture_report`) così i quattro costruttori di
pagina hanno davvero qualcosa da leggere.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.renderers.typst.dossier_catalog import dati, shared as s
from app.schemas.final_report_v2 import StatementPeriod
from app.services.final_report_dossier import DossierSource, extend_dossier
from database.models import BalanceSheet, IncomeStatement
from tests.test_final_report_v2 import fixture_report, v1_report

# Ricavi 100.000, Costi operativi 52.000 (= somma delle 8 voci canoniche),
# EBITDA 48.000, Ammortamenti 8.000, EBIT 40.000, Oneri finanziari 3.000,
# Ris. ante imposte 37.000, Imposte 1.000, Ris. netto 36.000.
_OBSERVED_CE = dict(
    ce01_ricavi_vendite=Decimal("100000"), ce05_materie_prime=Decimal("20000"),
    ce06_servizi=Decimal("10000"), ce07_godimento_beni=Decimal("5000"),
    ce08_costi_personale=Decimal("15000"), ce09_ammortamenti=Decimal("8000"),
    ce12_oneri_diversi=Decimal("2000"), ce15_oneri_finanziari=Decimal("3000"),
    ce20_imposte=Decimal("1000"),
)
# Le rettifiche aumentano il personale di 3.000 e riducono le imposte di 200:
# Costi operativi 55.000, EBITDA 45.000, EBIT 37.000, Ris. ante imposte
# 34.000, Imposte 800, Ris. netto 33.200 — Ammortamenti/Oneri fin. invariati.
_ADJUSTED_CE = dict(_OBSERVED_CE, ce08_costi_personale=Decimal("18000"), ce20_imposte=Decimal("800"))
# Chiusura: Ricavi 200.000, Costi operativi 100.000, EBITDA 100.000,
# Ammortamenti 20.000, EBIT 80.000, Oneri finanziari 6.000, Ris. ante
# imposte 74.000, Imposte 2.000, Ris. netto 72.000.
_CLOSING_CE = dict(
    ce01_ricavi_vendite=Decimal("200000"), ce05_materie_prime=Decimal("40000"),
    ce06_servizi=Decimal("20000"), ce07_godimento_beni=Decimal("10000"),
    ce08_costi_personale=Decimal("25000"), ce09_ammortamenti=Decimal("20000"),
    ce12_oneri_diversi=Decimal("5000"), ce15_oneri_finanziari=Decimal("6000"),
    ce20_imposte=Decimal("2000"),
)


def _zero_bs():
    return {c.name: Decimal("0") for c in BalanceSheet.__table__.columns if c.name.startswith("sp")}


def _zero_ce():
    return {c.name: Decimal("0") for c in IncomeStatement.__table__.columns if c.name.startswith("ce")}


def _infrannuale_report(years=(2027,)):
    """Un report v2 workflow infrannuale con basi observed/adjusted/closing
    reali (la fixture JSON `infrannuale.json` dichiara `source_scenario.
    period_months = 9`, `infrannual_closing.period_end = 2026-09-30`,
    un'unica rettifica confermata: gli assert sotto lo danno per noto)."""
    report = v1_report("infrannuale", list(years))
    sources = []
    period_ends = {"observed": date(2026, 9, 30), "adjusted": date(2026, 9, 30), "closing": date(2026, 12, 31)}
    for basis, months, ce in (("observed", 9, _OBSERVED_CE), ("adjusted", 9, _ADJUSTED_CE),
                              ("closing", 12, _CLOSING_CE)):
        bs, inc = _zero_bs(), _zero_ce()
        inc.update(ce)
        sources.append(DossierSource(
            StatementPeriod(id=f"{basis}:2026", year=2026, label=f"{basis} 2026", basis=basis,
                            period_months=months, period_end=period_ends[basis], source="test-fixture"), bs, inc))
    for year in report.forecast.years:
        bs, inc = _zero_bs(), _zero_ce()
        sources.append(DossierSource(
            StatementPeriod(id=f"forecast:{year.year}", year=year.year, label=str(year.year),
                            basis="forecast", period_months=12, source="test-fixture"),
            bs, inc, fixed_split=(Decimal("40"), Decimal("40"))))
    return extend_dossier(report, sources)


def _table(page, table_id):
    return next(item for item in page["items"] if item.get("kind") == "table" and item["id"] == table_id)


def _row_cells(table, row_id_suffix):
    return next(row["cells"] for row in table["rows"] if row["id"].endswith(":" + row_id_suffix))


@pytest.mark.parametrize("workflow", ("bilancio", "startup"))
def test_dati_pages_are_absent_outside_infrannuale_workflow(workflow):
    report = fixture_report(workflow, [2027])
    assert dati.build(report) == []


def test_dati_pages_appear_in_v4_order_for_infrannuale():
    report = _infrannuale_report()
    pages = dati.build(report)
    assert [page["id"] for page in pages] == ["fonti", "rettifiche", "chiusura", "indicatori-infrannuali"]
    for page in pages:
        assert page["family"] == "Dati di partenza"
        assert page["items"], f"pagina {page['id']} senza contenuto"
        # Vincolo del catalogo: il sottotitolo è una nota di metodo statica,
        # mai un numero.
        assert not any(char.isdigit() for char in page["subtitle"])


def test_no_dati_table_exceeds_five_value_columns():
    report = _infrannuale_report()
    for page in dati.build(report):
        for item in page["items"]:
            if item["kind"] == "table":
                assert len(item["columns"]) - 1 <= 5, (page["id"], item["id"])


def test_content_ids_are_unique_across_the_four_pages():
    report = _infrannuale_report()
    ids = []
    for page in dati.build(report):
        for item in page["items"]:
            if item["kind"] == "table":
                ids.append("heading:" + item["id"])
                ids.extend(row["id"] for row in item["rows"])
            else:
                ids.append(item["id"])
    assert len(ids) == len(set(ids)), ids


# ── Pagina 3 — Bilancio infrannuale e fonti ─────────────────────────────────


def test_fonti_page_kpis_and_ce_table():
    report = _infrannuale_report()
    page = next(p for p in dati.build(report) if p["id"] == "fonti")
    kpi_by_label = {kpi["label"]: kpi for kpi in page["kpis"]}
    assert kpi_by_label["data del bilancio infrannuale"]["value"] == "30.09.2026"
    assert kpi_by_label["periodo osservato"]["value"] == "9 mesi"
    assert kpi_by_label["ricavi prima delle rettifiche"]["value"] == "100000"
    assert kpi_by_label["EBITDA prima delle rettifiche"]["value"] == "48000"

    table = _table(page, "fonti-ce")
    assert table["columns"] == ["Voce", "9M 2026"]
    expected = {
        "ricavi": "100000", "costi-operativi": "52000", "ebitda": "48000", "ammortamenti": "8000",
        "ebit": "40000", "oneri-finanziari": "3000", "risultato-ante-imposte": "37000",
        "imposte": "1000", "risultato-netto": "36000",
    }
    for key, expected_value in expected.items():
        cells = _row_cells(table, key)
        assert Decimal(cells[1]) == Decimal(expected_value), (key, cells)

    perimetro = _table(page, "fonti-perimetro")
    assert perimetro["columns"] == ["Fonte", "Periodo", "Stato"]
    verifica = _row_cells(perimetro, "verifica")
    assert verifica[1] == "9M 2026" and verifica[2] == "disponibile"
    rettifiche_row = _row_cells(perimetro, "rettifiche")
    assert rettifiche_row[1] == "1 evento" and rettifiche_row[2] == "confermato"
    chiusura_row = _row_cells(perimetro, "chiusura")
    assert chiusura_row[1] == "31.12.2026" and chiusura_row[2] == "stimata"
    piano_row = _row_cells(perimetro, "piano")
    assert piano_row[1] == "2027" and piano_row[2] == "disponibile"


# ── Pagina 4 — Rettifiche apportate ─────────────────────────────────────────


def test_rettifiche_page_minimal_table_and_kpis():
    """Vincolo del proprietario: 4 KPI, grafico prima/dopo, UNA tabella a
    9 righe con colonne Prima · Rettifiche · Dopo — niente contropartite."""
    report = _infrannuale_report()
    page = next(p for p in dati.build(report) if p["id"] == "rettifiche")
    tables = [item for item in page["items"] if item["kind"] == "table"]
    assert len(tables) == 1
    charts = [item for item in page["items"] if item["kind"] == "chart"]
    assert len(charts) == 1
    assert charts[0]["chart"]["categories"] == ["Ricavi", "EBITDA", "Utile netto"]
    assert [s["label"] for s in charts[0]["chart"]["series"]] == ["Prima", "Dopo"]

    table = tables[0]
    assert table["columns"] == ["Voce", "Prima", "Rettifiche", "Dopo"]
    assert len(table["rows"]) == 9
    ebitda = _row_cells(table, "ebitda")
    assert [Decimal(c) for c in ebitda[1:]] == [Decimal("48000"), Decimal("-3000"), Decimal("45000")]
    netto = _row_cells(table, "risultato-netto")
    assert [Decimal(c) for c in netto[1:]] == [Decimal("36000"), Decimal("-2800"), Decimal("33200")]

    kpi_by_label = {kpi["label"]: kpi for kpi in charts[0]["kpis"]}
    assert kpi_by_label["rettifiche economiche"]["value"] == "1"
    assert Decimal(kpi_by_label["effetto sull'EBITDA"]["value"]) == Decimal("-3000")
    assert Decimal(kpi_by_label["effetto sul risultato netto"]["value"]) == Decimal("-2800")
    assert Decimal(kpi_by_label["utile 9M rettificato"]["value"]) == Decimal("33200")

    # Il rimando al dettaglio sta nel sottotitolo (niente blocco «note» a
    # parte: su dati reali trabocca su una seconda pagina fisica orfana).
    assert "Allegato D" in page["subtitle"]
    # Niente contropartite: nessuna cella del testo cita edited_label/counterpart.
    assert not any("Cassa" in str(cell) for row in table["rows"] for cell in row["cells"])


# ── Pagina 5 — Dall'infrannuale alla chiusura ───────────────────────────────


def test_chiusura_page_table_and_kpis():
    report = _infrannuale_report()
    page = next(p for p in dati.build(report) if p["id"] == "chiusura")
    table = _table(page, "chiusura-passaggio-tabella")
    assert table["columns"] == ["Voce", "Rettificato", "Stimato residuo", "Chiusura"]
    ricavi = _row_cells(table, "ricavi")
    assert [Decimal(c) for c in ricavi[1:]] == [Decimal("100000"), Decimal("100000"), Decimal("200000")]
    ebitda = _row_cells(table, "ebitda")
    assert [Decimal(c) for c in ebitda[1:]] == [Decimal("45000"), Decimal("55000"), Decimal("100000")]

    chart = next(item for item in page["items"] if item["kind"] == "chart")
    assert chart["chart"]["categories"] == ["Rettificato", "Stimato residuo", "Chiusura"]
    assert [ser["label"] for ser in chart["chart"]["series"]] == ["Ricavi", "EBITDA"]

    kpi_by_label = {kpi["label"]: kpi for kpi in chart["kpis"]}
    assert Decimal(kpi_by_label["ricavi osservati rettificati"]["value"]) == Decimal("100000")
    assert Decimal(kpi_by_label["ricavi stimati · periodo residuo"]["value"]) == Decimal("100000")
    assert Decimal(kpi_by_label["ricavi di chiusura"]["value"]) == Decimal("200000")
    assert Decimal(kpi_by_label["EBITDA di chiusura"]["value"]) == Decimal("100000")


# ── Pagina 6 — Indicatori dell'infrannuale ──────────────────────────────────


def test_indicatori_infrannuali_page_kpis_and_shape():
    report = _infrannuale_report()
    page = next(p for p in dati.build(report) if p["id"] == "indicatori-infrannuali")
    chart_items = [item for item in page["items"] if item["kind"] == "chart"]
    assert len(chart_items) == 1
    kpi_by_label = {kpi["label"]: kpi for kpi in chart_items[0]["kpis"]}
    assert kpi_by_label["indicatori della pratica"]["value"] == "15"
    # EBITDA margin è CE-puro (ebitda/ricavi): 45.000/100.000 rettificato,
    # 100.000/200.000 chiusura — due basi diverse, due valori diversi.
    margin_adj = Decimal(kpi_by_label["EBITDA margin · rettificato"]["value"])
    margin_close = Decimal(kpi_by_label["EBITDA margin · chiusura"]["value"])
    assert margin_adj == Decimal("45")
    assert margin_close == Decimal("50")
    assert kpi_by_label["periodi di durata diversa"]["value"] == "9 mesi"
    assert kpi_by_label["periodi di durata diversa"]["to"] == "12 mesi"

    chart = chart_items[0]["chart"]
    assert [ser["label"] for ser in chart["series"]] == ["Rettificato", "Chiusura"]
    ebitda_margin_label = s.indicator_by_id(report, "practice.ebitda_margin").label
    assert ebitda_margin_label in chart["categories"]

    table = _table(page, "indicatori-infrannuali-tabella")
    assert table["columns"] == ["Indicatore", "Rettificato", "Chiusura"]
    assert len(table["rows"]) <= 8
    for row in table["rows"]:
        assert row["cells"][1] is not None or row["cells"][2] is not None
        assert row["units"][1] == row["units"][2]

    assert "Allegato F" in page["subtitle"]


def test_indicatori_infrannuali_dropped_values_never_leave_none_rows():
    """`current_ratio`/`copertura_immob`/`indipendenza`/`roi`/`roe` dividono
    per un aggregato patrimoniale zero in questo fixture (BS azzerato): la
    riga sparisce, non compare come «n.d./n.d.»."""
    report = _infrannuale_report()
    page = next(p for p in dati.build(report) if p["id"] == "indicatori-infrannuali")
    table = _table(page, "indicatori-infrannuali-tabella")
    row_ids = {row["id"].rsplit(":", 1)[-1] for row in table["rows"]}
    assert "practice.pfn_ebitda" in row_ids  # pfn=0 / ebitda≠0: un valore reale, non n.d.
    assert "practice.current_ratio" not in row_ids  # 0/0: nessun valore da mostrare
