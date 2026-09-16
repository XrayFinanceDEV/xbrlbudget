// Development proof of M2-03 components; the final dossier follows later.
#import "base.typ": dossier, cover, plex, navy, muted
#import "charts.typ": chart-component, value-table, references
#import "chart-format.typ": precision
#let report = json("model.json")
#let options = json("options.json")
#show: body => dossier(report, options, body)
#cover(report)
#for chart in report.chart_series {
  pagebreak()
  plex(8pt, weight: 600, fill: muted)[INDICATORI · PROIEZIONI DEL PIANO]
  v(3mm)
  plex(16pt, weight: 600, fill: navy, chart.title)
  v(4mm)
  chart-component(chart, gray: options.grayscale, indicators: report.indicator_catalog)
  v(2mm)
  value-table(chart)
  v(3mm)
  plex(7.5pt, fill: muted)[Valori tabellari arrotondati a #precision(chart.unit) decimali.
    n.d. = dato non disponibile; la linea si interrompe sui dati mancanti.]
  if "indicator_ids" in chart {
    if chart.indicator_ids.len() == 0 {
      v(2mm)
      plex(7pt, fill: muted, chart.methodology)
    }
    for id in chart.indicator_ids {
      let indicator = report.indicator_catalog.find(i => i.id == id)
      v(2mm)
      plex(7pt, fill: muted, indicator.label + " · " + indicator.methodology + " · " + indicator.convention)
    }
  }
  for threshold in references(chart, report.indicator_catalog) {
    v(2mm)
    plex(7pt, fill: muted, "Fonte riferimento: " + threshold.source)
  }
}
