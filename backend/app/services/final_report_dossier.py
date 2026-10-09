"""Presentation-rich projection of authorized canonical report sources."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from app.schemas.final_report import Diagnostic, FinalReportModel
from app.schemas.final_report_v2 import (
    DetailedStatement, DetailedStatementRow, DocumentIdentity, DossierChartSeries,
    EditorialReadiness, FinalReportModelV2, IndicatorDefinition, ReportSeries,
    ReportSeriesGroup, StatementPeriod,
)
from calculations.ce_result import calculate_ce_result
from calculations.projection_common import punto_di_pareggio
from calculations.report_indicators import (
    balance_aggregates, financial_debt_total, indicator_results, unavailable_details,
)

CATALOG = json.loads((Path(__file__).resolve().parents[3] / 'contracts/final_report_dossier_catalog.json').read_text(encoding='utf-8'))
ZERO = Decimal('0')
HUNDRED = Decimal('100')
# La quota fissa di default del blocco pareggio (F5, decisione del proprietario 2026-09-26): è
# quella che vale sulla colonna base/storica quando lo scenario non ha ancora ipotesi di piano.
DEFAULT_FIXED_SHARE = Decimal('0.40')
EQUITY_DEPS = ('sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita')
LIABILITIES_DEPS = EQUITY_DEPS + ('sp16_debiti_breve', 'sp17_debiti_lungo', 'sp14_fondi_rischi', 'sp15_tfr', 'sp18_ratei_risconti_passivi')
UNITS = {'euro': 'eur', 'pct': 'percent', 'ratio': 'ratio', 'days': 'days'}


@dataclass(frozen=True)
class DossierSource:
    period: StatementPeriod
    balance_sheet: dict[str, Decimal] | None
    income_statement: dict[str, Decimal] | None
    calculations: dict | None = None
    cashflow: dict | None = None
    # Quota fissa per categoria (materie, servizi), in punti percentuali — F5 (decisione del
    # proprietario, 2026-09-26): le percentuali del PRIMO anno di piano
    # (`final_report_service._fixed_split`), mai quelle dell'anno stesso di questa colonna.
    # `None` senza alcuna ipotesi di piano salvata (il report dichiara il 60/40 di default). Resta
    # letta solo dalle basi diverse da 'forecast' (`historical`/`closing`): un anno di piano vero
    # usa `pareggio_motore`, mai più questa quota.
    fixed_split: tuple[Decimal, Decimal] | None = None
    # A02 (lotto 2 fix rilievi, 2026-09-26): `ForecastYear.engine_meta["pareggio"]`
    # dell'anno di piano, stringhe al centesimo o `None` per singola chiave (dizionario
    # con le 7 chiavi di `calculations.forecast_engine.engine_meta`, o `None` quando
    # l'anno non ha affatto un `engine_meta` persistito). Letto solo per basis=='forecast'.
    pareggio_motore: dict[str, str | None] | None = None
    # F2 (decisione del proprietario, 2026-09-26): `ForecastYear.engine_meta["rimborsi_piano"]`
    # dell'anno di piano — stringa al centesimo, le sole rate di uno scadenziamento vero (mai
    # scoperto/fidi/sweep) — per il DSCR. Letto solo per basis=='forecast'; `None` sia quando
    # l'anno non ha affatto un `engine_meta` persistito, sia quando il motore che ha girato è più
    # vecchio di questa correzione (nessuna chiave `rimborsi_piano`): in entrambi i casi il DSCR
    # di quell'anno esce indefinito con la stessa ragione dichiarata (`_dscr_capital_quota`).
    rimborsi_piano: str | None = None


def pareggio_motore_from(engine_meta: dict | None) -> dict | None:
    """`engine_meta['pareggio']` di un anno di piano, differenziando le due cause di assenza
    (minore, revisione finale lotto 2, 2026-09-26): `None` solo quando l'anno non ha affatto un
    `engine_meta` persistito (nessun motore ha mai girato per quell'anno — reason a valle
    `engine_meta_missing`); un dizionario vuoto quando `engine_meta` c'è ma non porta la chiave
    `pareggio` (un motore più vecchio del blocco pareggio) — reason a valle `pareggio_non_definito`,
    perché il motore che ha girato per quell'anno non ha mai calcolato la scomposizione. Prima di
    questa distinzione le due cause collassavano sullo stesso `None` e sulla stessa reason
    `engine_meta_missing`, anche quando un `engine_meta` esisteva davvero.
    """
    if engine_meta is None:
        return None
    return engine_meta.get('pareggio') or {}


def _path(data, key):
    for part in key.split('.'):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def build_detailed_statements(sources: list[DossierSource]) -> list[DetailedStatement]:
    statements = []
    titles = {'income_statement': 'Conto economico completo', 'balance_sheet': 'Stato patrimoniale completo', 'cashflow': 'Rendiconto finanziario completo — metodo indiretto'}
    for key, title in titles.items():
        rows = []
        for definition in CATALOG[key]:
            values, reasons = [], []
            header = definition['kind'] in ('section', 'group')
            applicable = header or bool(definition['field'] or definition['dependencies'])
            for source in sources:
                value, reason = None, None
                raw = getattr(source, key)
                if header:
                    reason = 'presentation_header'
                elif not applicable:
                    reason = 'model_field_unavailable'
                elif raw is None:
                    reason = 'source_period_unavailable'
                elif key == 'cashflow':
                    value = _path(raw, definition['field'])
                else:
                    enriched = dict(raw)
                    missing_details = unavailable_details(raw)
                    if key == 'income_statement':
                        ce = calculate_ce_result(raw)
                        enriched.update({field: getattr(ce, field) for field in ('production_value', 'production_cost', 'ebitda', 'ebit', 'financial_result', 'extraordinary_result', 'profit_before_tax', 'net_profit')})
                        # The D-section subtotal follows canonical detail-first netting,
                        # even when a legacy aggregate is also stored.
                        enriched['ce17_rettifiche_attivita_fin'] = ce.value_adjustments
                    else:
                        enriched.update(balance_aggregates(raw))
                    if definition['field'] in missing_details or any(k in missing_details for k in definition['dependencies']):
                        reason = 'detail_not_declared'
                    elif definition['difference']:
                        value = enriched['total_assets'] - enriched['total_liabilities']
                    elif definition['dependencies']:
                        dependencies = [enriched.get(k) for k in definition['dependencies']]
                        if all(v is not None for v in dependencies):
                            value = sum(dependencies, ZERO)
                    else:
                        value = enriched.get(definition['field'])
                if value is None and reason is None:
                    reason = 'source_field_unavailable'
                values.append(value)
                reasons.append(reason)
            rows.append(DetailedStatementRow(
                **{k: definition[k] for k in ('id', 'code', 'label', 'parent_id', 'level', 'kind')},
                applicable=applicable, values=values, unavailable_reasons=reasons,
                source='DetailedCashFlowCalculator' if key == 'cashflow' else 'persisted_statement; calculate_ce_result' if key == 'income_statement' else 'persisted_statement; balance_aggregates',
            ))
        statements.append(DetailedStatement(id=key, title=title, catalog_version=CATALOG['catalog_version'], periods=[s.period for s in sources], rows=rows))
    return statements


def build_indicator_catalog(sources: list[DossierSource]) -> list[IndicatorDefinition]:
    # F2 (decisione del proprietario, 2026-09-26): il DSCR di un anno di piano legge
    # `rimborsi_piano` invece del rendiconto — `is_forecast_year` lo dice a `indicator_results`,
    # `s.rimborsi_piano` resta `None` (dichiarato con la sua ragione) su ogni altra base.
    results = [
        indicator_results(
            s.balance_sheet, s.income_statement, (s.calculations or {}).get('ratios'), s.cashflow,
            is_forecast_year=s.period.basis == 'forecast',
            rimborsi_piano=None if s.rimborsi_piano is None else Decimal(s.rimborsi_piano),
        )
        for s in sources
    ]
    definitions = [('practice.' + row['key'], row, 'pratica') for row in CATALOG['practice_indicators']]
    definitions += [('practice.' + key, {'label': label, 'format': 'pct'}, 'incidenze') for key, label in (('materials_revenue', 'Materie prime / Ricavi'), ('services_revenue', 'Servizi / Ricavi'), ('personnel_revenue', 'Personale / Ricavi'))]
    # M2-02E: quattro indicatori canonici mancanti (pagine 7, 8, 12 del dossier v4). Come
    # `materials_revenue`/`services_revenue`/`personnel_revenue` sopra, non stanno nel catalogo
    # TS-generato (`contracts/final_report_dossier_catalog.json`, esportato da
    # `frontend/lib/pratica-indicators.ts` per la scheda Indicatori della pratica, un perimetro
    # diverso): entrano qui perché sono voci del solo modello v2 del report finale.
    definitions += [
        ('practice.opex_revenue', {'label': 'Costi Operativi / Ricavi', 'format': 'pct'}, 'incidenze'),
        ('practice.effective_tax_rate', {'label': 'Aliquota Effettiva', 'format': 'pct'}, 'fiscalità'),
        ('practice.ebit_margin', {'label': 'Margine EBIT', 'format': 'pct'}, 'redditività'),
        ('practice.quick_ratio', {'label': 'Liquidità Immediata', 'format': 'ratio'}, 'liquidità'),
    ]
    definitions += [('analytical.' + row['key'], row, row['category']) for row in CATALOG['analytical_indicators']]
    indicators = []
    for identifier, row, family in definitions:
        unit = UNITS[row['format']]
        prototype = next((r[identifier] for r in results if identifier in r), None)
        values, reasons = [], []
        for result in results:
            entry = result.get(identifier)
            value = entry.value if entry else None
            reason = entry.reason if entry else 'source_period_unavailable'
            if identifier.startswith('analytical.') and unit == 'percent' and value is not None:
                value *= Decimal('100')
            values.append(value)
            reasons.append(reason)
        indicators.append(IndicatorDefinition(id=identifier, label=row['label'], family=family, unit=unit,
            methodology=prototype.methodology if prototype else 'Fonte di calcolo non disponibile; nessuna formula applicata dal renderer.',
            convention=prototype.convention if prototype else 'Periodo e unità dichiarati; valori indisponibili distinti dallo zero.',
            periods=[s.period for s in sources], values=values, unavailable_reasons=reasons,
            source='calculations.report_indicators' if identifier.startswith('practice.') else 'FinancialRatiosCalculator',
        ))
    return indicators


CENT = Decimal('0.01')


def _q2(value: Decimal) -> Decimal:
    """Al centesimo (F5, decisione del proprietario 2026-09-26): la colonna base/storica del
    pareggio arrotonda come il motore (`_q2` in `calculations/forecast_engine.py`), cosi' resta
    confrontabile al centesimo con gli anni di piano — che leggono `engine_meta['pareggio']` gia'
    quantizzato."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _share(value: Decimal | None, total: Decimal | None) -> tuple[Decimal | None, str | None]:
    """Quota percentuale sull'aggregato, con il proprio motivo quando manca."""
    if value is None:
        return None, 'source_field_unavailable'
    if total is None:
        return None, 'source_period_unavailable'
    if total == ZERO:
        return None, 'zero_denominator'
    if total < ZERO:
        return None, 'non_positive_denominator'
    return value / total * HUNDRED, None


