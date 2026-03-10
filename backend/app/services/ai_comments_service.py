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
    """Structured output for 10 report comments."""
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
        "description": "Record the 10 report comments",
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


SYSTEM_PROMPT = (
    "Sei un analista finanziario senior italiano. Genera 10 commenti brevi per un report di "
    "analisi previsionale. Ogni commento: 2-4 frasi, tono professionale, evidenzia punti di "
    "forza, rischi e tendenze. Non ripetere numeri già visibili nel report — interpreta e "
    "aggiungi valore con osservazioni qualitative. Usa il tool fornito per strutturare la risposta."
)


def generate_report_comments(analysis_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate AI comments for 10 report sections using Claude Haiku.

    Returns dict with keys: dashboard_comment, composition_comment, income_margins_comment,
    structural_comment, liquidity_comment, solvency_comment, profitability_comment,
    efficiency_comment, break_even_comment, cashflow_comment.
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
