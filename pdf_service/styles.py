"""
PDF styling: colors, fonts, page dimensions, and ReportLab table styles.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import TableStyle

# Page dimensions
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 18 * mm
MARGIN_RIGHT = 18 * mm
MARGIN_TOP = 22 * mm
MARGIN_BOTTOM = 22 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

# Color palette (professional blues/grays matching reference PDF)
DARK_BLUE = colors.HexColor("#1a365d")
MEDIUM_BLUE = colors.HexColor("#2b6cb0")
LIGHT_BLUE = colors.HexColor("#bee3f8")
VERY_LIGHT_BLUE = colors.HexColor("#ebf8ff")
DARK_GRAY = colors.HexColor("#2d3748")
MEDIUM_GRAY = colors.HexColor("#718096")
LIGHT_GRAY = colors.HexColor("#e2e8f0")
VERY_LIGHT_GRAY = colors.HexColor("#f7fafc")
WHITE = colors.white
BLACK = colors.black

# Status colors
GREEN = colors.HexColor("#38a169")
LIGHT_GREEN = colors.HexColor("#c6f6d5")
YELLOW = colors.HexColor("#d69e2e")
LIGHT_YELLOW = colors.HexColor("#fefcbf")
RED = colors.HexColor("#e53e3e")
LIGHT_RED = colors.HexColor("#fed7d7")
ORANGE = colors.HexColor("#dd6b20")

# Chart colors (Matplotlib-compatible hex strings)
CHART_BLUE = "#2b6cb0"
CHART_GREEN = "#38a169"
CHART_RED = "#e53e3e"
CHART_YELLOW = "#d69e2e"
CHART_ORANGE = "#dd6b20"
CHART_PURPLE = "#805ad5"
CHART_TEAL = "#319795"
CHART_GRAY = "#718096"
CHART_LIGHT_BLUE = "#63b3ed"
CHART_LIGHT_GREEN = "#68d391"

# Forecast column background
FORECAST_BG = colors.HexColor("#fffff0")

# Font sizes
FONT_TITLE = 20
FONT_SUBTITLE = 14
FONT_SECTION = 13
FONT_SUBSECTION = 11
FONT_BODY = 9
FONT_TABLE = 8
FONT_TABLE_HEADER = 8
FONT_SMALL = 7
FONT_FOOTER = 7


def get_styles():
    """Get custom paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='CoverTitle',
        fontName='Helvetica-Bold',
        fontSize=FONT_TITLE,
        textColor=DARK_BLUE,
        alignment=TA_CENTER,
        spaceAfter=6 * mm,
    ))

    styles.add(ParagraphStyle(
        name='CoverSubtitle',
        fontName='Helvetica',
        fontSize=FONT_SUBTITLE,
        textColor=MEDIUM_BLUE,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    ))

    styles.add(ParagraphStyle(
        name='SectionTitle',
        fontName='Helvetica-Bold',
        fontSize=FONT_SECTION,
        textColor=DARK_BLUE,
        spaceBefore=8 * mm,
        spaceAfter=4 * mm,
        borderWidth=0,
        borderColor=MEDIUM_BLUE,
        borderPadding=2,
    ))

    styles.add(ParagraphStyle(
        name='SubsectionTitle',
        fontName='Helvetica-Bold',
        fontSize=FONT_SUBSECTION,
        textColor=MEDIUM_BLUE,
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
    ))

    styles.add(ParagraphStyle(
        name='BodyText_Custom',
        fontName='Helvetica',
        fontSize=FONT_BODY,
        textColor=DARK_GRAY,
        alignment=TA_JUSTIFY,
        spaceBefore=2 * mm,
        spaceAfter=2 * mm,
        leading=14,
    ))

    styles.add(ParagraphStyle(
        name='SmallText',
        fontName='Helvetica',
        fontSize=FONT_SMALL,
        textColor=MEDIUM_GRAY,
        alignment=TA_LEFT,
        spaceBefore=1 * mm,
        spaceAfter=1 * mm,
    ))

    styles.add(ParagraphStyle(
        name='TableHeader',
        fontName='Helvetica-Bold',
        fontSize=FONT_TABLE_HEADER,
        textColor=WHITE,
        alignment=TA_CENTER,
    ))

    styles.add(ParagraphStyle(
        name='TableCell',
        fontName='Helvetica',
        fontSize=FONT_TABLE,
        textColor=DARK_GRAY,
        alignment=TA_RIGHT,
    ))

    styles.add(ParagraphStyle(
        name='TableCellLeft',
        fontName='Helvetica',
        fontSize=FONT_TABLE,
        textColor=DARK_GRAY,
        alignment=TA_LEFT,
    ))

    styles.add(ParagraphStyle(
        name='TableCellBold',
        fontName='Helvetica-Bold',
        fontSize=FONT_TABLE,
        textColor=DARK_GRAY,
        alignment=TA_RIGHT,
    ))

    styles.add(ParagraphStyle(
        name='FooterText',
        fontName='Helvetica',
        fontSize=FONT_FOOTER,
        textColor=MEDIUM_GRAY,
        alignment=TA_CENTER,
    ))

    styles.add(ParagraphStyle(
        name='DashboardValue',
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=DARK_BLUE,
        alignment=TA_CENTER,
    ))

    styles.add(ParagraphStyle(
        name='DashboardLabel',
        fontName='Helvetica',
        fontSize=FONT_BODY,
        textColor=MEDIUM_GRAY,
        alignment=TA_CENTER,
    ))

    return styles


