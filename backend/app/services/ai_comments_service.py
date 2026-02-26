"""
AI Comments Service - Generate report commentary using Claude Haiku.

Produces 3 short Italian-language comments for the report page:
  1. Dashboard sintetica (overall health, scoring trends)
  2. Composizione patrimoniale (asset/liability structure)
  3. Conto economico e margini (income, margins, profitability)
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

AI_COMMENTS_MAX_TOKENS = 1500


class ReportComments(pydantic.BaseModel):
    """Structured output for 3 report comments."""
    dashboard_comment: str = pydantic.Field(
        description="2-4 frasi sulla salute complessiva dell'azienda: scoring, Z-Score, rating, tendenza generale"
    )
    composition_comment: str = pydantic.Field(
        description="2-4 frasi sulla struttura patrimoniale: composizione attivo/passivo, equilibrio finanziario, punti critici"
    )
    income_margins_comment: str = pydantic.Field(
        description="2-4 frasi su ricavi, margini, redditività: trend EBITDA, utile netto, efficienza operativa"
    )


def _build_tool_schema(model: type[pydantic.BaseModel], tool_name: str) -> dict:
    """Build an Anthropic tool definition from a Pydantic model."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    return {
        "name": tool_name,
        "description": "Record the 3 report comments",
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

        ratios = calc.get("ratios", {})
        profitability = ratios.get("profitability", {})
        liquidity = ratios.get("liquidity", {})
        solvency = ratios.get("solvency", {})

        altman = calc.get("altman", {})
        fgpmi = calc.get("fgpmi", {})
        em_score = calc.get("em_score", {})

        label = f"{'S' if y_type == 'historical' else 'P'}{year}"
        lines.append(f"--- {label} ---")
        lines.append(f"Ricavi: {revenue:,.0f} | EBITDA: {ebitda:,.0f} | Utile netto: {net_profit:,.0f}")
        lines.append(f"Totale attivo: {total_assets:,.0f} | Patrimonio netto: {total_equity:,.0f} | Debiti tot: {total_debt:,.0f}")
        lines.append(f"Attivo corr.: {current_assets:,.0f} | Passivo corr.: {current_liabilities:,.0f}")

        roe = profitability.get("roe")
        roi = profitability.get("roi")
        ros = profitability.get("ros")
        if roe is not None:
            lines.append(f"ROE: {_n(roe):.1f}% | ROI: {_n(roi):.1f}% | ROS: {_n(ros):.1f}%")

        cr = liquidity.get("current_ratio")
        qr = liquidity.get("quick_ratio")
        if cr is not None:
            lines.append(f"Current ratio: {_n(cr):.2f} | Quick ratio: {_n(qr):.2f}")

        de = solvency.get("debt_to_equity")
        ind_fin = solvency.get("financial_independence")
        if de is not None:
            lines.append(f"D/E: {_n(de):.2f} | Indip. finanziaria: {_n(ind_fin):.1f}%")

        if altman.get("z_score") is not None:
            lines.append(f"Altman Z-Score: {altman['z_score']:.2f} ({altman.get('classification', '')})")
        if fgpmi.get("rating_class"):
            lines.append(f"FGPMI: {fgpmi['rating_class']} (score {fgpmi.get('total_score', 0)}/{fgpmi.get('max_score', 0)})")
        if em_score.get("rating"):
            lines.append(f"EM-Score: {em_score['rating']}")

        # BS composition percentages
        if total_assets and total_assets > 0:
            fixed_pct = (_n(bs.get("fixed_assets")) / total_assets) * 100
            current_pct = (current_assets / total_assets) * 100
            equity_pct = (total_equity / total_assets) * 100
            lines.append(f"Composizione: Fisso {fixed_pct:.0f}% | Corrente {current_pct:.0f}% | CN/TA {equity_pct:.0f}%")

        # EBITDA margin
        if revenue and revenue > 0:
            ebitda_margin = (ebitda / revenue) * 100
            net_margin = (net_profit / revenue) * 100
            lines.append(f"EBITDA margin: {ebitda_margin:.1f}% | Net margin: {net_margin:.1f}%")

        lines.append("")

    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Sei un analista finanziario senior italiano. Genera 3 commenti brevi per un report di "
    "analisi previsionale. Ogni commento: 2-4 frasi, tono professionale, evidenzia punti di "
    "forza, rischi e tendenze. Non ripetere numeri già visibili nel report — interpreta e "
    "aggiungi valore con osservazioni qualitative. Usa il tool fornito per strutturare la risposta."
)


def generate_report_comments(analysis_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate AI comments for 3 report sections using Claude Haiku.

    Returns dict with keys: dashboard_comment, composition_comment, income_margins_comment.
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
                    "Analizza i seguenti dati finanziari e genera i 3 commenti richiesti "
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


def get_stored_comments(db: Session, scenario_id: int) -> Dict[str, str]:
    """Read stored AI comments from BudgetScenario. Returns empty dict if none."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        return {}
    result = {}
    if scenario.ai_comment_dashboard:
        result["dashboard_comment"] = scenario.ai_comment_dashboard
    if scenario.ai_comment_composition:
        result["composition_comment"] = scenario.ai_comment_composition
    if scenario.ai_comment_income_margins:
        result["income_margins_comment"] = scenario.ai_comment_income_margins
    return result


def save_comments(db: Session, scenario_id: int, comments: Dict[str, str]) -> None:
    """Write AI comments to BudgetScenario columns."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        return
    scenario.ai_comment_dashboard = comments.get("dashboard_comment")
    scenario.ai_comment_composition = comments.get("composition_comment")
    scenario.ai_comment_income_margins = comments.get("income_margins_comment")
    db.commit()
