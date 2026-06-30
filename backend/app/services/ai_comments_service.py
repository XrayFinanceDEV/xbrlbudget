"""
AI Comments Service - Generate report commentary using Claude Haiku.

Produces 10 short Italian-language comments for the report page:
  1. Dashboard sintetica (overall health, scoring trends)
  2. Composizione patrimoniale (asset/liability structure)
  3. Conto economico e margini (income, margins, profitability)
  4. Analisi strutturale (MS, CCN, MT)
  5. Indici di liquidità (current ratio, quick ratio)
  6. Indici di solvibilità (D/E, financial independence)
  7. Indici di redditività (ROE, ROI, ROS)
  8. Indici di efficienza (turnover ratios)
  9. Break Even Point (BEP, safety margin)
  10. Rendiconto finanziario (cashflow by activity)
"""
import logging
import os
from typing import Any, Dict, Optional

import anthropic
import pydantic
from sqlalchemy.orm import Session

from config import PDF_LLM_MODEL
from database.models import BudgetScenario

logger = logging.getLogger(__name__)

AI_COMMENTS_MAX_TOKENS = 4000


class ReportComments(pydantic.BaseModel):
    """Structured output for 11 report comments."""
    overall_comment: str = pydantic.Field(
        description="3-5 frasi di commento complessivo introduttivo: sintesi dello scenario, punti di forza e debolezza principali, tendenza generale storica vs previsionale, prospettive"
    )
    dashboard_comment: str = pydantic.Field(
        description="2-4 frasi sulla salute complessiva dell'azienda: scoring, Z-Score, rating, tendenza generale"
    )
    composition_comment: str = pydantic.Field(
        description="2-4 frasi sulla struttura patrimoniale: composizione attivo/passivo, equilibrio finanziario, punti critici"
    )
    income_margins_comment: str = pydantic.Field(
        description="2-4 frasi su ricavi, margini, redditività: trend EBITDA, utile netto, efficienza operativa"
    )
    structural_comment: str = pydantic.Field(
        description="2-4 frasi sull'analisi strutturale: margine di struttura (MS), capitale circolante netto (CCN), margine di tesoreria (MT), equilibrio fonti/impieghi"
    )
    liquidity_comment: str = pydantic.Field(
        description="2-4 frasi sugli indici di liquidità: current ratio, quick ratio, capacità di far fronte agli impegni a breve"
    )
    solvency_comment: str = pydantic.Field(
        description="2-4 frasi sugli indici di solvibilità: rapporto D/E, indipendenza finanziaria, struttura del debito, sostenibilità"
    )
    profitability_comment: str = pydantic.Field(
        description="2-4 frasi sugli indici di redditività: ROE, ROI, ROS, leva finanziaria, trend di rendimento"
    )
    efficiency_comment: str = pydantic.Field(
        description="2-4 frasi sugli indici di efficienza: rotazione magazzino, giorni clienti/fornitori, ciclo del circolante"
    )
    break_even_comment: str = pydantic.Field(
        description="2-4 frasi sul break even point: BEP vs ricavi, margine di sicurezza, leva operativa, struttura costi fissi/variabili"
    )
    cashflow_comment: str = pydantic.Field(
        description="2-4 frasi sul rendiconto finanziario: flusso operativo, investimenti, finanziamenti, variazione liquidità"
    )


