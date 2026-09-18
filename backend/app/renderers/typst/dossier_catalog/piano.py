"""Gruppo PIANO E RISULTATI (v4 pagine 7-10): ipotesi del piano, conto economico
previsionale, stato patrimoniale previsionale, flussi di cassa e sostenibilità.

Tutte e quattro le pagine sono anni-di-piano soltanto (`shared.forecast_periods`,
mai `select_periods`): la pagina deve rendere identica sui tre workflow
(bilancio, infrannuale, startup), e solo l'infrannuale ha un periodo di
chiusura — usarlo come ancora, come fa la v4 dimostrativa, romperebbe le
altre due. Precedente di «ce» (v4 pagina 8), fondazione M2-02D.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "piano"

FAMILY = "Piano e risultati"

ZERO = Decimal("0")

# Le nove righe di sintesi del CE previsionale (vincolo del proprietario,
# 2026-09-17: «rettifiche al minimo» si applica anche qui — la pagina di
# sezione mostra un aggregato, non le 47 righe del prospetto completo, che
# stanno nell'Allegato A). Etichette brevi, non il testo legale della riga
# (`row.label`), per restare leggibili nella tabella di sintesi — stesso
# principio di `_FORECAST_LABEL_OVERRIDES` nel vecchio inventario: si sceglie
# quale testo stampare per una riga canonica nota, non se ne inventa il
# valore. `production_value` (non `ce01_ricavi_vendite`) è la stessa base
# usata dal grafico di sintesi (v. apertura.py), così Ricavi − Costi = EBITDA
# torna visibile nella tabella.
_CE_SUMMARY_ROWS: tuple[tuple[str, str], ...] = (
    ("production_value", "Ricavi"),
    ("production_cost", "Costi operativi"),
    ("ebitda", "EBITDA"),
    ("ce09_ammortamenti", "Ammortamenti"),
    ("ebit", "EBIT"),
    ("ce15_oneri_finanziari", "Oneri finanziari"),
    ("profit_before_tax", "Risultato ante imposte"),
    ("ce20_imposte", "Imposte"),
    ("net_profit", "Risultato netto"),
)

# Le sei righe della «Riconciliazione della liquidità» (v4 pagina 10).
_CASHFLOW_SUMMARY_ROWS: tuple[tuple[str, str], ...] = (
    ("cash_reconciliation.cash_beginning", "Cassa iniziale"),
    ("operating.total_operating_cashflow", "Flusso operativo"),
    ("investing.total_investing_cashflow", "Flusso di investimento"),
    ("financing.total_financing_cashflow", "Flusso finanziario"),
    ("cash_reconciliation.total_cashflow", "Variazione di cassa"),
    ("cash_reconciliation.cash_ending", "Cassa finale"),
)

# Le undici righe dello «Stato patrimoniale» di sintesi (v4 pagina 9): tre
# derivate per somma/residuo (crediti commerciali, altre attività), le
# restanti righe di prospetto o serie strutturali dirette. Costruite in
# `_sp_summary_table`, non qui, perché tre di loro non sono un singolo codice.
_SP_COMMERCIAL_RECEIVABLE_CODES = ("sp06a_crediti_clienti_breve", "sp07a_crediti_clienti_lungo")
_SP_TOTAL_LIABILITIES_CODE = ("sp11_capitale+sp12_riserve+sp13_utile_perdita"
                              "+sp16_debiti_breve+sp17_debiti_lungo+sp14_fondi_rischi"
                              "+sp15_tfr+sp18_ratei_risconti_passivi")
_SP_EQUITY_CODE = "sp11_capitale+sp12_riserve+sp13_utile_perdita"
_SP_TRADE_PAYABLES_CODE = "sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo"

# Testo statico per la tabella «Le sette aree del piano» (v4 pagina 7): il
# testo descrittivo di ogni riga è editoriale (m2-02d-catalogo.md, «il testo
# descrittivo di ogni riga è editoriale»), non un dato del modello — la v4
# dimostrativa la scrive a mano nello stesso modo (build-dossier-preview.py).
# Le SETTE aree sono quelle vere del modello (`assumption_sections[].key`),
# non i nomi dimostrativi della v4 campione («Altre voci CE», «Pregresso e
# nuovo»): il modello non ha quelle due sezioni, ha «Patrimoniale pregresso»
# e «Patrimoniale piano».
_AREA_DESCRIPTIONS: dict[str, str] = {
    "scenario": "Inflazione e ipotesi di scenario generale.",
    "fatturato": "Crescita dei ricavi delle vendite e degli altri ricavi.",
    "costi": "Incidenza dei costi operativi e ripartizione fissi/variabili.",
    "circolante": "Giorni di incasso, giacenza e pagamento del circolante.",
    "patrimoniale-pregresso": "Debito pregresso, fidi e piano di rimborso già in essere.",
    "patrimoniale-piano": "Investimenti, nuovo finanziamento, ammortamenti e cassa.",
    "imposte": "Aliquota fiscale, acconti e differenze temporanee.",
}


def _sum_two_rows(statement: Any, periods: list[Any], codes: tuple[str, str]) -> list[Any]:
    """Somma di due righe canoniche, periodo per periodo — «derivabile»
    (mappatura v4, pagina 9, «Crediti commerciali»): un periodo con una delle
    due masse assente resta assente, mai sostituito da un mezzo totale."""
    rows = [s.statement_row(statement, code) for code in codes]
    columns = [s.values_for_periods(row_obj, statement, periods) for row_obj in rows]
    return [None if any(v is None for v in pair) else sum(pair, ZERO) for pair in zip(*columns)]


def _sum_series(*value_lists: list[Any]) -> list[Any]:
    """Somma periodo per periodo di N serie già risolte (assunzioni, righe di
    prospetto): usata per «Investimenti» (tangibili+intangibili, pagina 7)."""
    return [None if any(v is None for v in group) else sum(group, ZERO) for group in zip(*value_lists)]


def _residual(total: list[Any], *deductions: list[Any]) -> list[Any]:
    """Residuo su un totale canonico, periodo per periodo — «Altre attività»
    (pagina 9): differenza fra righe canoniche dello stesso periodo, mai una
    massa inventata quando una delle componenti manca."""
    result = []
    for values in zip(total, *deductions):
        head, tail = values[0], values[1:]
        result.append(None if any(v is None for v in values) else head - sum(tail, ZERO))
    return result


def _assumption_values(report: FinalReportModelV2, section_key: str, field: str, count: int) -> list[Any]:
    """`AssumptionValue.values` per un campo, riallineato a `count` (il
    numero di anni di piano di questa pagina): `count` valori `None` se lo
    scenario non ha quel campo fra le proprie ipotesi (mai un
    `AttributeError` a valle — una riga del driver table che non trova
    l'ipotesi resta «n.d.», non sparisce la pagina), troncato o esteso con
    `None` se la lista non è già della stessa lunghezza — nulla nello schema
    lega `AssumptionValue.values` al numero di `forecast.years` (nessun
    `model_validator` incrociato in `final_report.py`), quindi l'allineamento
    per indice non va dato per garantito a monte."""
    section = s.assumption_section_by_key(report, section_key)
    assumption = s.assumption_value(section, field)
    if assumption is None:
        return [None] * count
    values = list(assumption.values)
    if len(values) < count:
        values = values + [None] * (count - len(values))
    return values[:count]


def _driver_row(identifier: str, label: str, values: list[Any], unit: str) -> dict[str, Any]:
    return s.row(f"driver:{identifier}", [label, *values], [None, *([unit] * len(values))])


def _ce_summary_table(report: FinalReportModelV2, statement: Any, periods: list[Any]) -> dict[str, Any]:
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for code, display_label in _CE_SUMMARY_ROWS:
        row_obj = s.statement_row(statement, code)
        values = s.values_for_periods(row_obj, statement, periods)
        rows.append(s.row(f"ce-summary:{code}", [display_label, *values],
                          [None, *(["eur"] * len(values))]))
    return s.table("ce-summary", "Conto economico · sintesi", columns, rows)


def _ce(report: FinalReportModelV2) -> dict[str, Any]:
    statement = s.statement_by_id(report, "income_statement")
    periods = s.forecast_periods(statement)  # «CE previsionale = anni di piano», m2-02d.md
    kpis = [kpi for kpi in (
        s.kpi_forecast(report, "income_statement",
                       ("ce01_ricavi_vendite", "revenue", "production_value"), "ricavi"),
        # `ebitda`/`net_profit` sono proprietà Python su `ForecastIncomeStatement`,
        # non colonne persistite: `kpi_forecast` non le trova mai su un report
        # reale (solo su una fixture sintetica che dichiari quei codici a
        # mano). `kpi_statement` legge lo stesso valore da `detailed_statements`,
        # dove `calculate_ce_result` lo ha già calcolato — v. la nota sopra
        # `kpi_statement` in shared.py. Corretto qui perché il file è lo
        # stesso: senza, «EBITDA» e «utile netto» restano silenziosamente
        # assenti dal riquadro KPI su ogni report reale (misurato su
        # AMBIENTA/575, scenario 18: solo 2 dei 4 KPI comparivano).
        s.kpi_statement(report, "income_statement", "ebitda", "EBITDA"),
        s.kpi_indicator(report, "practice.ebitda_margin", "margine EBITDA"),
        s.kpi_statement(report, "income_statement", "net_profit", "utile netto"),
    ) if kpi is not None]
    # «Evoluzione dei margini»: due indicatori reali (non una formula nuova),
    # limitati agli anni di piano. `analytical.profitability.ros` è il
    # margine operativo (EBIT/ricavi) già nel catalogo indicatori — nessun
    # calcolo qui, solo una finestra sui periodi che la pagina racconta.
    chart = s.indicator_chart(report, "ce-margini", "Evoluzione dei margini", "percent", periods,
        ["practice.ebitda_margin", "analytical.profitability.ros"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("ce-margini", "Evoluzione dei margini", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_ce_summary_table(report, statement, periods))
    return {"form": "rail+main", "id": "ce", "title": "Conto economico previsionale", "family": FAMILY,
            "subtitle": "Gli anni di piano sono confrontati sulla medesima base annuale.",
            "kpis": [] if block is not None else kpis, "items": items}


def _ipotesi(report: FinalReportModelV2) -> dict[str, Any]:
    ce_statement = s.statement_by_id(report, "income_statement")
    periods = s.forecast_periods(ce_statement)
    count = len(periods)
    cf_statement = s.statement_by_id(report, "cashflow")
    cf_periods = s.forecast_periods(cf_statement)  # stessi anni di `periods`, per costruzione dei source

    growth = _assumption_values(report, "fatturato", "revenue_growth_pct", count)
    opex_revenue = s.indicator_values_for_periods(report, "practice.opex_revenue", periods)
    ammortamenti = s.values_for_periods(s.statement_row(ce_statement, "ce09_ammortamenti"), ce_statement, periods)
    tangible = _assumption_values(report, "patrimoniale-piano", "tangible_investments", count)
    intangible = _assumption_values(report, "patrimoniale-piano", "intangible_investments", count)
    investments = _sum_series(tangible, intangible)
    rimborso_debito = s.values_for_periods(
        s.statement_row(cf_statement, "financing.third_party_funds.decreases"), cf_statement, cf_periods)
    effective_tax_rate = s.indicator_values_for_periods(report, "practice.effective_tax_rate", periods)

    investments_total = None if any(v is None for v in investments) else sum(investments, ZERO)

    kpis = [kpi for kpi in (
        s.kpi_horizon(report),
        s.kpi_series("crescita ricavi", growth, "percent") if any(v is not None for v in growth) else None,
        s.kpi_indicator_periods(report, "practice.ebitda_margin", "EBITDA margin obiettivo", periods),
        s.kpi("investimenti cumulati", investments_total, "eur") if investments_total is not None else None,
    ) if kpi is not None]

    driver_columns = ["Voce", *[s.period_label(period) for period in periods]]
    driver_rows = [
        _driver_row("revenue_growth", "Ricavi · crescita annua", growth, "percent"),
        _driver_row("opex_revenue", "Costi operativi / ricavi", opex_revenue, "percent"),
        _driver_row("ammortamenti", "Ammortamenti", ammortamenti, "eur"),
        _driver_row("investimenti", "Investimenti", investments, "eur"),
        _driver_row("rimborso_debito", "Rimborso debito", rimborso_debito, "eur"),
        _driver_row("effective_tax_rate", "Imposte / risultato ante imposte", effective_tax_rate, "percent"),
    ]
    driver_table = s.table("driver", "Driver del piano", driver_columns, driver_rows)

    aree_columns = ["Area", "Ipotesi da documentare"]
    aree_rows = [
        s.row(f"aree:{section.key}", [section.title, _AREA_DESCRIPTIONS[section.key]], [None, None])
        for section in report.assumption_sections
    ]
    aree_table = s.table("aree-piano", "Le sette aree del piano", aree_columns, aree_rows)

    return {"form": "rail+main", "id": "ipotesi", "title": "Ipotesi del piano", "family": FAMILY,
            "subtitle": "Le ipotesi sono presentate per anno e per area, con origine e "
                        "collegamento ai risultati attesi.",
            "kpis": kpis, "items": [driver_table, aree_table]}


def _sp_summary_table(report: FinalReportModelV2, statement: Any, periods: list[Any]) -> dict[str, Any]:
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    fixed_assets = s.values_for_periods(s.statement_row(statement, "fixed_assets"), statement, periods)
    rimanenze = s.values_for_periods(s.statement_row(statement, "sp05_rimanenze"), statement, periods)
    crediti_commerciali = _sum_two_rows(statement, periods, _SP_COMMERCIAL_RECEIVABLE_CODES)
    cassa = s.values_for_periods(s.statement_row(statement, "sp09_disponibilita_liquide"), statement, periods)
    totale_attivo = s.values_for_periods(s.statement_row(statement, "total_assets"), statement, periods)
    altre_attivita = _residual(totale_attivo, fixed_assets, rimanenze, crediti_commerciali, cassa)
    patrimonio_netto = s.values_for_periods(s.statement_row(statement, _SP_EQUITY_CODE), statement, periods)
    debiti_finanziari = s.structure_values_for_periods(report, "composition_sources", "financial_debt", periods)
    debiti_commerciali = s.values_for_periods(s.statement_row(statement, _SP_TRADE_PAYABLES_CODE), statement, periods)
    altre_passivita = s.structure_values_for_periods(report, "composition_sources", "other_liabilities", periods)
    totale_passivo = s.values_for_periods(s.statement_row(statement, _SP_TOTAL_LIABILITIES_CODE), statement, periods)

    rows_spec: tuple[tuple[str, str, list[Any]], ...] = (
        ("fixed_assets", "Immobilizzazioni nette", fixed_assets),
        ("sp05_rimanenze", "Rimanenze", rimanenze),
        ("crediti_commerciali", "Crediti commerciali", crediti_commerciali),
        ("sp09_disponibilita_liquide", "Disponibilità liquide", cassa),
        ("altre_attivita", "Altre attività", altre_attivita),
        ("total_assets", "Totale attivo", totale_attivo),
        ("patrimonio_netto", "Patrimonio netto", patrimonio_netto),
        ("debiti_finanziari", "Debiti finanziari", debiti_finanziari),
        ("debiti_commerciali", "Debiti commerciali", debiti_commerciali),
        ("altre_passivita", "Altre passività", altre_passivita),
        ("totale_passivo", "Totale passivo e netto", totale_passivo),
    )
    rows = [s.row(f"sp-summary:{code}", [label, *values], [None, *(["eur"] * len(values))])
            for code, label, values in rows_spec]
    return s.table("sp-summary", "Stato patrimoniale · sintesi", columns, rows)


def _sp(report: FinalReportModelV2) -> dict[str, Any]:
    statement = s.statement_by_id(report, "balance_sheet")
    periods = s.forecast_periods(statement)  # «SP previsionale = anni di piano», come «ce»
    kpis = [kpi for kpi in (
        s.kpi_statement(report, "balance_sheet", "total_assets", "totale attivo"),
        s.kpi_statement(report, "balance_sheet", _SP_EQUITY_CODE, "patrimonio netto"),
        s.kpi_statement(report, "balance_sheet", "fixed_assets", "immobilizzazioni nette"),
        s.kpi_structure(report, "composition_sources", "financial_debt", "debiti finanziari"),
    ) if kpi is not None]
    equity_values = s.values_for_periods(s.statement_row(statement, _SP_EQUITY_CODE), statement, periods)
    financial_debt_values = s.structure_values_for_periods(report, "composition_sources", "financial_debt", periods)
    chart = s.chart_from_series("sp-patrimonio-debito", "Patrimonio e indebitamento", "eur", periods,
        [("Patrimonio netto", equity_values), ("Debiti finanziari", financial_debt_values)])
    items: list[dict[str, Any]] = []
    block = s.chart_block("sp-patrimonio-debito", "Patrimonio e indebitamento", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_sp_summary_table(report, statement, periods))
    return {"form": "rail+main", "id": "sp", "title": "Stato patrimoniale previsionale", "family": FAMILY,
            "subtitle": None,
            "kpis": [] if block is not None else kpis, "items": items}


def _cashflow_summary_table(statement: Any, periods: list[Any]) -> dict[str, Any]:
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for code, display_label in _CASHFLOW_SUMMARY_ROWS:
        row_obj = s.statement_row(statement, code)
        values = s.values_for_periods(row_obj, statement, periods)
        rows.append(s.row(f"cf-summary:{code}", [display_label, *values],
                          [None, *(["eur"] * len(values))]))
    return s.table("cf-summary", "Riconciliazione della liquidità", columns, rows)


def _flussi(report: FinalReportModelV2) -> dict[str, Any]:
    statement = s.statement_by_id(report, "cashflow")
    periods = s.forecast_periods(statement)  # «Flussi = anni di piano», come «ce»/«sp»

    operating = s.values_for_periods(
        s.statement_row(statement, "operating.total_operating_cashflow"), statement, periods)
    investing = s.values_for_periods(
        s.statement_row(statement, "investing.total_investing_cashflow"), statement, periods)
    third_party_decreases = s.values_for_periods(
        s.statement_row(statement, "financing.third_party_funds.decreases"), statement, periods)
    own_funds_decreases = s.values_for_periods(
        s.statement_row(statement, "financing.own_funds.decreases"), statement, periods)
    cash_beginning = s.values_for_periods(
        s.statement_row(statement, "cash_reconciliation.cash_beginning"), statement, periods)
    cash_ending = s.values_for_periods(
        s.statement_row(statement, "cash_reconciliation.cash_ending"), statement, periods)

    operating_sum = None if any(v is None for v in operating) else sum(operating, ZERO)
    investing_sum = None if any(v is None for v in investing) else sum(investing, ZERO)
    # «Rimborsi»: le due righe di dettaglio sono un magnitudine di decremento
    # (positiva), non il flusso netto già segnato come `total_financing_cashflow`
    # — il segno si inverte qui per mostrarli come un'uscita, mai una nuova
    # grandezza calcolata (mappatura v4 pagina 10, nota «segno da verificare
    # in resa»; confrontato con `investing.total_investing_cashflow`, che è
    # già firmato correttamente in uscita).
    third_party_sum = None if any(v is None for v in third_party_decreases) else sum(third_party_decreases, ZERO)
    own_funds_sum = None if any(v is None for v in own_funds_decreases) else sum(own_funds_decreases, ZERO)
    repayments_sum = None if third_party_sum is None else -(third_party_sum + (own_funds_sum or ZERO))
    cash_change = (None if not cash_beginning or not cash_ending
                  or cash_beginning[0] is None or cash_ending[-1] is None
                  else cash_ending[-1] - cash_beginning[0])

    kpis = [kpi for kpi in (
        s.kpi("flussi operativi", operating_sum, "eur") if operating_sum is not None else None,
        s.kpi("investimenti", investing_sum, "eur") if investing_sum is not None else None,
        s.kpi("rimborsi", repayments_sum, "eur") if repayments_sum is not None else None,
        s.kpi("variazione di cassa", cash_change, "eur") if cash_change is not None else None,
    ) if kpi is not None]

    chart = s.statement_chart(report, "cashflow", "flussi-composizione", "Composizione dei flussi di cassa",
        "eur", periods, [("operating.total_operating_cashflow", "Operativo"),
                         ("investing.total_investing_cashflow", "Investimenti"),
                         ("financing.total_financing_cashflow", "Finanziario")])
    items: list[dict[str, Any]] = []
    block = s.chart_block("flussi-composizione", "Composizione dei flussi di cassa", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_cashflow_summary_table(statement, periods))
    return {"form": "rail+main", "id": "flussi", "title": "Flussi di cassa e sostenibilità", "family": FAMILY,
            "subtitle": "Somme e riconciliazione sull'intero orizzonte di piano.",
            "kpis": [] if block is not None else kpis, "items": items}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    return [_ipotesi(report), _ce(report), _sp(report), _flussi(report)]