def _deps_sum(data: dict[str, Decimal], keys: tuple[str, ...]) -> Decimal | None:
    """Somma gli aggregati come fa la riga del prospetto: campo assente ⇒ None."""
    return None if any(key not in data for key in keys) else sum((data[key] for key in keys), ZERO)


def _pareggio_field(motore: dict[str, str | None], field: str) -> Decimal | None:
    """Una chiave di `engine_meta['pareggio']` (stringa al centesimo o `None`) come `Decimal`."""
    raw = motore.get(field)
    return None if raw is None else Decimal(raw)


def _column(series: dict[str, tuple[list, list]], key: str, value: Decimal | None, reason: str | None) -> None:
    series[key][0].append(value)
    series[key][1].append(value is None and (reason or 'source_field_unavailable') or None)


def _columns(keys: tuple[str, ...]) -> dict[str, tuple[list, list]]:
    return {key: ([], []) for key in keys}


def _finish(series: dict[str, tuple[list, list]], labels: dict[str, str], unit: dict[str, str]) -> list[ReportSeries]:
    return [ReportSeries(id=key, label=labels[key], unit=unit[key], values=values, unavailable_reasons=reasons)
            for key, (values, reasons) in series.items()]


def build_structure_series(sources: list[DossierSource], indicators: list[IndicatorDefinition]) -> list[ReportSeriesGroup]:
    """Le serie delle pagine «Composizioni» e «Pareggio», dagli stessi numeri dei prospetti.

    Nulla qua ricalcola una formula: importi e quote vengono dagli aggregati
    canonici (`balance_aggregates`, `financial_debt_total`) e il pareggio dalla stessa regola del
    motore budget (`calculations.projection_common.punto_di_pareggio`, F5, decisione del
    proprietario 2026-09-26), sia sulla colonna base/storica sia sugli anni di piano. Un valore
    che non c'è è null con il proprio motivo, mai zero.
    """
    periods = [source.period for source in sources]

    uses = _columns(('fixed_assets', 'fixed_assets_share', 'current_other', 'current_other_share', 'cash', 'cash_share'))
    for source in sources:
        bs = source.balance_sheet
        if bs is None:
            for key in uses:
                _column(uses, key, None, 'source_period_unavailable')
            continue
        aggregates = balance_aggregates(bs)
        fixed, total, cash = aggregates['fixed_assets'], aggregates['total_assets'], bs.get('sp09_disponibilita_liquide')
        other = None if (cash is None or fixed is None) else total - fixed - cash
        for key, value in (('fixed_assets', fixed), ('current_other', other), ('cash', cash)):
            _column(uses, key, value, None if value is not None else 'source_field_unavailable')
            share, share_reason = _share(value, total)
            _column(uses, key + '_share', share, share_reason)

    sources_group = _columns(('equity', 'equity_share', 'financial_debt', 'financial_debt_share', 'other_liabilities', 'other_liabilities_share'))
    for source in sources:
        bs = source.balance_sheet
        if bs is None:
            for key in sources_group:
                _column(sources_group, key, None, 'source_period_unavailable')
            continue
        equity = _deps_sum(bs, EQUITY_DEPS)
        financial = financial_debt_total(lambda field: bs.get(field, ZERO))
        liabilities = _deps_sum(bs, LIABILITIES_DEPS)
        other = None if (equity is None or liabilities is None) else liabilities - equity - financial
        for key, value in (('equity', equity), ('financial_debt', financial), ('other_liabilities', other)):
            _column(sources_group, key, value, None if value is not None else 'source_field_unavailable')
            share, share_reason = _share(value, liabilities)
            _column(sources_group, key + '_share', share, share_reason)

    by_indicator = {indicator.id: indicator for indicator in indicators}
    incidence_specs = (('materials', 'Materie prime / Ricavi', 'practice.materials_revenue'),
                       ('services', 'Servizi / Ricavi', 'practice.services_revenue'),
                       ('personnel', 'Personale / Ricavi', 'practice.personnel_revenue'),
                       ('financial_charges', 'Oneri finanziari / Ricavi', 'practice.of_revenue'))
    incidence = [ReportSeries(id=key, label=label, unit='percent',
                              values=list(by_indicator[identifier].values),
                              unavailable_reasons=list(by_indicator[identifier].unavailable_reasons))
                 for key, label, identifier in incidence_specs]

    pareggio = _columns(('fixed_costs', 'variable_costs', 'contribution_margin', 'break_even_revenue', 'safety_margin_pct'))
    for source in sources:
        bs, inc = source.balance_sheet, source.income_statement
        if bs is None or inc is None:
            for key in pareggio:
                _column(pareggio, key, None, 'source_period_unavailable')
            continue
        if source.period.basis == 'forecast':
            # A02 (lotto 2 fix rilievi, 2026-09-26): un anno di piano non ricalcola
            # più fissi/variabili con una quota 60/40 (o quella delle ipotesi): usa
            # integralmente `engine_meta['pareggio']` del motore, dichiarato per
            # ogni anno in `calculations/forecast_engine.py`. `None` per l'intero
            # anno (`engine_meta_missing`) quando non c'è affatto un `pareggio`
            # persistito; `None` (`pareggio_non_definito`) quando il motore l'ha
            # dichiarato lui stesso non definito (ce05/ce06 sotto override).
            motore = source.pareggio_motore
            if motore is None:
                for key in pareggio:
                    _column(pareggio, key, None, 'engine_meta_missing')
                continue

            variabili = _pareggio_field(motore, 'costi_variabili')
            fissi_operativi = _pareggio_field(motore, 'costi_fissi_operativi')
            if variabili is None or fissi_operativi is None:
                for key in pareggio:
                    _column(pareggio, key, None, 'pareggio_non_definito')
                continue
            _column(pareggio, 'variable_costs', variabili, None)
            _column(pareggio, 'fixed_costs', fissi_operativi, None)
            revenue = inc.get('ce01_ricavi_vendite')
            # Stessa definizione della colonna base/storica: MdC = Ricavi − Costi
            # variabili (qui i variabili sono quelli dichiarati dal motore).
            margin = None if revenue is None else revenue - variabili
            _column(pareggio, 'contribution_margin', margin, None if margin is not None else 'source_field_unavailable')
            bep = _pareggio_field(motore, 'fatturato_pareggio')
            sicurezza_pct = _pareggio_field(motore, 'margine_sicurezza_pct')
            _column(pareggio, 'break_even_revenue', bep, None if bep is not None else 'pareggio_non_definito')
            _column(pareggio, 'safety_margin_pct', sicurezza_pct, None if sicurezza_pct is not None else 'pareggio_non_definito')
            continue
        # F5 (decisione del proprietario, 2026-09-26): la colonna base/storica usa la STESSA
        # regola del motore (`calculations.projection_common.punto_di_pareggio`), mai più
        # `FinancialRatiosCalculator.calculate_break_even_analysis` — quella ignorava
        # ce02/ce03/ce03a/ce04/ce10/ce11/ce11b e rendeva le due colonne incomparabili: a crescita
        # zero il piano ripartiva costi diversi da quelli della base, e il testo raccontava un
        # finto risanamento ("negativo nel <base> … positivo dal <primo anno di piano>"). Le
        # quote fisso/variabile di ce05/ce06 vengono da `source.fixed_split` — le percentuali del
        # PRIMO anno di piano (`final_report_service._fixed_split`) — cosi' base e piano
        # applicano la stessa aritmetica alla stessa ripartizione; senza ipotesi di piano restano
        # il 60/40 di default (`DEFAULT_FIXED_SHARE`), dichiarato, su entrambe le voci.
        required = ('ce01_ricavi_vendite', 'ce04_altri_ricavi', 'ce05_materie_prime', 'ce06_servizi',
                    'ce07_godimento_beni', 'ce08_costi_personale', 'ce12_oneri_diversi')
        valori = {campo: inc.get(campo) for campo in required}
        if any(v is None for v in valori.values()):
            for key in pareggio:
                _column(pareggio, key, None, 'source_field_unavailable')
            continue
        if source.fixed_split is None:
            materials_pct = services_pct = DEFAULT_FIXED_SHARE * HUNDRED
        else:
            materials_pct, services_pct = source.fixed_split
        # R07 (#63, 2026-10-09): come nel motore, la quota fisso/variabile riguarda il CONSUMO di materie
        # (ce05 + ce10), e ce10 non si somma una seconda volta ai costi fissi.
        ce10_base = inc.get('ce10_var_rimanenze_mat_prime') or ZERO
        ce05, ce06 = valori['ce05_materie_prime'] + ce10_base, valori['ce06_servizi']
        ce05_fixed = ce05 * materials_pct / HUNDRED
        ce06_fixed = ce06 * services_pct / HUNDRED
        esito = punto_di_pareggio(
            ce01=valori['ce01_ricavi_vendite'], ce02=inc.get('ce02_variazioni_rimanenze'),
            ce03=inc.get('ce03_lavori_interni'), ce03a=inc.get('ce03a_incrementi_immobilizzazioni'),
            ce04=valori['ce04_altri_ricavi'],
            ce05_fixed=ce05_fixed, ce05_variable=ce05 - ce05_fixed,
            ce06_fixed=ce06_fixed, ce06_variable=ce06 - ce06_fixed,
            ce07=valori['ce07_godimento_beni'], ce08=valori['ce08_costi_personale'],
            ce10=ZERO, ce11=inc.get('ce11_accantonamenti'),
            ce11b=inc.get('ce11b_altri_accantonamenti'), ce12=valori['ce12_oneri_diversi'],
        )
        _column(pareggio, 'fixed_costs', _q2(esito['costi_fissi_operativi']), None)
        _column(pareggio, 'variable_costs', _q2(esito['costi_variabili']), None)
        _column(pareggio, 'contribution_margin', _q2(valori['ce01_ricavi_vendite'] - esito['costi_variabili']), None)
        if esito['fatturato_pareggio'] is not None:
            _column(pareggio, 'break_even_revenue', _q2(esito['fatturato_pareggio']), None)
            _column(pareggio, 'safety_margin_pct', _q2(esito['margine_sicurezza_pct']), None)
        else:
            # Stessa guardia del blocco `pareggio` del motore budget: il ricavo di pareggio
            # esiste solo con ricavi e margine di contribuzione positivi.
            reason = 'zero_denominator' if valori['ce01_ricavi_vendite'] == ZERO else 'non_positive_denominator'
            for key in ('break_even_revenue', 'safety_margin_pct'):
                _column(pareggio, key, None, reason)

    labels = {
        'fixed_assets': 'Immobilizzazioni nette', 'fixed_assets_share': 'Immobilizzazioni nette · quota %',
        'current_other': 'Circolante e altro', 'current_other_share': 'Circolante e altro · quota %',
        'cash': 'Disponibilità liquide', 'cash_share': 'Disponibilità liquide · quota %',
        'equity': 'Patrimonio netto', 'equity_share': 'Patrimonio netto · quota %',
        'financial_debt': 'Debiti finanziari', 'financial_debt_share': 'Debiti finanziari · quota %',
        'other_liabilities': 'Altre passività', 'other_liabilities_share': 'Altre passività · quota %',
        'fixed_costs': 'Costi fissi', 'variable_costs': 'Costi variabili',
        'contribution_margin': 'Margine di contribuzione', 'break_even_revenue': 'Ricavi di pareggio',
        'safety_margin_pct': 'Margine di sicurezza %',
    }
    eur = {key: 'eur' for key in labels}
    units = {**eur, **{key: 'percent' for key in labels if key.endswith('_share') or key == 'safety_margin_pct'}}
    return [
        ReportSeriesGroup(id='composition_uses', title='Composizione degli impieghi', periods=periods,
                          series=_finish(uses, labels, units), source='persisted_statement; balance_aggregates',
                          methodology="Immobilizzazioni nette e disponibilità liquide dagli aggregati di bilancio; il circolante e altro è il residuo sul totale dell'attivo. Quote percentuali sullo stesso totale."),
        ReportSeriesGroup(id='composition_sources', title='Composizione delle fonti', periods=periods,
                          series=_finish(sources_group, labels, units), source='persisted_statement; balance_aggregates; financial_debt_total',
                          # Minore (revisione finale lotto 2, 2026-09-26): testo allineato a C03/C04
                          # — `financial_debt_total` è una somma incondizionata, mai un ramo "banche
                          # positive altrimenti fallback" che tagliava fuori gli altri finanziatori.
                          methodology='Patrimonio netto dagli aggregati; debiti finanziari con la convenzione della PFN (somma'
                                      ' incondizionata di banche, altri finanziatori e obbligazioni, breve e lungo termine);'
                                      ' altre passività come residuo sul totale del passivo.'),
        ReportSeriesGroup(id='cost_incidence', title='Incidenza dei costi sui ricavi', periods=periods,
                          series=incidence, source='calculations.report_indicators',
                          methodology="Valori del catalogo indicatori (practice.*): rapporto sull'articolo CE 1 × 100, con i flussi del periodo senza annualizzazione."),
        ReportSeriesGroup(id='break_even', title='Pareggio e margine di sicurezza', periods=periods,
                          series=_finish(pareggio, labels, units),
                          source='calculations.projection_common.punto_di_pareggio (anni di piano e colonna base/storica)',
                          methodology='Gli anni di piano riportano `engine_meta[\'pareggio\']` del motore (A02, lotto 2 fix'
                                      ' rilievi 2026-09-26): costi variabili e fissi operativi dichiarati dal motore. La'
                                      ' colonna base/storica applica la STESSA regola (`punto_di_pareggio`, F5, decisione'
                                      ' del proprietario 2026-09-26) al CE di base, con le quote fisso/variabile di'
                                      ' ce05/ce06 del primo anno di piano — così le due colonne sono confrontabili; senza'
                                      ' ipotesi di piano resta il 60/40 di default, dichiarato. Ricavi di pareggio e'
                                      ' margine di sicurezza assenti quando il motore non li dichiara (piano) o quando'
                                      ' ricavi e margine di contribuzione non sono positivi (in entrambe le colonne).'),
    ]