def _build_tool_schema(model: type[pydantic.BaseModel], tool_name: str) -> dict:
    """Build an Anthropic tool definition from a Pydantic model."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    return {
        "name": tool_name,
        "description": "Record the report comments",
        "input_schema": schema,
    }


def _n(v) -> float:
    """Coalesce None to 0 for safe formatting."""
    return v if v is not None else 0


def _build_data_summary(analysis_data: Dict[str, Any]) -> str:
    """Extract key metrics from analysis data into a concise summary for the LLM."""
    scenario = analysis_data.get("scenario", {})
    company = scenario.get("company", {})
    lines = [
        f"Azienda: {company.get('name', 'N/A')}",
        f"Settore: {company.get('sector', 'N/A')}",
        f"Scenario: {scenario.get('name', 'N/A')} (base {scenario.get('base_year', '')})",
        "",
    ]

    # Collect per-year summaries
    all_years = analysis_data.get("historical_years", []) + analysis_data.get("forecast_years", [])
    calc_by_year = analysis_data.get("calculations", {}).get("by_year", {})

    for yd in sorted(all_years, key=lambda y: y["year"]):
        year = yd["year"]
        y_type = yd.get("type", "?")
        inc = yd.get("income_statement", {})
        bs = yd.get("balance_sheet", {})
        calc = calc_by_year.get(str(year), {})

        revenue = _n(inc.get("revenue"))
        ebitda = _n(inc.get("ebitda"))
        net_profit = _n(inc.get("net_profit"))
        total_assets = _n(bs.get("total_assets"))
        total_equity = _n(bs.get("total_equity"))
        total_debt = _n(bs.get("total_debt"))
        current_assets = _n(bs.get("current_assets"))
        current_liabilities = _n(bs.get("current_liabilities"))
        fixed_assets = _n(bs.get("fixed_assets"))

        ratios = calc.get("ratios", {})
        profitability = ratios.get("profitability", {})
        liquidity = ratios.get("liquidity", {})
        solvency = ratios.get("solvency", {})
        activity = ratios.get("activity", {})
        efficiency = ratios.get("efficiency", {})
        coverage = ratios.get("coverage", {})
        break_even = ratios.get("break_even", {})
        turnover = ratios.get("turnover", {})

        altman = calc.get("altman", {})
        fgpmi = calc.get("fgpmi", {})
        em_score = calc.get("em_score", {})

        label = f"{'S' if y_type == 'historical' else 'P'}{year}"
        lines.append(f"--- {label} ---")
        lines.append(f"Ricavi: {revenue:,.0f} | EBITDA: {ebitda:,.0f} | Utile netto: {net_profit:,.0f}")
        lines.append(f"Totale attivo: {total_assets:,.0f} | Patrimonio netto: {total_equity:,.0f} | Debiti tot: {total_debt:,.0f}")
        lines.append(f"Attivo corr.: {current_assets:,.0f} | Passivo corr.: {current_liabilities:,.0f} | Immobilizzazioni: {fixed_assets:,.0f}")

        # Structural indicators (MS, CCN, MT)
        ccn = current_assets - current_liabilities
        ms = total_equity - fixed_assets
        lines.append(f"CCN: {ccn:,.0f} | MS: {ms:,.0f}")

        # Profitability
        roe = profitability.get("roe")
        roi = profitability.get("roi")
        ros = profitability.get("ros")
        if roe is not None:
            lines.append(f"ROE: {_n(roe):.1f}% | ROI: {_n(roi):.1f}% | ROS: {_n(ros):.1f}%")

        # Extended profitability
        ext_prof = ratios.get("extended_profitability", {})
        ebitda_margin = ext_prof.get("ebitda_margin")
        if ebitda_margin is not None:
            lines.append(f"EBITDA margin: {_n(ebitda_margin):.1f}% | Net margin: {_n(ext_prof.get('net_profit_margin')):.1f}%")

        # Liquidity
        cr = liquidity.get("current_ratio")
        qr = liquidity.get("quick_ratio")
        if cr is not None:
            lines.append(f"Current ratio: {_n(cr):.2f} | Quick ratio: {_n(qr):.2f}")

        # Solvency
        de = solvency.get("debt_to_equity")
        ind_fin = solvency.get("financial_independence")
        if de is not None:
            lines.append(f"D/E: {_n(de):.2f} | Indip. finanziaria: {_n(ind_fin):.1f}%")
            debt_ratio = solvency.get("debt_ratio")
            if debt_ratio is not None:
                lines.append(f"Debt ratio: {_n(debt_ratio):.2f}")

        # Coverage
        interest_cov = coverage.get("interest_coverage")
        if interest_cov is not None:
            lines.append(f"Interest coverage: {_n(interest_cov):.2f}")

        # Activity / Turnover
        inv_days = activity.get("inventory_days") or turnover.get("inventory_days")
        rec_days = activity.get("receivable_days") or turnover.get("receivable_days")
        pay_days = activity.get("payable_days") or turnover.get("payable_days")
        if inv_days is not None:
            lines.append(f"GG magazzino: {_n(inv_days):.0f} | GG clienti: {_n(rec_days):.0f} | GG fornitori: {_n(pay_days):.0f}")

        # Efficiency
        asset_turnover = efficiency.get("asset_turnover")
        if asset_turnover is not None:
            lines.append(f"Asset turnover: {_n(asset_turnover):.2f}")

        # Break-even
        bep = break_even.get("break_even_revenue")
        safety = break_even.get("safety_margin")
        op_lev = break_even.get("operating_leverage")
        if bep is not None:
            lines.append(f"BEP ricavi: {_n(bep):,.0f} | Margine sicurezza: {_n(safety):.1f}% | Leva operativa: {_n(op_lev):.2f}")
            contrib_margin_pct = break_even.get("contribution_margin_percentage")
            if contrib_margin_pct is not None:
                lines.append(f"MdC%: {_n(contrib_margin_pct):.1f}%")

        # Scoring
        if altman.get("z_score") is not None:
            lines.append(f"Altman Z-Score: {altman['z_score']:.2f} ({altman.get('classification', '')})")
        if fgpmi.get("rating_class"):
            lines.append(f"FGPMI: {fgpmi['rating_class']} (score {fgpmi.get('total_score', 0)}/{fgpmi.get('max_score', 0)})")
        if em_score.get("rating"):
            lines.append(f"EM-Score: {em_score['rating']}")

        # BS composition percentages
        if total_assets and total_assets > 0:
            fixed_pct = (fixed_assets / total_assets) * 100
            current_pct = (current_assets / total_assets) * 100
            equity_pct = (total_equity / total_assets) * 100
            lines.append(f"Composizione: Fisso {fixed_pct:.0f}% | Corrente {current_pct:.0f}% | CN/TA {equity_pct:.0f}%")

        lines.append("")

    # Cashflow summary
    cashflow_data = analysis_data.get("calculations", {}).get("cashflow", {}).get("years", [])
    if cashflow_data:
        lines.append("--- RENDICONTO FINANZIARIO ---")
        for cf in cashflow_data:
            year = cf.get("year", "?")
            operating = cf.get("operating_activities", {})
            investing = cf.get("investing_activities", {})
            financing = cf.get("financing_activities", {})
            reconciliation = cf.get("cash_reconciliation", {})
            op_cf = _n(operating.get("total_operating_cashflow"))
            inv_cf = _n(investing.get("total_investing_cashflow"))
            fin_cf = _n(financing.get("total_financing_cashflow"))
            total_cf = _n(reconciliation.get("total_cashflow"))
            cash_end = _n(reconciliation.get("cash_ending"))
            lines.append(f"{year}: Operativo {op_cf:,.0f} | Investimenti {inv_cf:,.0f} | Finanziamenti {fin_cf:,.0f} | Totale {total_cf:,.0f} | Cassa finale {cash_end:,.0f}")
        lines.append("")

    return "\n".join(lines)


_NUMBER_FORMAT_RULE = (
    "FORMATO NUMERI: quando citi un importo scrivilo SEMPRE per intero in euro con il "
    "separatore delle migliaia (punto), es. «2.820.468 €» oppure «-57.600 €». NON usare MAI "
    "abbreviazioni come K, k, M, mln, mld, B, né formati tipo «€2,8M», «€10,3M» o «€-57,6K», "
    "né notazione scientifica. Le percentuali restano normali (es. «1,8%»)."
)

SYSTEM_PROMPT = (
    "Sei un analista finanziario senior italiano. Genera 11 commenti brevi per un report di "
    "analisi previsionale. Ogni commento: 2-4 frasi (il commento complessivo 3-5 frasi), "
    "tono professionale, evidenzia punti di forza, rischi e tendenze. Non ripetere numeri "
    "già visibili nel report — interpreta e aggiungi valore con osservazioni qualitative. "
    + _NUMBER_FORMAT_RULE +
    " Usa il tool fornito per strutturare la risposta."
)


def generate_report_comments(analysis_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate AI comments for 10 report sections using Claude Haiku.

    Returns dict with keys: overall_comment, dashboard_comment, composition_comment,
    income_margins_comment, structural_comment, liquidity_comment, solvency_comment,
    profitability_comment, efficiency_comment, break_even_comment, cashflow_comment.
    Returns empty dict if no API key or on any error.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("No ANTHROPIC_API_KEY set — skipping AI comments")
        return {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        data_summary = _build_data_summary(analysis_data)
        tool = _build_tool_schema(ReportComments, "report_comments")

        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=AI_COMMENTS_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Analizza i seguenti dati finanziari e genera i 10 commenti richiesti "
                    "usando il tool report_comments.\n\n"
                    f"{data_summary}"
                ),
            }],
            tools=[tool],
            tool_choice={"type": "tool", "name": "report_comments"},
        )

        for block in response.content:
            if block.type == "tool_use":
                result = ReportComments.model_validate(block.input)
                return result.model_dump()

        logger.warning("No tool_use block in AI comments response")
        return {}

    except Exception as e:
        logger.warning(f"AI comments generation failed: {e}")
        return {}


# Mapping from comment dict keys to BudgetScenario column names
_COMMENT_FIELDS = [
    ("overall_comment", "ai_comment_overall"),
    ("dashboard_comment", "ai_comment_dashboard"),
    ("composition_comment", "ai_comment_composition"),
    ("income_margins_comment", "ai_comment_income_margins"),
    ("structural_comment", "ai_comment_structural"),
    ("liquidity_comment", "ai_comment_liquidity"),
    ("solvency_comment", "ai_comment_solvency"),
    ("profitability_comment", "ai_comment_profitability"),
    ("efficiency_comment", "ai_comment_efficiency"),
    ("break_even_comment", "ai_comment_break_even"),
    ("cashflow_comment", "ai_comment_cashflow"),
]


def get_stored_comments(db: Session, scenario_id: int) -> Dict[str, str]:
    """Read stored AI comments from BudgetScenario. Returns empty dict if none."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        return {}
    result = {}
    for dict_key, col_name in _COMMENT_FIELDS:
        value = getattr(scenario, col_name, None)
        if value:
            result[dict_key] = value
    return result


