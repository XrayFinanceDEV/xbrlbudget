// Native vectors only. Floats are confined to graphical coordinates/axis ticks.
#import "base.typ": plex, navy, blue, ink, muted, rule
#import "chart-format.typ": display-value, unit-label, precision
#let geometry = json("chart-layout.json")
#let coordinate(value) = {
  let result = float(value)
  let zero = str(value).replace("-", "").replace(".", "").clusters().all(d => d == "0")
  if result == calc.inf or result == -calc.inf or result != result or (result == 0 and not zero) {
    panic("chart-coordinate-out-of-range")
  }
  result
}
#let colors(gray) = {
  if gray { (black, rgb("#555555"), rgb("#888888"), rgb("#BBBBBB")) }
  else { (navy, blue, rgb("#5E6B78"), rgb("#AEC5D2")) }
}
#let dash(index) = ("solid", "dashed", "dotted", "dash-dotted").at(calc.rem(index, 4))
#let symbol(index, color) = {
  if calc.rem(index, 4) == 0 { circle(radius: 2.3pt, fill: color, stroke: 0.4pt + color) }
  else if calc.rem(index, 4) == 1 { rect(width: 4.6pt, height: 4.6pt, fill: color, stroke: 0.4pt + color) }
  else if calc.rem(index, 4) == 2 { rotate(45deg, rect(width: 4.6pt, height: 4.6pt, fill: color, stroke: 0.4pt + color)) }
  else { circle(radius: 2.3pt, fill: white, stroke: 0.9pt + color) }
}
#let segments(values) = {
  let result = (); let current = ()
  for (i, value) in values.enumerate() {
    if value == none {
      if current.len() > 0 { result.push(current); current = () }
    } else { current.push((i, coordinate(value))) }
  }
  if current.len() > 0 { result.push(current) }
  result
}
#let references(chart, indicators) = {
  let result = ()
  if "indicator_ids" in chart {
    for id in chart.indicator_ids {
      let indicator = indicators.find(i => i.id == id)
      for threshold in indicator.thresholds {
        result.push((label: indicator.label + " · " + threshold.label,
          value: threshold.value, source: threshold.source))
      }
    }
  }
  result
}
#let plot(chart, gray: false, thresholds: ()) = {
  let width = float(geometry.width_mm) * 1mm
  let height = float(geometry.plot_height_mm) * 1mm
  let values = chart.series.map(s => s.values.filter(v => v != none).map(coordinate)).flatten()
  if values.len() == 0 {
    box(width: width, height: height, align(center + horizon,
      plex(11pt, fill: muted)[n.d. · Nessun dato disponibile per i periodi rappresentati]))
  } else {
    values += thresholds.map(t => coordinate(t.value))
    if values.any(v => v == calc.inf or v == -calc.inf or v != v) { panic("chart-coordinate-out-of-range") }
    values.push(0)
    let lo = calc.min(..values); let hi = calc.max(..values)
    let magnitude = calc.max(calc.abs(lo), calc.abs(hi))
    let exponent = if magnitude >= 1000 or (magnitude > 0 and magnitude < 0.01) {
      int(calc.floor(calc.log(magnitude, base: 10)))
    } else { 0 }
    let scale = calc.pow(10, exponent)
    if scale == 0 or scale == calc.inf { panic("chart-scale-out-of-range") }
    // Normalize before subtracting: avoid overflow of opposite large values.
    lo = lo / scale; hi = hi / scale
    let padding = if hi == lo { 1 } else { (hi - lo) * 0.08 }
    lo -= padding; hi += padding
    let ox = 41pt; let oy = 16pt
    let pw = width - ox - 8pt; let ph = height - oy - 25pt
    let xp(index) = ox + (index + 0.5) / chart.categories.len() * pw
    let yp(value) = oy + (hi - value / scale) / (hi - lo) * ph
    let bars = chart.id in geometry.bars
    box(width: width, height: height)[
      #place(top + left, dx: ox, dy: 0pt, plex(7pt, fill: muted,
        unit-label(chart.unit) + if exponent != 0 { " · ×10^" + str(exponent) } else { "" }))
      #for k in range(5) {
        let tick = lo + k / 4 * (hi - lo)
        let y = oy + (hi - tick) / (hi - lo) * ph
        place(top + left, dx: ox, dy: y, line(length: pw, stroke: 0.4pt + rule))
        place(top + left, dy: y - 4pt, box(width: ox - 5pt,
          align(right, plex(7pt, fill: muted, str(calc.round(tick, digits: 2)).replace(".", ",")))))
      }
      #place(top + left, dx: ox, dy: yp(0), line(length: pw, stroke: 0.8pt + muted))
      #for threshold in thresholds {
        place(top + left, dx: ox, dy: yp(coordinate(threshold.value)),
          line(length: pw, stroke: (paint: muted, thickness: 0.7pt, dash: "dashed")))
      }
      #for (si, series) in chart.series.enumerate() {
        let color = colors(gray).at(calc.rem(si, 4))
        for segment in segments(series.values) {
          if bars {
            for (index, value) in segment {
              let bw = pw / chart.categories.len() * 0.72 / chart.series.len()
              let x = xp(index) - pw / chart.categories.len() * 0.36 + si * bw
              if value == 0 {
                place(top + left, dx: x, dy: yp(0), line(length: bw - 1pt, stroke: 1pt + color))
              } else {
                place(top + left, dx: x, dy: calc.min(yp(value), yp(0)),
                  rect(width: bw - 1pt, height: calc.abs(yp(value) - yp(0)), fill: color, stroke: 0.3pt + ink))
              }
            }
          } else {
            for j in range(segment.len() - 1) {
              let a = segment.at(j); let b = segment.at(j + 1)
              place(top + left, dx: xp(a.at(0)), dy: yp(a.at(1)),
                line(end: (xp(b.at(0)) - xp(a.at(0)), yp(b.at(1)) - yp(a.at(1))),
                  stroke: (paint: color, thickness: 1.5pt, dash: dash(si))))
            }
            for (index, value) in segment {
              place(top + left, dx: xp(index) - 2.3pt, dy: yp(value) - 2.3pt, symbol(si, color))
            }
          }
        }
      }
      #for (index, category) in chart.categories.enumerate() {
        place(top + left, dx: xp(index) - 13pt, dy: oy + ph + 6pt, plex(8pt, str(category)))
      }
    ]
  }
}
#let legend(chart, gray: false, thresholds: ()) = [
  #for (index, series) in chart.series.enumerate() {
    let color = colors(gray).at(calc.rem(index, 4))
    grid(columns: (14pt, 1fr), gutter: 5pt,
      box(width: 12pt, height: 8pt)[
        #place(left + horizon, line(length: 12pt, stroke: (paint: color, thickness: 1.5pt, dash: dash(index))))
      ], plex(8pt, series.label))
    v(3pt)
  }
  #for threshold in thresholds {
    plex(7pt, fill: muted, "Riferimento: " + threshold.label + " = " + display-value(threshold.value, chart.unit))
    v(2pt)
  }
]
#let chart-component(chart, gray: false, indicators: ()) = context {
  let width = float(geometry.width_mm) * 1mm
  let height = float(geometry.height_mm) * 1mm
  let legend-height = float(geometry.legend_height_mm) * 1mm
  if chart.series.len() > geometry.max_series { panic("chart-series-exceed-distinct-styles") }
  let thresholds = references(chart, indicators)
  let key = legend(chart, gray: gray, thresholds: thresholds)
  if measure(block(width: width, key)).height > legend-height { panic("chart-legend-does-not-fit") }
  let body = stack(dir: ttb, spacing: 0pt, plot(chart, gray: gray, thresholds: thresholds),
      block(width: width, height: legend-height, key))
  let measured = measure(body)
  if measured.height > height { panic("chart-component-does-not-fit") }
  metadata((kind: "chart", content_id: "chart:" + chart.id, page: here().page(),
    width_mm: geometry.width_mm, height_mm: geometry.height_mm,
    measured_width_mm: str(measured.width / 1mm), measured_height_mm: str(measured.height / 1mm),
    unit: chart.unit, categories: chart.categories, series: chart.series, thresholds: thresholds))
  block(width: width, height: height, breakable: false, body)
}
#let value-table(chart) = context {
  let width = float(geometry.width_mm) * 1mm
  let label-width = 135pt
  let column-width = (width - label-width) / chart.categories.len()
  let fits = chart.series.all(s => s.values.all(v =>
    measure(plex(8pt, display-value(v, chart.unit))).width <= column-width - 6pt))
  let cells = ()
  if fits {
    for series in chart.series {
      cells.push(table.cell(breakable: false, plex(8pt, series.label)))
      for value in series.values {
        cells.push(table.cell(breakable: false, align(right, plex(8pt, display-value(value, chart.unit)))))
      }
    }
    table(columns: (label-width, ..((column-width,) * chart.categories.len())), inset: 3pt,
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(plex(8pt, weight: 600, "Serie · " + unit-label(chart.unit)),
        ..chart.categories.map(y => table.cell(align: right, plex(8pt, weight: 600, str(y))))), ..cells)
  } else {
    // Keep large exact amounts readable; never shrink or clip their digits.
    for series in chart.series {
      cells.push(table.cell(colspan: 2, plex(8pt, weight: 600, series.label)))
      for (year, value) in chart.categories.zip(series.values) {
        if measure(plex(8pt, display-value(value, chart.unit))).width > width / 2 - 6pt {
          panic("chart-value-does-not-fit")
        }
        cells.push(table.cell(breakable: false, plex(8pt, str(year))))
        cells.push(table.cell(breakable: false, align(right, plex(8pt, display-value(value, chart.unit)))))
      }
    }
    table(columns: (1fr, 1fr), inset: 3pt,
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(plex(8pt, weight: 600)[Periodo], plex(8pt, weight: 600, "Valore · " + unit-label(chart.unit))), ..cells)
  }
}