DOSSIER_CHARTS = (
    ('structural_balance', 'Equilibrio finanziario e strutturale', ('practice.ccn', 'practice.mt', 'practice.ms')),
    ('practice_liquidity', 'Liquidità corrente della pratica', ('practice.current_ratio',)),
    ('practice_profitability', 'Redditività operativa della pratica', ('practice.roi', 'practice.roe', 'practice.ros')),
    ('practice_asset_coverage', 'Autonomia e copertura immobilizzazioni', ('practice.indipendenza', 'practice.copertura_immob')),
    ('practice_net_debt', 'Posizione finanziaria netta della pratica', ('practice.pfn',)),
    ('practice_net_debt_ebitda', 'PFN / EBITDA della pratica', ('practice.pfn_ebitda',)),
    ('practice_dscr', 'Copertura degli oneri finanziari — DSCR', ('practice.dscr',)),
    ('economic_incidence', 'Incidenze economiche sui ricavi', ('practice.ebitda_margin', 'practice.materials_revenue', 'practice.services_revenue')),
    ('financial_charges', 'Incidenza degli oneri finanziari', ('practice.of_revenue', 'practice.of_mol')),
    ('analytical_liquidity', 'Liquidità — convenzione analitica', ('analytical.liquidity.current_ratio', 'analytical.liquidity.quick_ratio', 'analytical.liquidity.acid_test')),
)


