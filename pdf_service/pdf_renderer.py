"""
PDF Renderer: builds the ReportLab document with all pages, tables, and charts.
"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether, HRFlowable,
)
from reportlab.lib.units import mm, cm
from reportlab.lib import colors

from pdf_service.styles import (
    PAGE_WIDTH, PAGE_HEIGHT, MARGIN_LEFT, MARGIN_RIGHT,
    MARGIN_TOP, MARGIN_BOTTOM, CONTENT_WIDTH,
    DARK_BLUE, MEDIUM_BLUE, LIGHT_BLUE, VERY_LIGHT_BLUE,
    DARK_GRAY, MEDIUM_GRAY, LIGHT_GRAY, VERY_LIGHT_GRAY,
    WHITE, BLACK, GREEN, LIGHT_GREEN, YELLOW, LIGHT_YELLOW,
    RED, LIGHT_RED, FORECAST_BG,
    FONT_TABLE, FONT_TABLE_HEADER, FONT_SMALL,
    get_styles, get_data_table_style,
)
from pdf_service.italian_text import (
    REPORT_TITLE, REPORT_SUBTITLE, COVER_PREPARED_BY, COVER_DATE_PREFIX,
    COVER_YEARS_PREFIX, SECTION_COMPANY_DATA, SECTION_INTRODUCTION,
    SECTION_DASHBOARD, SECTION_ASSET_COMPOSITION, SECTION_INCOME_MARGINS,
    SECTION_STRUCTURAL_ANALYSIS, SECTION_RATIOS, SECTION_ALTMAN,
    SECTION_EM_SCORE, SECTION_FGPMI, SECTION_CASHFLOW,
    SECTION_BALANCE_SHEET, SECTION_INCOME_STATEMENT,
    SECTION_RECLASSIFIED_BS, SECTION_CASHFLOW_STATEMENT,
    SECTION_NOTES, SECTION_BREAK_EVEN,
    COMPANY_NAME, COMPANY_TAX_ID, COMPANY_SECTOR, COMPANY_ANALYSIS_YEARS,
    SECTOR_NAMES, INTRODUCTION_TEXT, NOTES_TEXT,
    DASHBOARD_SUBTITLE, ALTMAN_SAFE, ALTMAN_GRAY, ALTMAN_DISTRESS,
    BS_LABELS, BS_AGGREGATE_LABELS, IS_LABELS, IS_AGGREGATE_LABELS,
    RECLASSIFIED_BS_LABELS, RATIO_CATEGORIES, RATIO_LABELS,
    CF_LABELS,
)
from pdf_service.em_score import EM_SCORE_TABLE, get_em_score_description
from pdf_service.report_generator import ReportData, YearData


def _fmt(value, decimals=2, is_pct=False, is_ratio=False, is_days=False) -> str:
    """Format a numeric value for display in tables."""
    if value is None:
        return "-"
    v = float(value) if isinstance(value, Decimal) else float(value)
    if is_pct:
        return f"{v * 100:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    if is_ratio:
        return f"{v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if is_days:
        return f"{v:,.0f} gg".replace(",", ".")
    # Currency: Italian format
    if abs(v) < 0.005:
        return "0"
    sign = "-" if v < 0 else ""
    abs_v = abs(v)
    int_part = int(abs_v)
    dec_part = round((abs_v - int_part) * 100)
    int_str = f"{int_part:,}".replace(",", ".")
    return f"{sign}{int_str},{dec_part:02d}"


def _pct_fmt(value) -> str:
    """Format as percentage (value already in 0-1 range)."""
    return _fmt(value, is_pct=True)


def _cur_fmt(value) -> str:
    """Format as currency."""
    return _fmt(value)


class PDFReportRenderer:
    """Assembles the PDF document from ReportData."""

    def __init__(self, data: ReportData):
        self.data = data
        self.styles = get_styles()
        self.elements = []
        self.page_number = 0

    def render(self) -> BytesIO:
        """Render the complete PDF and return as BytesIO."""
        buf = BytesIO()

        doc = SimpleDocTemplate(
            buf,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=f"Analisi {self.data.company.name}",
            author="XBRL Budget",
        )

        self._build_cover()
        self._build_company_data()
        self._build_introduction()
        self._build_dashboard()
        self._build_composition()
        self._build_income_margins()
        self._build_structural_analysis()
        self._build_ratio_pages()
        self._build_altman_detail()
        self._build_em_score()
        self._build_fgpmi_detail()
        self._build_break_even()
        self._build_cashflow_indices()
        self._build_appendix_bs()
        self._build_appendix_is()
        self._build_appendix_reclassified()
        self._build_appendix_cashflow()
        self._build_notes()

        doc.build(self.elements, onFirstPage=self._header_footer,
                  onLaterPages=self._header_footer)

        buf.seek(0)
        return buf

    def _header_footer(self, canvas, doc):
        """Draw header and footer on each page."""
        canvas.saveState()
        # Header line
        canvas.setStrokeColor(MEDIUM_BLUE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_LEFT, PAGE_HEIGHT - MARGIN_TOP + 5 * mm,
                    PAGE_WIDTH - MARGIN_RIGHT, PAGE_HEIGHT - MARGIN_TOP + 5 * mm)

        # Header text
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MEDIUM_GRAY)
        canvas.drawString(MARGIN_LEFT, PAGE_HEIGHT - MARGIN_TOP + 7 * mm,
                          self.data.company.name)
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT,
                               PAGE_HEIGHT - MARGIN_TOP + 7 * mm,
                               REPORT_TITLE)

        # Footer line
        canvas.line(MARGIN_LEFT, MARGIN_BOTTOM - 5 * mm,
                    PAGE_WIDTH - MARGIN_RIGHT, MARGIN_BOTTOM - 5 * mm)

        # Footer text
        canvas.drawString(MARGIN_LEFT, MARGIN_BOTTOM - 10 * mm,
                          "XBRL Budget - Analisi Finanziaria")
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT,
                               MARGIN_BOTTOM - 10 * mm,
                               f"Pag. {doc.page}")
        canvas.restoreState()

    # ===== PAGE BUILDERS =====

    def _build_cover(self):
        """Cover page."""
        self.elements.append(Spacer(1, 60 * mm))
        self.elements.append(Paragraph(REPORT_TITLE, self.styles['CoverTitle']))
        self.elements.append(Spacer(1, 5 * mm))

        # Company name
        self.elements.append(Paragraph(
            self.data.company.name, self.styles['CoverSubtitle']))
        self.elements.append(Spacer(1, 15 * mm))

        # Horizontal rule
        self.elements.append(HRFlowable(
            width="60%", thickness=2, color=MEDIUM_BLUE,
            spaceBefore=5 * mm, spaceAfter=10 * mm))

        # Years
        years = [yd.year for yd in self.data.years]
        years_str = " - ".join(str(y) for y in years)
        self.elements.append(Paragraph(
            f"{COVER_YEARS_PREFIX} {years_str}", self.styles['CoverSubtitle']))
        self.elements.append(Spacer(1, 10 * mm))

        # Date
        date_str = datetime.now().strftime("%d/%m/%Y")
        self.elements.append(Paragraph(
            f"{COVER_DATE_PREFIX} {date_str}", self.styles['CoverSubtitle']))
        self.elements.append(Spacer(1, 20 * mm))

        self.elements.append(Paragraph(
            COVER_PREPARED_BY, self.styles['SmallText']))
        self.elements.append(PageBreak())

    def _build_company_data(self):
        """Company data page."""
        self.elements.append(Paragraph(SECTION_COMPANY_DATA, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 5 * mm))

        sector_name = SECTOR_NAMES.get(self.data.sector, f"Settore {self.data.sector}")
        years = [yd.year for yd in self.data.years]

        table_data = [
            [COMPANY_NAME, self.data.company.name],
            [COMPANY_TAX_ID, self.data.company.tax_id or "N/D"],
            [COMPANY_SECTOR, sector_name],
            [COMPANY_ANALYSIS_YEARS, " - ".join(str(y) for y in years)],
            ["Scenario", self.data.scenario.name],
            ["Anno Base", str(self.data.scenario.base_year)],
        ]

        t = Table(table_data, colWidths=[55 * mm, CONTENT_WIDTH - 55 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), DARK_BLUE),
            ('TEXTCOLOR', (1, 0), (1, -1), DARK_GRAY),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, LIGHT_GRAY),
            ('LINEBELOW', (0, -1), (-1, -1), 1, MEDIUM_BLUE),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_introduction(self):
        """Introduction page."""
        self.elements.append(Paragraph(SECTION_INTRODUCTION, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 5 * mm))

        for para in INTRODUCTION_TEXT.split('\n\n'):
            self.elements.append(Paragraph(para.strip(), self.styles['BodyText_Custom']))
        self.elements.append(PageBreak())

    def _build_dashboard(self):
        """Dashboard page with 3 gauge charts."""
        self.elements.append(Paragraph(SECTION_DASHBOARD, self.styles['SectionTitle']))
        self.elements.append(Paragraph(DASHBOARD_SUBTITLE, self.styles['SubsectionTitle']))
        self.elements.append(Spacer(1, 5 * mm))

        # 3 gauge charts in a row
        gauge_keys = ['gauge_altman', 'gauge_fgpmi', 'gauge_em']
        gauge_images = []
        for key in gauge_keys:
            if key in self.data.chart_images:
                img = Image(self.data.chart_images[key],
                            width=55 * mm, height=42 * mm)
                gauge_images.append(img)
            else:
                gauge_images.append(Paragraph("N/D", self.styles['SmallText']))

        if gauge_images:
            t = Table([gauge_images], colWidths=[CONTENT_WIDTH / 3] * 3)
            t.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            self.elements.append(t)

        self.elements.append(Spacer(1, 8 * mm))

        # Summary metrics table
        latest = self.data.years[-1]
        summary_data = [
            ["Indicatore", "Valore", "Stato"],
            ["Altman Z-Score", f"{float(latest.altman.z_score):.2f}",
             self._altman_status(latest.altman.classification)],
            ["FGPMI Rating", latest.fgpmi.rating_code,
             latest.fgpmi.risk_level],
            ["EM-Score", self.data.em_score_rating,
             get_em_score_description(self.data.em_score_rating)],
            ["Ricavi", _cur_fmt(latest.inc.revenue), ""],
            ["EBITDA", _cur_fmt(latest.inc.ebitda),
             _pct_fmt(latest.ratios['profitability'].ebitda_margin)],
            ["Utile Netto", _cur_fmt(latest.inc.net_profit),
             _pct_fmt(latest.ratios['profitability'].net_margin)],
            ["Patrimonio Netto", _cur_fmt(latest.bs.total_equity), ""],
            ["Current Ratio", _fmt(latest.ratios['liquidity'].current_ratio, is_ratio=True), ""],
            ["ROE", _pct_fmt(latest.ratios['profitability'].roe), ""],
        ]

        col_widths = [60 * mm, 50 * mm, CONTENT_WIDTH - 110 * mm]
        t = Table(summary_data, colWidths=col_widths)
        style = get_data_table_style(len(summary_data))
        t.setStyle(style)
        self.elements.append(t)
        self.elements.append(PageBreak())

    def _altman_status(self, classification: str) -> str:
        if classification == "safe":
            return ALTMAN_SAFE
        elif classification == "gray_zone":
            return ALTMAN_GRAY
        return ALTMAN_DISTRESS

    def _build_composition(self):
        """Asset/Liability composition page."""
        self.elements.append(Paragraph(
            SECTION_ASSET_COMPOSITION, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        if 'composition_assets' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['composition_assets'],
                width=CONTENT_WIDTH, height=70 * mm))
        self.elements.append(Spacer(1, 5 * mm))

        if 'composition_liabilities' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['composition_liabilities'],
                width=CONTENT_WIDTH, height=70 * mm))

        self.elements.append(PageBreak())

    def _build_income_margins(self):
        """Income margins pages."""
        self.elements.append(Paragraph(
            SECTION_INCOME_MARGINS, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        if 'income_margins' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['income_margins'],
                width=CONTENT_WIDTH, height=60 * mm))
        self.elements.append(Spacer(1, 3 * mm))

        if 'margin_pct' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['margin_pct'],
                width=CONTENT_WIDTH, height=60 * mm))
        self.elements.append(Spacer(1, 3 * mm))

        # Income variation table
        self._build_income_variation_table()
        self.elements.append(PageBreak())

        # Waterfall on next page
        if 'income_waterfall' in self.data.chart_images:
            self.elements.append(Paragraph(
                "Composizione del Reddito", self.styles['SubsectionTitle']))
            self.elements.append(Image(
                self.data.chart_images['income_waterfall'],
                width=CONTENT_WIDTH, height=75 * mm))
            self.elements.append(PageBreak())

    def _build_income_variation_table(self):
        """Table showing YoY income statement variations."""
        years = [yd.year for yd in self.data.years]
        header = ["Voce"] + [str(y) for y in years]
        if len(years) >= 2:
            header.append("Var. %")

        rows = [header]
        metrics = [
            ("Ricavi", lambda yd: yd.inc.revenue),
            ("Valore Produzione", lambda yd: yd.inc.production_value),
            ("EBITDA", lambda yd: yd.inc.ebitda),
            ("EBIT", lambda yd: yd.inc.ebit),
            ("Utile Netto", lambda yd: yd.inc.net_profit),
        ]

        for label, fn in metrics:
            row = [label]
            for yd in self.data.years:
                row.append(_cur_fmt(fn(yd)))
            if len(self.data.years) >= 2:
                prev = float(fn(self.data.years[-2]))
                curr = float(fn(self.data.years[-1]))
                if prev != 0:
                    var = ((curr - prev) / abs(prev)) * 100
                    row.append(f"{var:+.1f}%")
                else:
                    row.append("N/A")
            rows.append(row)

        n_cols = len(header)
        label_w = 45 * mm
        data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else CONTENT_WIDTH
        col_widths = [label_w] + [data_w] * (n_cols - 1)

        t = Table(rows, colWidths=col_widths)
        t.setStyle(get_data_table_style(len(rows)))
        self.elements.append(t)

    def _build_structural_analysis(self):
        """Structural analysis page."""
        self.elements.append(Paragraph(
            SECTION_STRUCTURAL_ANALYSIS, self.styles['SectionTitle']))

        if 'structural' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['structural'],
                width=CONTENT_WIDTH, height=65 * mm))

        # Table
        self._build_multi_year_ratio_table(
            "working_capital",
            ["ms", "ccn", "mt", "ccln"],
            is_currency=True)

        self.elements.append(PageBreak())

    def _build_ratio_pages(self):
        """Build pages for each ratio category."""
        # Coverage / Solidity
        self.elements.append(Paragraph(SECTION_RATIOS, self.styles['SectionTitle']))

        if 'ratio_coverage' in self.data.chart_images:
            self.elements.append(Paragraph(
                "Indici di Solidita", self.styles['SubsectionTitle']))
            self.elements.append(Image(
                self.data.chart_images['ratio_coverage'],
                width=CONTENT_WIDTH, height=55 * mm))
        self._build_multi_year_ratio_table(
            "coverage",
            ["fixed_assets_coverage_with_equity_and_ltdebt",
             "fixed_assets_coverage_with_equity",
             "independence_from_third_parties"],
            is_pct=True)
        self.elements.append(PageBreak())

        # Liquidity
        if 'ratio_liquidity' in self.data.chart_images:
            self.elements.append(Paragraph(
                "Indici di Liquidita", self.styles['SubsectionTitle']))
            self.elements.append(Image(
                self.data.chart_images['ratio_liquidity'],
                width=CONTENT_WIDTH, height=55 * mm))
        self._build_multi_year_ratio_table(
            "liquidity",
            ["current_ratio", "quick_ratio", "acid_test"],
            is_ratio=True)
        self.elements.append(PageBreak())

        # Turnover
        self.elements.append(Paragraph(
            "Indici di Rotazione e Durata", self.styles['SubsectionTitle']))
        self._build_multi_year_ratio_table(
            "turnover",
            ["inventory_turnover", "receivables_turnover", "payables_turnover",
             "working_capital_turnover", "total_assets_turnover"],
            is_ratio=True)
        self.elements.append(Spacer(1, 3 * mm))

        if 'ratio_activity' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['ratio_activity'],
                width=CONTENT_WIDTH, height=55 * mm))
        self._build_multi_year_ratio_table(
            "activity",
            ["inventory_turnover_days", "receivables_turnover_days",
             "payables_turnover_days", "working_capital_days",
             "cash_conversion_cycle"],
            is_days=True)
        self.elements.append(PageBreak())

        # Profitability
        if 'ratio_profitability' in self.data.chart_images:
            self.elements.append(Paragraph(
                "Indici di Redditivita", self.styles['SubsectionTitle']))
            self.elements.append(Image(
                self.data.chart_images['ratio_profitability'],
                width=CONTENT_WIDTH, height=55 * mm))
        self._build_multi_year_ratio_table(
            "profitability",
            ["roe", "roi", "ros", "rod", "ebitda_margin", "ebit_margin", "net_margin"],
            is_pct=True)
        self.elements.append(Spacer(1, 3 * mm))

        # Extended profitability
        self._build_multi_year_ratio_table(
            "extended_profitability",
            ["spread", "financial_leverage_effect", "ebitda_on_sales",
             "financial_charges_on_revenue"],
            is_pct=True)
        self.elements.append(PageBreak())

        # Efficiency
        self.elements.append(Paragraph(
            "Indici di Efficienza", self.styles['SubsectionTitle']))
        self._build_multi_year_ratio_table(
            "efficiency",
            ["revenue_per_employee_cost", "revenue_per_materials_cost"],
            is_ratio=True)
        self.elements.append(Spacer(1, 5 * mm))

        # Solvency
        self.elements.append(Paragraph(
            "Indici di Solvibilita", self.styles['SubsectionTitle']))
        self._build_multi_year_ratio_table(
            "solvency",
            ["autonomy_index", "leverage_ratio", "debt_to_equity", "debt_to_production"],
            is_ratio=True)

        if 'ratio_solvency' in self.data.chart_images:
            self.elements.append(Spacer(1, 3 * mm))
            self.elements.append(Image(
                self.data.chart_images['ratio_solvency'],
                width=CONTENT_WIDTH, height=55 * mm))
        self.elements.append(PageBreak())

    def _build_multi_year_ratio_table(self, category: str, ratio_keys: List[str],
                                      is_pct=False, is_ratio=False,
                                      is_currency=False, is_days=False):
        """Build a multi-year table for a ratio category."""
        years = [yd.year for yd in self.data.years]
        header = ["Indice", "Formula"] + [str(y) for y in years]
        rows = [header]

        for key in ratio_keys:
            label_info = RATIO_LABELS.get(key, (key, ""))
            label, formula = label_info
            row = [label, formula]

            for yd in self.data.years:
                val = getattr(yd.ratios[category], key, None)
                if val is None:
                    row.append("-")
                elif is_currency:
                    row.append(_cur_fmt(val))
                elif is_pct:
                    row.append(_pct_fmt(val))
                elif is_days:
                    row.append(_fmt(val, is_days=True))
                else:
                    row.append(_fmt(val, is_ratio=True))
            rows.append(row)

        n_years = len(years)
        label_w = 55 * mm
        formula_w = 25 * mm
        data_w = (CONTENT_WIDTH - label_w - formula_w) / n_years if n_years > 0 else 30 * mm
        col_widths = [label_w, formula_w] + [data_w] * n_years

        # Determine forecast column start
        forecast_start = None
        for i, yd in enumerate(self.data.years):
            if yd.is_forecast:
                forecast_start = i + 2  # +2 for label and formula columns
                break

        t = Table(rows, colWidths=col_widths)
        t.setStyle(get_data_table_style(
            len(rows),
            forecast_col_start=forecast_start,
            total_col_count=len(header)))
        self.elements.append(t)

    def _build_altman_detail(self):
        """Altman Z-Score detail page."""
        self.elements.append(Paragraph(SECTION_ALTMAN, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        latest = self.data.years[-1]

        # Classification box
        z = float(latest.altman.z_score)
        cls = latest.altman.classification
        self.elements.append(Paragraph(
            f"Z-Score: <b>{z:.2f}</b> - {self._altman_status(cls)}",
            self.styles['SubsectionTitle']))
        self.elements.append(Paragraph(
            latest.altman.interpretation_it, self.styles['BodyText_Custom']))
        self.elements.append(Spacer(1, 5 * mm))

        # Components chart
        if 'altman_components' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['altman_components'],
                width=CONTENT_WIDTH * 0.8, height=50 * mm))

        # Components table
        comp = latest.altman.components
        comp_data = [
            ["Componente", "Descrizione", "Valore"],
            ["A", "Capitale Circolante / Totale Attivo", _fmt(comp.A, is_ratio=True)],
            ["B", "Riserve / Totale Attivo", _fmt(comp.B, is_ratio=True)],
            ["C", "EBIT / Totale Attivo", _fmt(comp.C, is_ratio=True)],
            ["D", "Patrimonio Netto / Debiti Totali", _fmt(comp.D, is_ratio=True)],
        ]
        if latest.altman.model_type == "manufacturing":
            comp_data.append(
                ["E", "Fatturato / Totale Attivo", _fmt(comp.E, is_ratio=True)])

        t = Table(comp_data, colWidths=[20 * mm, CONTENT_WIDTH - 55 * mm, 35 * mm])
        t.setStyle(get_data_table_style(len(comp_data)))
        self.elements.append(Spacer(1, 5 * mm))
        self.elements.append(t)

        # Trend chart
        if 'altman_trend' in self.data.chart_images:
            self.elements.append(Spacer(1, 5 * mm))
            self.elements.append(Image(
                self.data.chart_images['altman_trend'],
                width=CONTENT_WIDTH * 0.8, height=50 * mm))

        # Multi-year Z-Score table
        years = [yd.year for yd in self.data.years]
        z_row = ["Z-Score"] + [f"{float(yd.altman.z_score):.2f}" for yd in self.data.years]
        cls_row = ["Classificazione"] + [self._altman_status(yd.altman.classification)
                                          for yd in self.data.years]
        header = [""] + [str(y) for y in years]
        t_data = [header, z_row, cls_row]

        n_cols = len(header)
        col_w = CONTENT_WIDTH / n_cols
        t = Table(t_data, colWidths=[col_w] * n_cols)
        t.setStyle(get_data_table_style(len(t_data)))
        self.elements.append(Spacer(1, 5 * mm))
        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_em_score(self):
        """EM-Score page with rating mapping table."""
        self.elements.append(Paragraph(SECTION_EM_SCORE, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        # Result
        self.elements.append(Paragraph(
            f"EM-Score Rating: <b>{self.data.em_score_rating}</b> - "
            f"{get_em_score_description(self.data.em_score_rating)}",
            self.styles['SubsectionTitle']))
        self.elements.append(Paragraph(
            f"Z-Score utilizzato: {float(self.data.em_score_z):.2f}",
            self.styles['BodyText_Custom']))

        if 'gauge_em' in self.data.chart_images:
            self.elements.append(Spacer(1, 3 * mm))
            self.elements.append(Image(
                self.data.chart_images['gauge_em'],
                width=60 * mm, height=45 * mm))

        # Rating table
        self.elements.append(Spacer(1, 5 * mm))
        self.elements.append(Paragraph(
            "Tabella di conversione Z-Score / Rating",
            self.styles['SubsectionTitle']))

        table_data = [["Z-Score minimo", "Rating", "Descrizione"]]
        for threshold, rating in EM_SCORE_TABLE:
            desc = get_em_score_description(rating)
            z_str = f"{float(threshold):.2f}" if float(threshold) > -100 else "< 1.75"
            table_data.append([z_str, rating, desc])

        t = Table(table_data, colWidths=[35 * mm, 25 * mm, CONTENT_WIDTH - 60 * mm])
        style_cmds = get_data_table_style(len(table_data))
        t.setStyle(style_cmds)

        # Highlight current rating row
        for i, (threshold, rating) in enumerate(EM_SCORE_TABLE):
            if rating == self.data.em_score_rating:
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, i + 1), (-1, i + 1), LIGHT_BLUE),
                    ('FONTNAME', (0, i + 1), (-1, i + 1), 'Helvetica-Bold'),
                ]))
                break

        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_fgpmi_detail(self):
        """FGPMI Rating detail page."""
        self.elements.append(Paragraph(SECTION_FGPMI, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        latest = self.data.years[-1]
        fgpmi = latest.fgpmi

        # Result summary
        self.elements.append(Paragraph(
            f"Rating: <b>{fgpmi.rating_code}</b> - {fgpmi.rating_description}",
            self.styles['SubsectionTitle']))
        self.elements.append(Paragraph(
            f"Punteggio: {fgpmi.total_score}/{fgpmi.max_score} - "
            f"Livello rischio: {fgpmi.risk_level} - "
            f"Settore: {fgpmi.sector_model.title()}",
            self.styles['BodyText_Custom']))

        if fgpmi.revenue_bonus > 0:
            self.elements.append(Paragraph(
                f"Bonus Fatturato: +{fgpmi.revenue_bonus} punti (Fatturato > 500.000 EUR)",
                self.styles['BodyText_Custom']))

        # Indicators chart
        if 'fgpmi_indicators' in self.data.chart_images:
            self.elements.append(Spacer(1, 3 * mm))
            self.elements.append(Image(
                self.data.chart_images['fgpmi_indicators'],
                width=CONTENT_WIDTH * 0.8, height=50 * mm))

        # Indicators table
        self.elements.append(Spacer(1, 5 * mm))
        ind_data = [["Cod.", "Indicatore", "Valore", "Punti", "Max", "%"]]
        for code in ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7']:
            ind = fgpmi.indicators[code]
            ind_data.append([
                ind.code,
                ind.name,
                _fmt(ind.value, is_ratio=True),
                str(ind.points),
                str(ind.max_points),
                f"{float(ind.percentage):.1f}%"
            ])
        # Revenue bonus row
        ind_data.append([
            "", "Bonus Fatturato", "", str(fgpmi.revenue_bonus), "5", ""])
        # Total row
        ind_data.append([
            "", "TOTALE", "", str(fgpmi.total_score), str(fgpmi.max_score),
            f"{(fgpmi.total_score / fgpmi.max_score * 100):.1f}%"])

        col_widths = [12 * mm, 55 * mm, 25 * mm, 18 * mm, 18 * mm,
                      CONTENT_WIDTH - 128 * mm]
        t = Table(ind_data, colWidths=col_widths)
        t.setStyle(get_data_table_style(len(ind_data)))
        # Bold the total row
        t.setStyle(TableStyle([
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, DARK_BLUE),
        ]))
        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_break_even(self):
        """Break Even Point page."""
        self.elements.append(Paragraph(SECTION_BREAK_EVEN, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        if 'break_even' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['break_even'],
                width=CONTENT_WIDTH, height=55 * mm))

        if 'safety_margin' in self.data.chart_images:
            self.elements.append(Spacer(1, 3 * mm))
            self.elements.append(Image(
                self.data.chart_images['safety_margin'],
                width=CONTENT_WIDTH, height=55 * mm))

        self._build_multi_year_ratio_table(
            "break_even",
            ["break_even_revenue", "safety_margin", "operating_leverage",
             "fixed_cost_multiplier", "fixed_costs", "variable_costs",
             "contribution_margin"],
            is_currency=False)

        self.elements.append(PageBreak())

    def _build_cashflow_indices(self):
        """Cash flow summary page."""
        self.elements.append(Paragraph(SECTION_CASHFLOW, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        if 'cashflow_summary' in self.data.chart_images:
            self.elements.append(Image(
                self.data.chart_images['cashflow_summary'],
                width=CONTENT_WIDTH, height=60 * mm))

        # Summary table
        cf_years = [yd for yd in self.data.years if yd.cashflow]
        if cf_years:
            years = [yd.year for yd in cf_years]
            header = ["Voce"] + [str(y) for y in years]
            rows = [header]

            metrics = [
                ("Flusso Operativo", lambda yd: yd.cashflow.operating_activities.total_operating_cashflow),
                ("Flusso Investimenti", lambda yd: yd.cashflow.investing_activities.total_investing_cashflow),
                ("Flusso Finanziamento", lambda yd: yd.cashflow.financing_activities.total_financing_cashflow),
                ("Variazione Netta", lambda yd: yd.cashflow.cash_reconciliation.total_cashflow),
                ("Cassa Iniziale", lambda yd: yd.cashflow.cash_reconciliation.cash_beginning),
                ("Cassa Finale", lambda yd: yd.cashflow.cash_reconciliation.cash_ending),
            ]

            for label, fn in metrics:
                row = [label]
                for yd in cf_years:
                    row.append(_cur_fmt(fn(yd)))
                rows.append(row)

            n_cols = len(header)
            label_w = 50 * mm
            data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else 30 * mm
            col_widths = [label_w] + [data_w] * (n_cols - 1)

            t = Table(rows, colWidths=col_widths)
            t.setStyle(get_data_table_style(len(rows)))
            self.elements.append(Spacer(1, 5 * mm))
            self.elements.append(t)

        self.elements.append(PageBreak())

    def _build_appendix_bs(self):
        """Appendix: Balance Sheet table."""
        self.elements.append(Paragraph(
            f"APPENDICE - {SECTION_BALANCE_SHEET}", self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        years = [yd.year for yd in self.data.years]
        header = ["Voce"] + [str(y) for y in years]
        rows = [header]

        # Assets section
        rows.append(["ATTIVO"] + [""] * len(years))
        for code in ["sp01", "sp02", "sp03", "sp04", "sp05", "sp06",
                      "sp07", "sp08", "sp09", "sp10"]:
            label = BS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = getattr(yd.bs, f"{code}_{'crediti_soci' if code == 'sp01' else ''}", None)
                # Use the attribute lookup approach
                val = self._get_bs_value(yd.bs, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # Total Assets
        row = [BS_AGGREGATE_LABELS["total_assets"]]
        for yd in self.data.years:
            row.append(_cur_fmt(yd.bs.total_assets))
        rows.append(row)

        # Liabilities section
        rows.append(["PASSIVO"] + [""] * len(years))
        for code in ["sp11", "sp12", "sp13", "sp14", "sp15", "sp16", "sp17", "sp18"]:
            label = BS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = self._get_bs_value(yd.bs, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # Total Liabilities
        row = [BS_AGGREGATE_LABELS["total_liabilities"]]
        for yd in self.data.years:
            row.append(_cur_fmt(yd.bs.total_liabilities))
        rows.append(row)

        n_cols = len(header)
        label_w = 55 * mm
        data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else 30 * mm
        col_widths = [label_w] + [data_w] * (n_cols - 1)

        t = Table(rows, colWidths=col_widths)
        style = get_data_table_style(len(rows))
        t.setStyle(style)

        # Bold section headers and totals
        for i, row in enumerate(rows):
            if row[0] in ("ATTIVO", "PASSIVO",
                          BS_AGGREGATE_LABELS["total_assets"],
                          BS_AGGREGATE_LABELS["total_liabilities"]):
                t.setStyle(TableStyle([
                    ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, i), (-1, i), LIGHT_BLUE),
                ]))

        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_appendix_is(self):
        """Appendix: Income Statement table."""
        self.elements.append(Paragraph(
            f"APPENDICE - {SECTION_INCOME_STATEMENT}", self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        years = [yd.year for yd in self.data.years]
        header = ["Voce"] + [str(y) for y in years]
        rows = [header]

        # Revenue section
        for code in ["ce01", "ce02", "ce03", "ce03a", "ce04"]:
            label = IS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = self._get_is_value(yd.inc, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # Production Value
        row = [IS_AGGREGATE_LABELS["production_value"]]
        for yd in self.data.years:
            row.append(_cur_fmt(yd.inc.production_value))
        rows.append(row)

        # Costs section
        for code in ["ce05", "ce06", "ce07", "ce08", "ce09", "ce10",
                      "ce11", "ce11b", "ce12"]:
            label = IS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = self._get_is_value(yd.inc, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # EBITDA & EBIT
        for agg_key in ["ebitda", "ebit"]:
            row = [IS_AGGREGATE_LABELS[agg_key]]
            for yd in self.data.years:
                row.append(_cur_fmt(getattr(yd.inc, agg_key)))
            rows.append(row)

        # Financial section
        for code in ["ce13", "ce14", "ce15", "ce16", "ce17"]:
            label = IS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = self._get_is_value(yd.inc, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # Extraordinary
        for code in ["ce18", "ce19"]:
            label = IS_LABELS.get(code, code)
            row = [label]
            for yd in self.data.years:
                val = self._get_is_value(yd.inc, code)
                row.append(_cur_fmt(val))
            rows.append(row)

        # Taxes and Net Profit
        row = [IS_LABELS["ce20"]]
        for yd in self.data.years:
            row.append(_cur_fmt(yd.inc.ce20_imposte))
        rows.append(row)

        row = [IS_AGGREGATE_LABELS["net_profit"]]
        for yd in self.data.years:
            row.append(_cur_fmt(yd.inc.net_profit))
        rows.append(row)

        n_cols = len(header)
        label_w = 55 * mm
        data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else 30 * mm
        col_widths = [label_w] + [data_w] * (n_cols - 1)

        t = Table(rows, colWidths=col_widths)
        t.setStyle(get_data_table_style(len(rows)))

        # Bold aggregate rows
        for i, row in enumerate(rows):
            if row[0] in (IS_AGGREGATE_LABELS["production_value"],
                          IS_AGGREGATE_LABELS["ebitda"],
                          IS_AGGREGATE_LABELS["ebit"],
                          IS_AGGREGATE_LABELS["net_profit"]):
                t.setStyle(TableStyle([
                    ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, i), (-1, i), LIGHT_BLUE),
                ]))

        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_appendix_reclassified(self):
        """Appendix: Reclassified Balance Sheet."""
        self.elements.append(Paragraph(
            f"APPENDICE - {SECTION_RECLASSIFIED_BS}", self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        years = [yd.year for yd in self.data.years]
        header = ["Voce"] + [str(y) for y in years]
        rows = [header]

        # Reclassified structure
        reclass_items = [
            ("fixed_assets", True), ("sp02", False), ("sp03", False), ("sp04", False),
            ("current_assets", True), ("sp05", False), ("sp06", False), ("sp07", False),
            ("sp08", False), ("sp09", False),
            ("sp10", False), ("sp01", False),
            ("total_assets", True),
            ("total_equity", True), ("sp11", False), ("sp12", False), ("sp13", False),
            ("sp14", False), ("sp15", False),
            ("sp17", False), ("sp16", False), ("sp18", False),
            ("total_liabilities", True),
        ]

        for key, is_aggregate in reclass_items:
            label = RECLASSIFIED_BS_LABELS.get(key, key)
            row = [label]
            for yd in self.data.years:
                if is_aggregate:
                    val = getattr(yd.bs, key, Decimal(0))
                else:
                    val = self._get_bs_value(yd.bs, key)
                row.append(_cur_fmt(val))
            rows.append(row)

        n_cols = len(header)
        label_w = 60 * mm
        data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else 30 * mm
        col_widths = [label_w] + [data_w] * (n_cols - 1)

        t = Table(rows, colWidths=col_widths)
        t.setStyle(get_data_table_style(len(rows)))

        # Bold aggregate rows
        for i, (key, is_agg) in enumerate(reclass_items):
            if is_agg:
                t.setStyle(TableStyle([
                    ('FONTNAME', (0, i + 1), (-1, i + 1), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, i + 1), (-1, i + 1), LIGHT_BLUE),
                ]))

        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_appendix_cashflow(self):
        """Appendix: Cash Flow Statement."""
        cf_years = [yd for yd in self.data.years if yd.cashflow]
        if not cf_years:
            return

        self.elements.append(Paragraph(
            f"APPENDICE - {SECTION_CASHFLOW_STATEMENT}", self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 3 * mm))

        years = [yd.year for yd in cf_years]
        header = ["Voce"] + [str(y) for y in years]
        rows = [header]

        # Operating Activities
        rows.append(["A. ATTIVITA OPERATIVA"] + [""] * len(years))

        op_items = [
            ("Utile Netto", lambda cf: cf.operating_activities.start.net_profit),
            ("+ Imposte", lambda cf: cf.operating_activities.start.income_taxes),
            ("+ Oneri/Proventi Finanziari", lambda cf: cf.operating_activities.start.interest_expense_income),
            ("= Utile prima rettifiche", lambda cf: cf.operating_activities.start.profit_before_adjustments),
            ("+ Ammortamenti", lambda cf: cf.operating_activities.non_cash_adjustments.depreciation_amortization),
            ("+ Accantonamenti", lambda cf: cf.operating_activities.non_cash_adjustments.provisions),
            ("= Flusso prima var. CCN", lambda cf: cf.operating_activities.cashflow_before_wc),
            ("Var. Rimanenze", lambda cf: cf.operating_activities.working_capital_changes.delta_inventory),
            ("Var. Crediti", lambda cf: cf.operating_activities.working_capital_changes.delta_receivables),
            ("Var. Debiti", lambda cf: cf.operating_activities.working_capital_changes.delta_payables),
            ("Altre variazioni", lambda cf: cf.operating_activities.working_capital_changes.other_wc_changes),
            ("Interessi pagati/incassati", lambda cf: cf.operating_activities.cash_adjustments.interest_paid_received),
            ("Imposte pagate", lambda cf: cf.operating_activities.cash_adjustments.taxes_paid),
            ("TOTALE FLUSSO OPERATIVO", lambda cf: cf.operating_activities.total_operating_cashflow),
        ]

        for label, fn in op_items:
            row = [label]
            for yd in cf_years:
                row.append(_cur_fmt(fn(yd.cashflow)))
            rows.append(row)

        # Investing Activities
        rows.append(["B. ATTIVITA DI INVESTIMENTO"] + [""] * len(years))
        inv_items = [
            ("Investimenti materiali", lambda cf: cf.investing_activities.tangible_assets.net),
            ("Investimenti immateriali", lambda cf: cf.investing_activities.intangible_assets.net),
            ("Investimenti finanziari", lambda cf: cf.investing_activities.financial_assets.net),
            ("TOTALE FLUSSO INVESTIMENTI", lambda cf: cf.investing_activities.total_investing_cashflow),
        ]
        for label, fn in inv_items:
            row = [label]
            for yd in cf_years:
                row.append(_cur_fmt(fn(yd.cashflow)))
            rows.append(row)

        # Financing Activities
        rows.append(["C. ATTIVITA DI FINANZIAMENTO"] + [""] * len(years))
        fin_items = [
            ("Mezzi di terzi (netto)", lambda cf: cf.financing_activities.third_party_funds.net),
            ("Mezzi propri (netto)", lambda cf: cf.financing_activities.own_funds.net),
            ("TOTALE FLUSSO FINANZIAMENTO", lambda cf: cf.financing_activities.total_financing_cashflow),
        ]
        for label, fn in fin_items:
            row = [label]
            for yd in cf_years:
                row.append(_cur_fmt(fn(yd.cashflow)))
            rows.append(row)

        # Reconciliation
        rows.append(["RICONCILIAZIONE"] + [""] * len(years))
        recon_items = [
            ("Variazione netta di cassa", lambda cf: cf.cash_reconciliation.total_cashflow),
            ("Cassa iniziale", lambda cf: cf.cash_reconciliation.cash_beginning),
            ("Cassa finale", lambda cf: cf.cash_reconciliation.cash_ending),
        ]
        for label, fn in recon_items:
            row = [label]
            for yd in cf_years:
                row.append(_cur_fmt(fn(yd.cashflow)))
            rows.append(row)

        n_cols = len(header)
        label_w = 60 * mm
        data_w = (CONTENT_WIDTH - label_w) / (n_cols - 1) if n_cols > 1 else 30 * mm
        col_widths = [label_w] + [data_w] * (n_cols - 1)

        t = Table(rows, colWidths=col_widths)
        t.setStyle(get_data_table_style(len(rows)))

        # Bold section headers and totals
        bold_labels = {
            "A. ATTIVITA OPERATIVA", "B. ATTIVITA DI INVESTIMENTO",
            "C. ATTIVITA DI FINANZIAMENTO", "RICONCILIAZIONE",
            "TOTALE FLUSSO OPERATIVO", "TOTALE FLUSSO INVESTIMENTI",
            "TOTALE FLUSSO FINANZIAMENTO",
            "= Utile prima rettifiche", "= Flusso prima var. CCN",
        }
        section_labels = {
            "A. ATTIVITA OPERATIVA", "B. ATTIVITA DI INVESTIMENTO",
            "C. ATTIVITA DI FINANZIAMENTO", "RICONCILIAZIONE",
        }
        for i, row in enumerate(rows):
            if row[0] in bold_labels:
                t.setStyle(TableStyle([
                    ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                ]))
            if row[0] in section_labels:
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), LIGHT_BLUE),
                ]))

        self.elements.append(t)
        self.elements.append(PageBreak())

    def _build_notes(self):
        """Notes / methodology page."""
        self.elements.append(Paragraph(SECTION_NOTES, self.styles['SectionTitle']))
        self.elements.append(Spacer(1, 5 * mm))

        for para in NOTES_TEXT.split('\n\n'):
            para = para.strip()
            if para:
                self.elements.append(Paragraph(para, self.styles['BodyText_Custom']))
                self.elements.append(Spacer(1, 2 * mm))

    # ===== HELPER METHODS =====

    def _get_bs_value(self, bs, code: str):
        """Get balance sheet value by code (sp01-sp18)."""
        field_map = {
            "sp01": "sp01_crediti_soci",
            "sp02": "sp02_immob_immateriali",
            "sp03": "sp03_immob_materiali",
            "sp04": "sp04_immob_finanziarie",
            "sp05": "sp05_rimanenze",
            "sp06": "sp06_crediti_breve",
            "sp07": "sp07_crediti_lungo",
            "sp08": "sp08_attivita_finanziarie",
            "sp09": "sp09_disponibilita_liquide",
            "sp10": "sp10_ratei_risconti_attivi",
            "sp11": "sp11_capitale",
            "sp12": "sp12_riserve",
            "sp13": "sp13_utile_perdita",
            "sp14": "sp14_fondi_rischi",
            "sp15": "sp15_tfr",
            "sp16": "sp16_debiti_breve",
            "sp17": "sp17_debiti_lungo",
            "sp18": "sp18_ratei_risconti_passivi",
        }
        attr = field_map.get(code)
        if attr:
            return getattr(bs, attr, Decimal(0))
        return Decimal(0)

    def _get_is_value(self, inc, code: str):
        """Get income statement value by code (ce01-ce20)."""
        field_map = {
            "ce01": "ce01_ricavi_vendite",
            "ce02": "ce02_variazioni_rimanenze",
            "ce03": "ce03_lavori_interni",
            "ce03a": "ce03a_incrementi_immobilizzazioni",
            "ce04": "ce04_altri_ricavi",
            "ce05": "ce05_materie_prime",
            "ce06": "ce06_servizi",
            "ce07": "ce07_godimento_beni",
            "ce08": "ce08_costi_personale",
            "ce09": "ce09_ammortamenti",
            "ce10": "ce10_var_rimanenze_mat_prime",
            "ce11": "ce11_accantonamenti",
            "ce11b": "ce11b_altri_accantonamenti",
            "ce12": "ce12_oneri_diversi",
            "ce13": "ce13_proventi_partecipazioni",
            "ce14": "ce14_altri_proventi_finanziari",
            "ce15": "ce15_oneri_finanziari",
            "ce16": "ce16_utili_perdite_cambi",
            "ce17": "ce17_rettifiche_attivita_fin",
            "ce18": "ce18_proventi_straordinari",
            "ce19": "ce19_oneri_straordinari",
            "ce20": "ce20_imposte",
        }
        attr = field_map.get(code)
        if attr:
            return getattr(inc, attr, Decimal(0))
        return Decimal(0)
