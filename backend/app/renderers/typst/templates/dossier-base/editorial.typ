// Resolved composition used to freeze the canonical dossier's physical pages.
#import "base.typ": dossier, cover, plex, marker, body-width, navy, blue, ink, muted, rule, gray-mode
#import "charts.typ": chart-component, value-table
#import "chart-format.typ": display-value, unit-label
#let report = json("model.json")
#let options = json("options.json")
#let inventory = json("editorial-inventory.json")
#let note-text-height = 18mm
#let safe-prose(size, value, weight: 400, fill: navy) = context {
  if value.split(regex("\\s+")).any(word =>
    measure(plex(size, weight: weight, word)).width > body-width) {
    panic("editorial-prose-token-does-not-fit")
  }
  plex(size, weight: weight, fill: fill, value)
}
#let footer() = context {
  let page-number = here().page()
  let comment = "Spazio riservato al commento del dossier."
  if report.editorial_plan != none {
    if page-number > report.editorial_plan.pages.len() { panic("page-outside-editorial-plan") }
    let page = report.editorial_plan.pages.at(page-number - 1)
    let note = report.editorial_notes.find(n => n.id == page.note_id)
    if note != none { comment = note.text }
  }
  let text-body = plex(9pt, fill: muted, comment)
  let measured = measure(block(width: body-width, text-body))
  // A line break limit also rejects blank-line expansion; neither path truncates.
  if (measured.height > note-text-height or comment.split("\n").len() > 4 or
    comment.split(regex("\\s+")).any(word => measure(plex(9pt, word)).width > body-width)) {
    panic("editorial-note-does-not-fit")
  }
  marker((kind: "slot", content_id: "note-slot", width_pt: str(body-width.pt()),
    height_pt: str(note-text-height.pt()), font_size_pt: "9", max_lines: 4))
  block(width: body-width, height: 26mm)[
    #line(length: 100%, stroke: 0.7pt + rule)
    #v(2pt)
    #plex(8pt, weight: 600, fill: navy)[Lettura del consulente]
    #v(3pt)
    #block(width: body-width, height: note-text-height, text-body)
  ]
}
#show: body => dossier(report, options, body, note-footer: footer)
#let cell(value, unit, available: body-width, size: 8pt, fill: ink) = if unit == none {
  // Permit wrapping technical source names at separators without removing text.
  let display = if value == none { "n.d." } else {
    value.replace("_", "_\u{200b}").replace("+", "+\u{200b}")
      .replace("/", "/\u{200b}").replace(".", ".\u{200b}")
  }
  if display.split(regex("[\\s\u{200b}]+")).any(word => measure(plex(size, word)).width > available) {
    panic("editorial-cell-token-does-not-fit")
  }
  plex(size, fill: fill, display)
} else {
  // Euro interi nelle tabelle (decisione del proprietario, 2026-09-17): «4.006.984,18» non entra in una
  // colonna di un periodo su sei (49,7 pt contro 39,8). Si arrotonda al mezzo euro sulla stringa; i
  // grafici restano al centesimo, i conti restano al centesimo sotto.
  let display = plex(size, fill: fill, display-value(value, unit, places: if unit == "eur" { 0 } else { none }))
  if measure(display).width > available { panic("editorial-amount-does-not-fit") }
  display
}
#let heading(item) = [
  #marker((kind: "content", content_id: "heading:" + item.id))
  #safe-prose(14pt, weight: 600, fill: navy, item.title)
  #v(2mm)
]
#let appendix-index() = context {
  let values = query(metadata).map(node => node.value)
  for statement in report.detailed_statements {
    let rows = values.filter(value => value.kind == "content" and
      value.content_id.starts-with("row:" + statement.id + ":"))
    if rows.len() == 0 { panic("appendix-index-without-source-rows") }
    let first = rows.first().page
    let last = rows.last().page
    plex(9pt, statement.title + " · pagina " + str(first) +
      if first == last { "" } else { "–" + str(last) })
    linebreak()
  }
}
#let repeated-table-title(section, item, count) = table.cell(
  colspan: count,
  fill: if gray-mode { rgb("#F2F2F2") } else { rgb("#F3F6F8") },
  inset: (x: 3pt, y: 2.5pt),
)[
  #grid(columns: (auto, 1fr), column-gutter: 3mm,
    plex(6.8pt, weight: 600, fill: blue, upper(section.title)),
    align(right, plex(7pt, weight: 500, fill: navy, item.title)))
]
#let compact-period-table(section, item, value-start) = context {
  let count = item.columns.len()
  let value-count = count - value-start - 1
  let label-width = if value-count >= 6 { 65mm } else { 78mm }
  let value-width = (body-width - label-width) / value-count
  let cells = ()
  for row in item.rows {
    cells.push(table.cell(breakable: false)[
      #marker((kind: "content", content_id: row.id))
      #if value-start == 2 {
        cell(row.cells.first(), none, available: label-width - 6pt, size: 6.5pt, fill: muted)
        linebreak()
        cell(row.cells.at(1), row.units.at(1), available: label-width - 6pt)
      } else {
        cell(row.cells.first(), row.units.first(), available: label-width - 6pt)
      }
      #let note = row.cells.last()
      #if note != none and note != "" {
        linebreak()
        cell(note, none, available: label-width - 6pt, size: 6.3pt, fill: muted)
      }
    ])
    for index in range(value-start, count - 1) {
      cells.push(table.cell(breakable: false, align: right,
        cell(row.cells.at(index), row.units.at(index), available: value-width - 6pt)))
    }
  }
  table(columns: (label-width, ..((value-width,) * value-count)), inset: (x: 3pt, y: 2.5pt),
    stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
    table.header(
      repeated-table-title(section, item, value-count + 1),
      table.cell(fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") },
        plex(7.2pt, weight: 600, fill: navy, item.columns.at(if value-start == 2 { 1 } else { 0 }))),
      ..item.columns.slice(value-start, count - 1).map(c => table.cell(
        fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") }, align: right,
        plex(7pt, weight: 600, fill: navy, c)))),
    ..cells)
}
#let data-table(section, item) = context {
  let count = item.columns.len()
  let periodic-start = if item.id.starts-with("appendix:") { 1 }
    else if (item.id.starts-with("comparison:") or item.id.starts-with("forecast-")
      or item.id == "infrannual-closing-values") { 2 }
    else { none }
  let label-width = if count <= 3 { 65mm } else { 60mm }
  let column-width = (body-width - label-width) / calc.max(1, count - 1)
  let fits = count >= 2 and item.rows.all(r =>
    r.cells.enumerate().all(pair => pair.at(0) == 0 or
      measure(cell(pair.at(1), r.units.at(pair.at(0)))).width <= column-width - 6pt))
  if periodic-start != none and count - periodic-start - 1 > 0 {
    compact-period-table(section, item, periodic-start)
  } else if fits {
    let cells = ()
    for row in item.rows {
      for (index, value) in row.cells.enumerate() {
        cells.push(table.cell(breakable: false)[
          #if index == 0 { marker((kind: "content", content_id: row.id)) }
          #cell(value, row.units.at(index), available: if index == 0 { label-width - 6pt } else { column-width - 6pt })
        ])
      }
    }
    table(columns: (label-width, ..((column-width,) * (count - 1))), inset: 3pt,
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(
        repeated-table-title(section, item, count),
        ..item.columns.map(c => table.cell(
          fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") },
          plex(7.5pt, weight: 600, fill: navy, c)))),
      ..cells)
  } else {
    // Long labels, many periods and large exact amounts receive room to wrap.
    let cells = ()
    for row in item.rows {
      cells.push(table.cell(breakable: false)[
        #marker((kind: "content", content_id: row.id))
        #cell(row.cells.first(), row.units.first(), available: 65mm - 6pt)
      ])
      cells.push(table.cell(breakable: false)[
        #for index in range(1, count) {
          plex(7pt, weight: 600, fill: muted, item.columns.at(index) + ": ")
          cell(row.cells.at(index), row.units.at(index), available: body-width - 65mm - 6pt)
          if index < count - 1 { linebreak() }
        }
      ])
    }
    table(columns: (65mm, body-width - 65mm), inset: 3pt,
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(
        repeated-table-title(section, item, 2),
        table.cell(fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") },
          plex(7.5pt, weight: 600, item.columns.first())),
        table.cell(fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") },
          plex(7.5pt, weight: 600)[Valori, periodi e fonti])),
      ..cells)
  }
}
#for section in inventory {
  if section.id != "cover" {
    pagebreak()
    plex(7.4pt, weight: 600, fill: blue, tracking: 0.6pt, upper(section.title))
    v(4mm)
  }
  for item in section.items {
    if item.kind == "cover" { cover(report) }
    else if item.kind == "table" {
      block(sticky: true, heading(item))
      data-table(section, item)
      v(5mm)
    } else if item.kind == "chart" {
      let chart = report.chart_series.find(c => c.id == item.chart_id)
      let content = [
        #safe-prose(14pt, weight: 600, fill: navy, item.title)
        #v(3mm)
        #chart-component(chart, gray: options.grayscale, indicators: report.indicator_catalog)
        #v(2mm)
        #value-table(chart)
      ]
      context {
        if measure(block(width: body-width, content)).height > 220mm {
          panic("editorial-chart-with-values-does-not-fit")
        }
        block(width: body-width, breakable: false, content)
      }
      v(5mm)
    } else {
      let content = [
        #marker((kind: "content", content_id: item.id))
        #safe-prose(14pt, weight: 600, fill: navy, item.title)
        #v(2mm)
        #if item.id == "appendix-index" { appendix-index() } else { safe-prose(9pt, fill: muted, item.text) }
      ]
      context {
        if measure(block(width: body-width, content)).height > 220mm {
          panic("editorial-text-does-not-fit")
        }
        block(width: body-width, breakable: false, content)
      }
      v(5mm)
    }
  }
}