#: Le serie che il contratto v4 chiede alle pagine executive (M2-02G fase 2,
#: traccia B): pag. 8 «Evoluzione dei margini» (EBITDA + EBIT, chiusura inclusa),
#: pag. 12 «Liquidità corrente e immediata» (current + quick ratio), pag. 14
#: «PFN / EBITDA» in volte, pag. 17 «Margine di sicurezza». L'asse non sono i
#: soli anni di piano: è la chiusura — o, in mancanza, l'ultimo storico — più gli
#: anni di piano, la stessa selezione che il catalogo applica con
#: `select_periods` (`dossier_catalog/shared.py`), dichiarata qui come
#: `period_ids` perché l'anno da solo non distingue la chiusura dall'osservato.
#: `(indicatori…, structure_refs…, metodologia)`: nessuna formula nuova, solo
#: colonne degli indicatori/celle strutturali già nel modello.
DOSSIER_WINDOW_CHARTS = (
    ('practice_margins_full', 'Evoluzione dei margini',
     ('practice.ebitda_margin', 'practice.ebit_margin'), (),
     "EBITDA margin e EBIT margin (EBIT / ricavi × 100) dal catalogo indicatori, "
     "sulla chiusura (o sull'ultimo storico) e sugli anni di piano: nessun punto "
     "è ricalcolato dal renderer."),
    ('practice_liquidity_ratios', 'Liquidità corrente e immediata',
     ('practice.current_ratio', 'practice.quick_ratio'), (),
     "Current ratio e quick ratio in convenzione pratica (attivo corrente della "
     "pratica, rispettivamente al lordo e al netto delle rimanenze, su debiti "
     "entro 12 mesi), stessi periodi del grafico dei margini strutturali."),
    ('practice_pfn_ebitda_trend', 'PFN / EBITDA',
     ('practice.pfn_ebitda',), (),
     "Rapporto PFN pratica / EBITDA del periodo, in volte: EBITDA nulla o "
     "negativa il periodo esce null con il proprio motivo (rapporto non "
     "significativo), mai un numero di ripiego."),
    ('practice_safety_margin_trend', 'Margine di sicurezza',
     (), ('break_even:safety_margin_pct',),
     "La serie `safety_margin_pct` del gruppo `break_even` di `structure_series`, "
     "esposta come serie di grafico senza ricalcolo: stessi valori, stesse "
     "colonne, stessi motivi."),
)

