#import "@preview/primaviz:0.10.0": multi-line-chart, grouped-bar-chart, themes
#import "common.typ": palette
// Deliberately preserve nulls/negative values in this candidate probe.
// A compile failure is a measured incompatibility, not replaced with zero.
#let render(chart, gray: false) = {
  let data = (labels: chart.categories.map(str), series: chart.series.map(s => (
    name: s.label, values: s.values.map(v => if v == none { none } else { float(v) })
  )))
  let annotations = if chart.id == "coverage" {
    ((type: "h-line", value: 1, dash: "dashed", label: "DSCR 1,00"),)
  } else { none }
  let theme = (palette: palette(gray: gray), show-grid: true, base-size: 7pt, base-gap: 4pt)
  if chart.id in ("income_results", "cashflows") {
    grouped-bar-chart(data, width: 420pt, height: 130pt, show-legend: false, theme: theme)
  } else {
    multi-line-chart(data, width: 420pt, height: 130pt, show-legend: false, annotations: annotations, theme: theme)
  }
}