def save_comments(db: Session, scenario_id: int, comments: Dict[str, str]) -> None:
    """Write AI comments to BudgetScenario columns."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        return
    for dict_key, col_name in _COMMENT_FIELDS:
        setattr(scenario, col_name, comments.get(dict_key))
    db.commit()


# ========================================================================
# Infrannuale (intra-year analysis) comments — Stampa tab
# ========================================================================

class InfrannualeComments(pydantic.BaseModel):
    """Structured output for 6 infrannuale Stampa comments (Italian)."""
    overall: str = pydantic.Field(
        description="2-3 frasi introduttive complessive: confronto storico vs infrannuale e tendenza proiettata, salute generale."
    )
    ce_confronto: str = pydantic.Field(
        description="2-3 frasi sul confronto di Conto Economico: evoluzione ricavi, margini e utile tra anno di riferimento e periodo infrannuale (annualizzato o diretto)."
    )
    sp_confronto: str = pydantic.Field(
        description="2-3 frasi sul confronto di Stato Patrimoniale: variazioni principali di attivo, patrimonio netto e debiti."
    )
    ce_proiezione: str = pydantic.Field(
        description="2-3 frasi sulla proiezione di Conto Economico a fine anno: trend su ricavi, costi e redditività attesa."
    )
    sp_proiezione: str = pydantic.Field(
        description="2-3 frasi sulla proiezione di Stato Patrimoniale a fine anno: evoluzione capitale circolante, indebitamento, liquidità."
    )
    indicatori: str = pydantic.Field(
        description="2-3 frasi sugli indicatori della crisi d'impresa: rating, punti critici, confronto tra colonne."
    )


_INFRANNUALE_SYSTEM_PROMPT = (
    "Sei un analista finanziario senior italiano. Stai commentando un'analisi infrannuale "
    "(situazione intermedia di X mesi proiettata a 12 mesi) per un report da stampare. "
    "Produci 6 commenti brevi e professionali: un commento introduttivo complessivo e un "
    "commento per ciascuna delle 5 tabelle (CE confronto, SP confronto, CE proiezione, SP "
    "proiezione, indicatori della crisi d'impresa). Tono professionale, 2-3 frasi ciascuno. "
    "Non elencare numeri già visibili nelle tabelle: interpreta, evidenzia tendenze, rischi "
    "e punti di forza. "
    + _NUMBER_FORMAT_RULE +
    " Usa il tool fornito."
)


def _build_infrannuale_summary(ctx: Dict[str, Any]) -> str:
    """Compact text summary of comparison + projection + indicators for the LLM."""
    scenario = ctx.get("scenario", {})
    lines = [
        f"Azienda: {scenario.get('company_name', 'N/A')}",
        f"Scenario: {scenario.get('name', 'N/A')}",
        f"Anno riferimento: {ctx.get('reference_year')} (12M) | Periodo infrannuale: {ctx.get('period_months')}M {ctx.get('partial_year')}",
        "",
    ]

    # CE summary (partial vs reference + annualized + projected)
    lines.append("--- CONTO ECONOMICO ---")
    for code, label in [
        ("ce01_ricavi_vendite", "Ricavi"),
        ("_totale_vp", "Tot. valore produzione"),
        ("_totale_cp", "Tot. costi produzione"),
        ("_ebitda", "EBITDA"),
        ("_ebit", "EBIT"),
        ("_totale_fin", "Fin."),
        ("_profit_before_tax", "PBT"),
        ("ce20_imposte", "Imposte"),
        ("_net_profit", "Utile netto"),
    ]:
        row = ctx.get("income_map", {}).get(code, {})
        if not row:
            continue
        ref = _n(row.get("reference_value"))
        partial = _n(row.get("partial_value"))
        ann = _n(row.get("annualized_value"))
        proj = _n(row.get("projected_value"))
        lines.append(f"{label}: S={ref:,.0f} | I={partial:,.0f} | Ann={ann:,.0f} | P={proj:,.0f}")
    lines.append("")

    # BS summary
    lines.append("--- STATO PATRIMONIALE ---")
    for code, label in [
        ("_totale_attivo", "Tot. Attivo"),
        ("sp05_rimanenze", "Rimanenze"),
        ("sp06_crediti_breve", "Crediti breve"),
        ("sp09_disponibilita_liquide", "Cassa"),
        ("_totale_pn", "Patrimonio Netto"),
        ("sp14_fondi_rischi", "Fondi rischi"),
        ("sp15_tfr", "TFR"),
        ("_totale_debiti", "Tot. Debiti"),
        ("sp16_debiti_breve", "Debiti breve"),
        ("sp17_debiti_lungo", "Debiti lungo"),
    ]:
        row = ctx.get("balance_map", {}).get(code, {})
        if not row:
            continue
        ref = _n(row.get("reference_value"))
        partial = _n(row.get("partial_value"))
        proj = _n(row.get("projected_value"))
        lines.append(f"{label}: S={ref:,.0f} | I={partial:,.0f} | P={proj:,.0f}")
    lines.append("")

    # Indicators
    indicators = ctx.get("indicators", {})
    if indicators:
        lines.append("--- INDICATORI ---")
        for col_name, vals in indicators.items():
            lines.append(f"{col_name}: " + " | ".join(f"{k}={v}" for k, v in vals.items()))
        lines.append("")

    # Rating
    ratings = ctx.get("ratings", {})
    if ratings:
        lines.append("--- RATING ---")
        for col_name, r in ratings.items():
            lines.append(f"{col_name}: {r.get('code')} ({r.get('label')}) — oltre={r.get('oltre_count')}/14, alerts={r.get('alerts', 0)}")

    return "\n".join(lines)


def generate_infrannuale_comments(ctx: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate 6 AI comments for the infrannuale Stampa via Claude Haiku.

    `ctx` shape (built by the endpoint):
        {
          scenario: {name, company_name, ...},
          reference_year, partial_year, period_months,
          income_map: {code: {reference_value, partial_value, annualized_value, projected_value}},
          balance_map: {code: {reference_value, partial_value, projected_value}},
          indicators: {"Storico": {...}, "Infrann.": {...}, "Proiez.": {...}},
          ratings: {"Storico": {code, label, oltre_count, alerts}, ...},
        }

    Returns {} on missing API key or any error.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("No ANTHROPIC_API_KEY set — skipping infrannuale AI comments")
        return {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        summary = _build_infrannuale_summary(ctx)
        tool = _build_tool_schema(InfrannualeComments, "infrannuale_comments")

        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=AI_COMMENTS_MAX_TOKENS,
            system=_INFRANNUALE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Analizza i dati seguenti e genera i 6 commenti richiesti usando il tool "
                    "infrannuale_comments.\n\n"
                    f"{summary}"
                ),
            }],
            tools=[tool],
            tool_choice={"type": "tool", "name": "infrannuale_comments"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return InfrannualeComments.model_validate(block.input).model_dump()

        logger.warning("No tool_use block in infrannuale AI comments response")
        return {}

    except Exception as e:
        logger.warning(f"Infrannuale AI comments generation failed: {e}")
        return {}


import json as _json


def get_infrannuale_comments(db: Session, scenario_id: int) -> Dict[str, str]:
    """Read stored infrannuale AI comments (JSON) from BudgetScenario."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario or not scenario.ai_comments_infrannuale:
        return {}
    try:
        data = _json.loads(scenario.ai_comments_infrannuale)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_infrannuale_comments(db: Session, scenario_id: int, comments: Dict[str, str]) -> None:
    """Write infrannuale AI comments to BudgetScenario as JSON text."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        return
    # Keep only the six known keys to avoid pollution
    allowed = {"overall", "ce_confronto", "sp_confronto", "ce_proiezione", "sp_proiezione", "indicatori"}
    cleaned = {k: v for k, v in comments.items() if k in allowed and isinstance(v, str)}
    scenario.ai_comments_infrannuale = _json.dumps(cleaned) if cleaned else None
    db.commit()