_WINDOW_MAX_PERIODS = 5


def _window_periods(sources: list[DossierSource]) -> list[StatementPeriod]:
    """Chiusura (o ultimo storico) + anni di piano, mai osservato/rettificato."""
    by_basis = lambda basis: sorted((s.period for s in sources if s.period.basis == basis), key=lambda p: p.year)
    forecast, closings, historicals = by_basis('forecast'), by_basis('closing'), by_basis('historical')
    anchor = closings[-1] if closings else (historicals[-1] if historicals else None)
    selected = ([anchor] if anchor is not None else []) + forecast
    return selected[-_WINDOW_MAX_PERIODS:]


def _closing_quadrature_control(report: FinalReportModel, sources: list[DossierSource]) -> Diagnostic | None:
    """Il terzo controllo di pag. 18: «{M}M rettificati + Q4 = chiusura".

    Il modello **non** lo può misurare: la chiusura è un esercizio a sé (una
    proiezione promossa, o un consuntivo importato), non esiste una stima
    autonoma della quota restante da confrontare, e dove l'identità regge essa
    vale per costruzione — un tautogramma, non un esito. La regola del repo è
    che un controllo mancante vale «non lo so», mai un verdetto: qui «non lo so»
    viene dichiarato, con il suo motivo, a `severity: info` (non allarma la
    readiness: non è un difetto misurato, è un confine del modello).
    """
    if report.practice.workflow_type != 'infrannuale':
        return None  # nessun parziale, nessun controllo da dichiarare.
    adjusted = [s.period for s in sources if s.period.basis == 'adjusted']
    closing = [s.period for s in sources if s.period.basis == 'closing']
    if not adjusted or not closing:
        return None
    months = adjusted[-1].period_months or 12
    return Diagnostic(
        code='closing_progressive_check_unverifiable', severity='info', section='closing',
        message=(f"Il controllo «{months}M rettificati + restante dell'anno = chiusura» non è "
                 "verificabile dal modello: la chiusura è un esercizio autonomo (proiezione "
                 "promossa o consuntivo importato) e nessuna stima indipendente della quota "
                 "restante esiste da riconciliare; dove l'identità regge, vale per costruzione. "
                 "Controllo dichiarato non verificabile, non omesso."),
    )


