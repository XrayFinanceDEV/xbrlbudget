#import "common.typ": legend, chart-table, plot-note
#let candidate = sys.inputs.at("candidate", default: "native")
#let graph = if candidate == "native" {
  import "native.typ" as native
  native.render
} else if candidate == "cetz" {
  import "cetz.typ" as cetz
  cetz.render
} else {
  import "primaviz.typ" as prima
  prima.render
}
#let chart = json("chart.json")
#set page(paper: "a4", margin: 22mm)
#set text(font: "Libertinus Serif", size: 10pt, lang: "it")
#set par(justify: false)
#text(size: 18pt, weight: "bold", chart.title)
#v(14pt)
#graph(chart)
#v(14pt)
#legend(chart)
#v(8pt)
#plot-note(chart)
#v(14pt)
#chart-table(chart)