def get_data_table_style(num_rows, header_rows=1, forecast_col_start=None,
                         total_col_count=None):
    """
    Get standard table style for data tables.

    Args:
        num_rows: Total number of rows including header
        header_rows: Number of header rows (default 1)
        forecast_col_start: Column index where forecast data starts (for highlighting)
        total_col_count: Total number of columns
    """
    style_commands = [
        # Header
        ('BACKGROUND', (0, 0), (-1, header_rows - 1), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), WHITE),
        ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, header_rows - 1), FONT_TABLE_HEADER),
        ('ALIGN', (0, 0), (-1, header_rows - 1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, header_rows - 1), 4),
        ('TOPPADDING', (0, 0), (-1, header_rows - 1), 4),

        # Body
        ('FONTNAME', (0, header_rows), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, header_rows), (-1, -1), FONT_TABLE),
        ('TEXTCOLOR', (0, header_rows), (-1, -1), DARK_GRAY),
        ('ALIGN', (1, header_rows), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, header_rows), (0, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, header_rows), (-1, -1), 3),
        ('TOPPADDING', (0, header_rows), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),

        # Alternating row colors
        ('ROWBACKGROUNDS', (0, header_rows), (-1, -1),
         [WHITE, VERY_LIGHT_GRAY]),

        # Grid
        ('LINEBELOW', (0, header_rows - 1), (-1, header_rows - 1), 1, DARK_BLUE),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, MEDIUM_GRAY),
        ('LINEAFTER', (0, 0), (-2, -1), 0.25, LIGHT_GRAY),
    ]

    # Highlight forecast columns
    if forecast_col_start is not None and total_col_count is not None:
        for col in range(forecast_col_start, total_col_count):
            style_commands.append(
                ('BACKGROUND', (col, header_rows), (col, -1), FORECAST_BG)
            )

    return TableStyle(style_commands)


def get_category_header_style():
    """Style for ratio category header rows."""
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), DARK_BLUE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), FONT_TABLE),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('SPAN', (0, 0), (-1, 0)),
    ])


def get_summary_card_style():
    """Style for dashboard summary cards (3-column layout)."""
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WHITE),
        ('BOX', (0, 0), (-1, -1), 1, MEDIUM_BLUE),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ])
