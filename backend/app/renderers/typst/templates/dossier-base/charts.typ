// Native vectors only. Floats are confined to graphical coordinates/axis ticks.
#import "base.typ": plex, navy, blue, ink, muted, rule, gray-mode
#import "chart-format.typ": display-value-with-unit, display-value, unit-label, precision
#let geometry = json("chart-layout.json")
// Palette di serie = `colors.series_palette` dello style contract (deep, mid,
// amber, light-blue): le prime due sono le variabili di `base.typ`, così in
// scala di grigi restano i due toni che già usavano.
#let series-palette(gray) = {
  if gray { (rgb("#262626"), rgb("#777777"), rgb("#888888"), rgb("#BBBBBB")) }
  else { (navy, blue, rgb("#B7791F"), rgb("#9CC0D8")) }
}
// Nome storico, usato dai chiamanti precedenti: la palette è unica.
#let colors(gray) = series-palette(gray)
// `colors.chart_strokes.dumbbell_link` dello style contract.
#let dumbbell-link = if gray-mode { rgb("#AAAAAA") } else { rgb("#9CC0D8") }
#let kind(chart) = {
  // Il kind è un attributo dell'item (traccia A, punto 2): la lista `bars` del
  // bundle resta solo il ripiego di un item che non dichiara nulla.
  if "kind" in chart and chart.kind != none { chart.kind }
  else if chart.id in geometry.bars { "bar" } else { "line" }
}
#let coordinate(value) = {
  let result = float(value)
  let zero = str(value).replace("-", "").replace(".", "").clusters().all(d => d == "0")
  if result == calc.inf or result == -calc.inf or result != result or (result == 0 and not zero) {
    panic("chart-coordinate-out-of-range")
  }
  result
}
#let dash(index) = ("solid", "dashed", "dotted", "dash-dotted").at(calc.rem(index, 4))
#let dot(color, filled: true) = circle(radius: 2.3pt,
  fill: if filled { color } else { white }, stroke: (paint: color, thickness: if filled { 0.4pt } else { 0.9pt }))
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
#let cartesian-plot(chart, gray: false, thresholds: (), width-mm: none, bars: none, height-mm: none) = {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let height = if height-mm == none { float(geometry.plot_height_mm) * 1mm } else { float(height-mm) * 1mm }
  let bars = if bars != none { bars } else { kind(chart) == "bar" }
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
    // Rilievo 5: un asse di importi (eur) resta in euro interi sotto i
    // 10.000 €; solo oltre passa a € migliaia. Le altre unità (ratio,
    // percent, giorni) restano sulla soglia precedente: non sono importi,
    // e non è la loro scala a essere in questione qui.
    let is-amount = chart.unit == "eur"
    let exponent = if is-amount { if magnitude >= 10000 { 3 } else { 0 } }
      else if magnitude >= 1000 { int(calc.floor(calc.log(magnitude, base: 10))) } else { 0 }
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
    // Un asse di importi non mostra mai decimali («0,997» invece di «997»
    // euro): l'unità di tick è sempre intera, in euro o in migliaia di euro.
    let group-thousands(digits) = {
      let groups = (); let integer = digits
      while integer.len() > 3 {
        groups.insert(0, integer.slice(integer.len() - 3))
        integer = integer.slice(0, integer.len() - 3)
      }
      groups.insert(0, integer)
      groups.join(".")
    }
    let tick-label(tick) = if is-amount {
      let rounded = calc.round(tick, digits: 0)
      let sign = if rounded < 0 { "−" } else { "" }
      sign + group-thousands(str(calc.abs(rounded)))
    } else {
      str(calc.round(tick, digits: if calc.abs(tick) < 1 { 3 } else { 2 })).replace(".", ",")
    }
    let scale-word = if exponent == 3 { " · valori in migliaia" } else if exponent == 6 { " · valori in milioni" }
      else if exponent == 9 { " · valori in miliardi" } else { "" }
    box(width: width, height: height)[
      #place(top + left, dx: ox, dy: 0pt, plex(7pt, fill: muted, unit-label(chart.unit) + scale-word))
      #for k in range(5) {
        let tick = lo + k / 4 * (hi - lo)
        let y = oy + (hi - tick) / (hi - lo) * ph
        place(top + left, dx: ox, dy: y, line(length: pw, stroke: 0.4pt + rule))
        place(top + left, dy: y - 4pt, box(width: ox - 5pt,
          align(right, plex(7pt, fill: muted, tick-label(tick)))))
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
// stacked (traccia A, punto 3): barre orizzontali al 100%, un segmento per
// serie nell'ordine dichiarato — la stessa posizione in tutte le colonne, che
// è ciò che rende leggibile un confronto fra righe. Le quote non sono
// riscritte come cifre: il percentuale è la lunghezza del segmento, e i
// numeri restano nelle tavole di pagina e negli Allegati (è ciò che la v4
// dichiara nel proprio sottotitolo). Nessun numero nasce qui: `share` è la
// stessa divisione che già decide la lunghezza del segmento.
#let stacked-plot(chart, gray: false, width-mm: none, height-mm: none) = {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let height = if height-mm == none { float(geometry.plot_height_mm) * 1mm } else { float(height-mm) * 1mm }
  let rows = chart.categories.len()
  let label-w = calc.min(34mm, width * 0.26)
  let ox = label-w + 5pt
  let track = width - ox - 5pt
  let pad-top = 13pt; let pad-bottom = 6pt
  let row-h = (height - pad-top - pad-bottom) / calc.max(1, rows)
  let bar-h = calc.min(row-h * 0.66, 15pt)
  let value(index, series) = {
    let raw = series.values.at(index, default: none)
    if raw == none { none } else { coordinate(raw) }
  }
  let total(index) = chart.series.map(s => {
    let v = value(index, s)
    if v == none { 0.0 } else if v < 0 { panic("stacked-chart-negative-value") } else { v }
  }).sum()
  let shares(index) = chart.series.map(s => {
    let v = value(index, s)
    if v == none or total(index) == 0 { 0.0 } else { v / total(index) }
  })
  let before(list, count) = if count == 0 { 0.0 } else { list.slice(0, count).sum() }
  box(width: width, height: height)[
    #place(top + left, dy: 0pt, plex(7pt, fill: muted,
      "composizione percentuale · dettaglio numerico nelle tavole e negli allegati"))
    #for (index, category) in chart.categories.enumerate() {
      let y = pad-top + index * row-h
      place(top + left, dx: 0pt, dy: y + (row-h - bar-h) / 2,
        box(width: label-w, inset: (right: 3pt), align(right + horizon, plex(7.6pt, fill: muted, str(category)))))
      place(top + left, dx: ox, dy: y + (row-h - bar-h) / 2,
        rect(width: track, height: bar-h, fill: none, stroke: 0.4pt + rule))
      for (si, series) in chart.series.enumerate() {
        let paint = colors(gray).at(calc.rem(si, 4))
        let x = ox + before(shares(index), si) * track
        let w = shares(index).at(si) * track
        if w > 0.01mm {  // un segmento invisibile non si disegna: non è un dato assente
          place(top + left, dx: x, dy: y + (row-h - bar-h) / 2,
            rect(width: w, height: bar-h, fill: paint, stroke: (paint: white, thickness: 0.4pt)))
        }
      }
    }
  ]
}
// dumbbell (traccia A, punto 3): una riga per etichetta, cerchio vuoto =
// periodo iniziale, cerchio pieno = periodo finale, segmento `dumbbell-link`
// fra i due, valori `a → b` a destra. Due serie sole: la terza non avrebbe
// due estremi da congiungere, e disegnarla sarebbe un'invenzione del template.
#let dumbbell-plot(chart, gray: false, width-mm: none, height-mm: none) = {
  if chart.series.len() != 2 { panic("dumbbell-chart-requires-two-series") }
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let height = if height-mm == none { float(geometry.plot_height_mm) * 1mm } else { float(height-mm) * 1mm }
  let rows = chart.categories.len()
  let label-w = calc.min(38mm, width * 0.30)
  let values-w = calc.min(30mm, width * 0.22)
  let ox = label-w + 6pt
  let track = width - ox - values-w - 6pt
  let pad-top = 13pt; let pad-bottom = 12pt
  let row-h = (height - pad-top - pad-bottom) / calc.max(1, rows)
  let points = chart.series.map(s => s.values.filter(v => v != none).map(coordinate)).flatten()
  let lo = calc.min(0.0, ..points)
  let hi = calc.max(0.0, ..points)
  if hi == lo { hi = lo + 1.0 }
  let span = hi - lo
  hi += span * 0.08; lo -= span * 0.02
  let xp(value) = ox + (value - lo) / (hi - lo) * track
  let at(series, index) = {
    let raw = chart.series.at(series).values.at(index, default: none)
    if raw == none { none } else { coordinate(raw) }
  }
  let shown(raw, series, index) = if raw == none { "n.d." } else {
    display-value-with-unit(chart.series.at(series).values.at(index), chart.unit)
  }
  let axis-tick(value) = {
    let rounded = calc.round(value, digits: 2)
    (if rounded < 0 { "−" } else { "" }) + display-value-with-unit(calc.abs(rounded), chart.unit)
  }
  box(width: width, height: height)[
    #place(top + left, dy: 0pt, plex(7pt, fill: muted, unit-label(chart.unit)))
    // Gli estremi dell'asse sono numeri calcolati qui, non importi del
    // modello: `str(float)` negativo escono con il segno matematico U+2212,
    // che `display-value` non sa riconoscere (cerca "-", e si ritrova a
    // tagliare una stringa a metà di un carattere). Il segno si mette fuori,
    // come già fa `tick-label` del grafico cartesiano.
    #place(top + left, dx: ox, dy: height - pad-bottom + 4pt, box(width: track)[
      #plex(7pt, fill: muted, axis-tick(lo))
      #h(1fr)
      #plex(7pt, fill: muted, axis-tick(hi))
    ])
    #for (index, category) in chart.categories.enumerate() {
      let y = pad-top + index * row-h + row-h / 2
      place(top + left, dx: 0pt, dy: y - 4pt, box(width: label-w, inset: (right: 3pt),
        align(right, plex(7.6pt, fill: muted, str(category)))))
      place(top + left, dx: ox, dy: y, line(length: track, stroke: 0.4pt + rule))
      let a = at(0, index); let b = at(1, index)
      if a != none and b != none {
        place(top + left, dx: xp(a), dy: y - 1.5pt,
          line(length: calc.abs(xp(b) - xp(a)), stroke: (paint: dumbbell-link, thickness: 3pt)))
      }
      if a != none { place(top + left, dx: xp(a) - 2.3pt, dy: y - 2.3pt, dot(colors(gray).at(0), filled: false)) }
      if b != none { place(top + left, dx: xp(b) - 2.3pt, dy: y - 2.3pt, dot(colors(gray).at(1), filled: true)) }
      place(top + left, dx: width - values-w, dy: y - 4pt,
        box(width: values-w, align(right)[#plex(7.6pt, fill: ink,
          shown(a, 0, index) + " → " + shown(b, 1, index))]))
    }
  ]
}
#let plot(chart, gray: false, thresholds: (), width-mm: none, height-mm: none) = {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let height = if height-mm == none { float(geometry.plot_height_mm) * 1mm } else { float(height-mm) * 1mm }
  let values = chart.series.map(s => s.values.filter(v => v != none).map(coordinate)).flatten()
  if values.len() == 0 {
    // Un grafico vuoto non è una figura pulita: è il caso che in una pagina
    // executive si dichiara da sé (`is_empty`, non una sbarra a zero).
    box(width: width, height: height, align(center + horizon,
      plex(11pt, fill: muted)[n.d. · Nessun dato disponibile per i periodi rappresentati]))
  } else {
    let shape = kind(chart)
    if shape == "stacked" { stacked-plot(chart, gray: gray, width-mm: width-mm, height-mm: height-mm) }
    else if shape == "dumbbell" { dumbbell-plot(chart, gray: gray, width-mm: width-mm, height-mm: height-mm) }
    else { cartesian-plot(chart, gray: gray, thresholds: thresholds, width-mm: width-mm,
        bars: shape == "bar", height-mm: height-mm) }
  }
}
#let legend(chart, gray: false, thresholds: (), width-mm: none) = {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let shape = kind(chart)
  block(width: width, [
    #if shape == "dumbbell" [
      // I due marker del dumbbell non sono due serie: sono i due estremi del
      // confronto, e la legenda della v4 li nomina cosi.
      #for (index, series) in chart.series.enumerate() {
        grid(columns: (14pt, 1fr), column-gutter: 5pt,
          box(width: 12pt, height: 8pt)[
            #place(left + horizon, dx: 2pt, dot(colors(gray).at(index), filled: index > 0))],
          plex(7.6pt, fill: muted, series.label))
        v(3pt)
      }
    ] else [
      #for (index, series) in chart.series.enumerate() {
        let color = colors(gray).at(calc.rem(index, 4))
        grid(columns: (14pt, 1fr), column-gutter: 5pt,
          box(width: 12pt, height: 8pt)[
            #if shape == "line" [
              #place(left + horizon, line(length: 12pt, stroke: (paint: color, thickness: 1.5pt, dash: dash(index))))
            ] else [
              #place(left + horizon, rect(width: 10pt, height: 6.5pt, fill: color, stroke: 0.3pt + ink))
            ]
          ],
          plex(7.6pt, fill: muted, series.label))
        v(3pt)
      }
    ]
    #for threshold in thresholds [
      #plex(7pt, fill: muted, "Riferimento: " + threshold.label + " = " + display-value-with-unit(threshold.value, chart.unit))
      #v(2pt)
    ]
  ])
}
// `height-mm` lo dichiara Python quando la pagina ne mette due in colonna:
// due grafici da 94 mm più una tavola non stanno in un foglio, e la v4
// infatti li disegna più bassi. Senza dichiarazione vale la geometria base.
#let chart-component(chart, gray: false, indicators: (), width-mm: none, height-mm: none) = context {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let declared-height = if height-mm == none { geometry.height_mm } else { str(height-mm) }
  let height = float(declared-height) * 1mm
  // In un riquadro compatto la legenda riservata scende a 20 mm: i 32 della
  // geometria base sono tarati sul riquadro pieno, e lasciarli qui toglieva
  // al disegno metà della propria altezza.
  let legend-height = if height-mm == none { float(geometry.legend_height_mm) * 1mm } else { 20mm }
  if chart.series.len() > geometry.max_series { panic("chart-series-exceed-distinct-styles") }
  let thresholds = references(chart, indicators)
  let key = legend(chart, gray: gray, thresholds: thresholds, width-mm: width-mm)
  if measure(block(width: width, key)).height > legend-height { panic("chart-legend-does-not-fit") }
  let body = stack(dir: ttb, spacing: 0pt,
      plot(chart, gray: gray, thresholds: thresholds, width-mm: width-mm,
        height-mm: if height-mm == none { none } else { float(declared-height) - 20.0 }),
      block(width: width, height: legend-height, key))
  let measured = measure(body)
  if measured.height > height { panic("chart-component-does-not-fit") }
  metadata((kind: "chart", content_id: "chart:" + chart.id, page: here().page(),
    width_mm: if width-mm == none { geometry.width_mm } else { str(width-mm) }, height_mm: declared-height,
    measured_width_mm: str(measured.width / 1mm), measured_height_mm: str(measured.height / 1mm),
    unit: chart.unit, categories: chart.categories, series: chart.series, thresholds: thresholds))
  block(width: width, height: height, breakable: false, body)
}
// `places` è la precisione della tipografia del dossier: gli euro si impaginano
// in euro interi (M2-02), le altre unità restano alla precisione di default.
#let value-table(chart, places: none, width-mm: none) = context {
  let width = if width-mm == none { float(geometry.width_mm) * 1mm } else { float(width-mm) * 1mm }
  let label-width = 135pt
  let column-width = (width - label-width) / chart.categories.len()
  let shown(value) = display-value-with-unit(value, chart.unit, places: places)
  let fits = chart.series.all(s => s.values.all(v =>
    measure(plex(8pt, shown(v))).width <= column-width - 6pt))
  let cells = ()
  if fits {
    for series in chart.series {
      cells.push(table.cell(breakable: false, plex(8pt, series.label)))
      for value in series.values {
        cells.push(table.cell(breakable: false, align(right, plex(8pt, shown(value)))))
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
        if measure(plex(8pt, shown(value))).width > width / 2 - 6pt {
          panic("chart-value-does-not-fit")
        }
        cells.push(table.cell(breakable: false, plex(8pt, str(year))))
        cells.push(table.cell(breakable: false, align(right, plex(8pt, shown(value)))))
      }
    }
    table(columns: (1fr, 1fr), inset: 3pt,
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(plex(8pt, weight: 600)[Periodo], plex(8pt, weight: 600, "Valore · " + unit-label(chart.unit))), ..cells)
  }
}
#let panel-grid(gutter: 6mm, ..panels) = {
  // Due (o piú d'uno) grafici affiancati a metà larghezza: la forma
  // `full+panels` delle pagine 13 e 16 della v4. La larghezza di ogni pannello
  // la dichiara Python (`width_mm`, 86 mm con due pannelli su 178) e questo
  // grid la rispetta: le colonne sono `1fr`, il gutter è l'unico numero di
  // questa funzione.
  block(breakable: false,
    grid(columns: ((1fr,) * calc.max(1, panels.len())), column-gutter: gutter, ..panels))
}
