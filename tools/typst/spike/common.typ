// Presentation only. Exact wire values are retained in text and tables;
// float conversion is confined to vector plotting coordinates.
#let palette(gray: false) = if gray { (black, rgb("777777"), rgb("bbbbbb")) } else { (rgb("153f4d"), rgb("b28646"), rgb("8ea5ac")) }
#let value(v) = if v == none { [n.d.] } else {
  let raw = str(v)
  let negative = raw.starts-with("-")
  let parts = raw.trim(at: start, "-").split(".")
  let digits = parts.first()
  let groups = ()
  while digits.len() > 3 {
    groups.insert(0, digits.slice(digits.len() - 3))
    digits = digits.slice(0, digits.len() - 3)
  }
  groups.insert(0, digits)
  (if negative { "−" } else { "" }) + groups.join(".") + (if parts.len() > 1 { "," + parts.at(1) } else { "" })
}
#let segments(values) = {
  let result = (); let current = ()
  for (i, v) in values.enumerate() {
    if v == none {
      if current.len() > 0 { result.push(current); current = () }
    } else { current.push((i, float(v))) }
  }
  if current.len() > 0 { result.push(current) }
  result
}
#let limits(chart) = {
  let values = chart.series.map(s => s.values.filter(v => v != none).map(float)).flatten()
  values.push(0)
  if chart.id == "coverage" { values.push(1) }
  let lo = calc.min(..values); let hi = calc.max(..values)
  let pad = calc.max((hi - lo) * 0.08, 0.1)
  (lo - pad, hi + pad)
}
#let legend(chart, gray: false) = {
  for (i, s) in chart.series.enumerate() {
    box(width: 10pt, height: 3pt, fill: palette(gray: gray).at(i))
    h(4pt); text(size: 8pt, s.label); h(10pt)
  }
}
#let chart-table(chart) = {
  table(columns: (1.7fr, ..chart.categories.map(_ => 1fr)),
    inset: 5pt, stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")),
    table.header([*Serie*], ..chart.categories.map(y => strong(str(y)))),
    ..chart.series.map(s => (text(size: 8pt, s.label), ..s.values.map(v => align(right, value(v))))).flatten()
  )
}
#let plot-note(chart) = text(size: 8pt, fill: rgb("60747d"))[
  Unità: #chart.unit. n.d. = dato non disponibile; i tratti si interrompono sui null.
  #if chart.id == "coverage" { [Linea di riferimento DSCR: 1,00.] }
]
