"""
Matplotlib chart generators for PDF reports.
Each function returns a BytesIO PNG image.
"""
import io
import math
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

from pdf_service.styles import (
    CHART_BLUE, CHART_GREEN, CHART_RED, CHART_YELLOW,
    CHART_ORANGE, CHART_PURPLE, CHART_TEAL, CHART_GRAY,
    CHART_LIGHT_BLUE, CHART_LIGHT_GREEN,
)

# Global matplotlib settings
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Helvetica', 'Arial'],
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.labelsize': 9,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
})

DPI = 150


def _fig_to_bytes(fig, dpi=DPI) -> io.BytesIO:
    """Convert matplotlib figure to PNG BytesIO."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf


def _fmt_number(value, decimals=2) -> str:
    """Format number with Italian locale (dot as thousands separator)."""
    if isinstance(value, Decimal):
        value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.{decimals}f}M".replace(",", ".")
    elif abs(value) >= 1_000:
        return f"{value / 1_000:,.{decimals}f}K".replace(",", ".")
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gauge_chart(value: float, min_val: float, max_val: float,
                label: str, thresholds: List[Tuple[float, str, str]],
                subtitle: str = "", size: Tuple[float, float] = (3.5, 2.5)
                ) -> io.BytesIO:
    """
    Create a semicircular gauge chart.

    Args:
        value: Current value to display
        min_val: Minimum scale value
        max_val: Maximum scale value
        label: Main label text
        thresholds: List of (threshold_value, color, zone_label)
        subtitle: Additional text below the value
        size: Figure size in inches
    """
    fig, ax = plt.subplots(figsize=size, subplot_kw={'projection': 'polar'})

    # Gauge spans from 180 to 0 degrees (left to right semicircle)
    theta_min = math.pi  # 180 degrees
    theta_max = 0  # 0 degrees

    # Draw colored zones
    prev_theta = theta_min
    for threshold_val, color, zone_label in thresholds:
        # Map value to angle
        frac = min(max((threshold_val - min_val) / (max_val - min_val), 0), 1)
        theta = theta_min - frac * (theta_min - theta_max)
        theta_range = np.linspace(prev_theta, theta, 50)
        ax.fill_between(theta_range, 0.6, 1.0, color=color, alpha=0.3)
        prev_theta = theta

    # Fill remaining
    if prev_theta > theta_max:
        theta_range = np.linspace(prev_theta, theta_max, 50)
        ax.fill_between(theta_range, 0.6, 1.0, color=thresholds[-1][1], alpha=0.3)

    # Draw needle
    frac = min(max((value - min_val) / (max_val - min_val), 0), 1)
    needle_theta = theta_min - frac * (theta_min - theta_max)
    ax.plot([needle_theta, needle_theta], [0, 0.9], color='#1a365d',
            linewidth=2.5, zorder=5)
    ax.scatter([needle_theta], [0.9], color='#1a365d', s=30, zorder=5)

    # Center dot
    ax.scatter([0], [0], color='#1a365d', s=50, zorder=6)

    # Configure polar plot as semicircle
    ax.set_ylim(0, 1.2)
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines['polar'].set_visible(False)
    ax.grid(False)

    # Add value text
    if abs(value) < 100:
        val_text = f"{value:.2f}"
    else:
        val_text = f"{value:,.0f}".replace(",", ".")
    ax.text(math.pi / 2, 0.3, val_text, ha='center', va='center',
            fontsize=16, fontweight='bold', color='#1a365d')

    # Add subtitle
    if subtitle:
        ax.text(math.pi / 2, 0.05, subtitle, ha='center', va='center',
                fontsize=8, color='#718096')

    fig.suptitle(label, fontsize=10, fontweight='bold', color='#1a365d', y=0.05)
    fig.subplots_adjust(top=0.95, bottom=0.15)

    return _fig_to_bytes(fig)


def stacked_bar_chart(years: List[int], data_series: List[Dict],
                      title: str, ylabel: str = "%",
                      size: Tuple[float, float] = (7, 4),
                      show_values: bool = True) -> io.BytesIO:
    """
    Create a stacked bar chart for composition analysis.

    Args:
        years: List of years for x-axis
        data_series: List of dicts with 'label', 'values', and 'color'
        title: Chart title
        ylabel: Y-axis label
        size: Figure size
        show_values: Show value labels on bars
    """
    fig, ax = plt.subplots(figsize=size)

    x = np.arange(len(years))
    bar_width = 0.6
    bottom = np.zeros(len(years))

    for series in data_series:
        values = [float(v) for v in series['values']]
        bars = ax.bar(x, values, bar_width, bottom=bottom,
                      label=series['label'], color=series['color'], alpha=0.85)
        if show_values:
            for i, (bar, val) in enumerate(zip(bars, values)):
                if abs(val) > 3:  # Only show label if segment is visible
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bottom[i] + val / 2,
                            f"{val:.1f}%", ha='center', va='center',
                            fontsize=7, color='white', fontweight='bold')
        bottom += np.array(values)

    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11, fontweight='bold', color='#1a365d')
    ax.legend(loc='upper left', fontsize=7, framealpha=0.9)
    ax.set_ylim(0, 105)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    return _fig_to_bytes(fig)


def line_chart(years: List[int], data_series: List[Dict],
               title: str, ylabel: str = "",
               size: Tuple[float, float] = (7, 3.5),
               show_values: bool = True,
               format_pct: bool = False,
               format_currency: bool = False,
               y_zero_line: bool = False) -> io.BytesIO:
    """
    Create a line chart with multiple series.

    Args:
        years: List of years for x-axis
        data_series: List of dicts with 'label', 'values', 'color'
        title: Chart title
        ylabel: Y-axis label
        size: Figure size
        show_values: Annotate values on data points
        format_pct: Format values as percentages
        format_currency: Format values as currency
        y_zero_line: Draw horizontal line at y=0
    """
    fig, ax = plt.subplots(figsize=size)

    for series in data_series:
        values = [float(v) for v in series['values']]
        line_style = series.get('linestyle', '-')
        marker = series.get('marker', 'o')
        ax.plot(years, values, marker=marker, label=series['label'],
                color=series['color'], linewidth=2, markersize=5,
                linestyle=line_style)

        if show_values:
            for x, y in zip(years, values):
                if format_pct:
                    txt = f"{y:.1f}%"
                elif format_currency:
                    txt = _fmt_number(y, 0)
                else:
                    txt = f"{y:.2f}"
                ax.annotate(txt, (x, y), textcoords="offset points",
                            xytext=(0, 8), ha='center', fontsize=7,
                            color=series['color'])

    if y_zero_line:
        ax.axhline(y=0, color='gray', linewidth=0.5, linestyle='-')

    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11, fontweight='bold', color='#1a365d')
    if len(data_series) > 1:
        ax.legend(loc='best', fontsize=7, framealpha=0.9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    return _fig_to_bytes(fig)


def waterfall_chart(labels: List[str], values: List[float],
                    title: str, size: Tuple[float, float] = (7, 4)
                    ) -> io.BytesIO:
    """
    Create a waterfall chart for income margin breakdown.

    Args:
        labels: Category labels
        values: Values (positive = increase, negative = decrease)
        title: Chart title
        size: Figure size
    """
    fig, ax = plt.subplots(figsize=size)

    n = len(labels)
    running = 0
    bottoms = []
    bar_colors = []

    for i, val in enumerate(values):
        if i == 0 or i == n - 1:
            # First and last bars start from 0
            bottoms.append(0)
            bar_colors.append(CHART_BLUE)
        else:
            if val >= 0:
                bottoms.append(running)
                bar_colors.append(CHART_GREEN)
            else:
                bottoms.append(running + val)
                bar_colors.append(CHART_RED)
        running += val if i < n - 1 else 0

    x = np.arange(n)
    display_values = [abs(v) if i > 0 and i < n - 1 else v
                      for i, v in enumerate(values)]

    bars = ax.bar(x, [abs(v) for v in values], bottom=bottoms,
                  color=bar_colors, alpha=0.85, width=0.6)

    # Connector lines
    for i in range(n - 1):
        top = bottoms[i] + abs(values[i])
        ax.plot([i + 0.3, i + 0.7], [top, top],
                color='gray', linewidth=0.5, linestyle='--')

    # Value labels
    for i, (bar, val) in enumerate(zip(bars, values)):
        y_pos = bottoms[i] + abs(val) / 2
        txt = _fmt_number(val, 0)
        ax.text(bar.get_x() + bar.get_width() / 2, y_pos, txt,
                ha='center', va='center', fontsize=7, fontweight='bold',
                color='white' if abs(val) > 0 else CHART_GRAY)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
    ax.set_title(title, fontsize=11, fontweight='bold', color='#1a365d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    return _fig_to_bytes(fig)


def bar_chart(labels: List[str], values: List[float],
              title: str, colors: Optional[List[str]] = None,
              ylabel: str = "", horizontal: bool = False,
              size: Tuple[float, float] = (7, 3.5)) -> io.BytesIO:
    """
    Create a simple bar chart.

    Args:
        labels: Category labels
        values: Values
        title: Chart title
        colors: Optional list of colors per bar
        ylabel: Y-axis label
        horizontal: If True, create horizontal bars
        size: Figure size
    """
    fig, ax = plt.subplots(figsize=size)

    if colors is None:
        colors = [CHART_BLUE] * len(values)

    x = np.arange(len(labels))

    if horizontal:
        bars = ax.barh(x, values, color=colors, alpha=0.85, height=0.6)
        ax.set_yticks(x)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel(ylabel)
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.01 * max(abs(v) for v in values),
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.4f}", va='center', fontsize=7)
    else:
        bars = ax.bar(x, values, color=colors, alpha=0.85, width=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel(ylabel)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height(), f"{val:.4f}",
                    ha='center', va='bottom', fontsize=7)

    ax.set_title(title, fontsize=11, fontweight='bold', color='#1a365d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    return _fig_to_bytes(fig)


def dual_axis_chart(years: List[int],
                    series1: Dict, series2: Dict,
                    title: str,
                    ylabel1: str = "", ylabel2: str = "",
                    size: Tuple[float, float] = (7, 3.5)) -> io.BytesIO:
    """
    Create a chart with two Y-axes (e.g., BEP revenue vs safety margin).

    Args:
        years: X-axis years
        series1: Dict with 'label', 'values', 'color' for left axis
        series2: Dict with 'label', 'values', 'color' for right axis
        title: Chart title
        ylabel1: Left Y-axis label
        ylabel2: Right Y-axis label
        size: Figure size
    """
    fig, ax1 = plt.subplots(figsize=size)
    ax2 = ax1.twinx()

    vals1 = [float(v) for v in series1['values']]
    vals2 = [float(v) for v in series2['values']]

    ax1.bar(years, vals1, color=series1['color'], alpha=0.6, width=0.6,
            label=series1['label'])
    ax2.plot(years, vals2, color=series2['color'], marker='o',
             linewidth=2, label=series2['label'])

    ax1.set_ylabel(ylabel1, color=series1['color'])
    ax2.set_ylabel(ylabel2, color=series2['color'])
    ax1.set_xticks(years)

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left',
               fontsize=7, framealpha=0.9)

    ax1.set_title(title, fontsize=11, fontweight='bold', color='#1a365d')
    ax1.spines['top'].set_visible(False)

    fig.tight_layout()
    return _fig_to_bytes(fig)