def extend_dossier(report: FinalReportModel, sources: list[DossierSource]) -> FinalReportModelV2:
    """Freeze exact sources in v2; pagination and AI remain subsequent steps."""
    payload = report.model_dump(mode='python')
    # model_dump omits closing for annual/startup via the inherited wire shape.
    payload.update(schema_version=2, source_hash='0' * 64, model_hash='0' * 64)
    years = report.practice.periods.forecast_years
    title = f'Report Budget {years[0]}' + (f' - {years[-1]}' if len(years) > 1 else '')
    indicators = build_indicator_catalog(sources)
    structure = build_structure_series(sources, indicators)
    by_id = {i.id: i for i in indicators}
    charts = list(report.chart_series)
    for identifier, chart_title, refs in DOSSIER_CHARTS:
        metrics = []
        for ref in refs:
            indicator = by_id[ref]
            by_year = {p.year: v for p, v in zip(indicator.periods, indicator.values) if p.basis == 'forecast'}
            metrics.append({'key': ref, 'label': indicator.label, 'values': [by_year.get(y) for y in years]})
        charts.append(DossierChartSeries(id=identifier, title=chart_title, unit=by_id[refs[0]].unit, categories=years,
            series=metrics, indicator_ids=list(refs), methodology='Valori del catalogo canonico; unità e convenzioni disponibili per ciascun indicatore.'))
    window = _window_periods(sources)
    axis = [p.id for p in window]
    structure_cells = {(group.id, series.id): (group, series)
                       for group in structure for series in group.series}
    for identifier, chart_title, refs, struct_refs, methodology in DOSSIER_WINDOW_CHARTS:
        metrics, units = [], []
        for ref in refs:
            indicator = by_id[ref]
            by_period = {p.id: v for p, v in zip(indicator.periods, indicator.values)}
            metrics.append({'key': ref, 'label': indicator.label, 'values': [by_period[pid] for pid in axis]})
            units.append(indicator.unit)
        for ref in struct_refs:
            group_id, _, series_id = ref.partition(':')
            group, series = structure_cells[(group_id, series_id)]
            by_period = {p.id: v for p, v in zip(group.periods, series.values)}
            metrics.append({'key': ref, 'label': series.label, 'values': [by_period[pid] for pid in axis]})
            units.append(series.unit)
        if any(unit != units[0] for unit in units):
            raise ValueError(f'dossier window chart {identifier} mixes units')
        charts.append(DossierChartSeries(id=identifier, title=chart_title, unit=units[0],
            categories=[p.year for p in window], series=metrics, indicator_ids=list(refs),
            structure_refs=list(struct_refs), period_ids=list(axis), methodology=methodology))
    diagnostics = list(report.diagnostics)
    closing_control = _closing_quadrature_control(report, sources)
    if closing_control is not None and not any(item.code == closing_control.code for item in diagnostics):
        diagnostics.append(closing_control)
    payload.update(document=DocumentIdentity(title=title, budget_years=years),
        detailed_statements=build_detailed_statements(sources), indicator_catalog=indicators,
        structure_series=structure, chart_series=charts, diagnostics=diagnostics,
        editorial_plan=None, editorial_notes=[],
        editorial_readiness=EditorialReadiness(status='pending', reasons=['Piano di impaginazione e commenti per pagina da preparare in M2-02A/M2-00C.']))
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['source_hash'] = draft.calculate_source_hash()
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['model_hash'] = draft.calculate_model_hash()
    return FinalReportModelV2.model_validate(payload)
