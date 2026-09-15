"""Verified native chart bundle and fixed dimensions for the future page planner."""
from dataclasses import dataclass
from decimal import Decimal
import json
import re

from .runtime import RendererLimits, RendererUnavailable, TemplateBundle


@dataclass(frozen=True)
class ChartDimensions:
    version: str
    width_mm: Decimal
    height_mm: Decimal
    plot_height_mm: Decimal
    legend_height_mm: Decimal
    max_series: int


class ChartTemplateBundle(TemplateBundle):
    """Internal preview entrypoint; never selected by report content or a URL."""
    def read(self, limits: RendererLimits):
        version, _, files = super().read(limits)
        entry = 'charts-preview.typ'
        if entry not in files:
            raise RendererUnavailable()
        dimensions = self._dimensions(files)
        return f'{version}+{dimensions.version}', entry, files

    def dimensions(self, limits: RendererLimits | None = None) -> ChartDimensions:
        _, _, files = super().read(limits or RendererLimits())
        return self._dimensions(files)

    @staticmethod
    def _dimensions(files):
        try:
            raw = json.loads(files['chart-layout.json'])
            fields = ('width_mm', 'height_mm', 'plot_height_mm', 'legend_height_mm')
            if (set(raw) != {'version', *fields, 'table_font_pt', 'axis_font_pt', 'bars', 'max_series'}
                    or any(not isinstance(raw[k], str) or not re.fullmatch(r'\d+(?:\.\d+)?', raw[k]) for k in fields)
                    or type(raw['max_series']) is not int or raw['max_series'] != 4
                    or not isinstance(raw['bars'], list) or len(set(raw['bars'])) != len(raw['bars'])
                    or any(not isinstance(v, str) or not v for v in raw['bars'])
                    or raw['table_font_pt'] != '8' or raw['axis_font_pt'] != '7'):
                raise ValueError()
            values = {k: Decimal(raw[k]) for k in ('width_mm', 'height_mm', 'plot_height_mm', 'legend_height_mm')}
            # Geometry is immutable for this component version: the page planner
            # must not accept a newly signed bundle with a different footprint.
            if (raw['version'] != 'native-charts-1'
                    or tuple(values[k] for k in fields) != tuple(map(Decimal, ('178', '94', '62', '32')))):
                raise ValueError()
            return ChartDimensions(raw['version'], **values, max_series=raw['max_series'])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise RendererUnavailable() from None
