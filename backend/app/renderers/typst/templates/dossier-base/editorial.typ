// Resolved composition used to freeze the canonical dossier's physical pages.
#import "base.typ": dossier, cover, plex, marker, body-width, navy, blue, ink, muted, rule, gray-mode, kpi-strip, kpi-column
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
  let page-of(id) = {
    let hits = values.filter(v => v.kind == "content" and v.content_id == id)
    if hits.len() == 0 { none } else { hits.first().page }
  }
  for (letter, statement) in ("A", "B", "C").zip(report.detailed_statements) {
    let rows = values.filter(value => value.kind == "content" and
      value.content_id.starts-with("row:" + statement.id + ":"))
    if rows.len() == 0 { panic("appendix-index-without-source-rows") }
    let first = rows.first().page
    let last = rows.last().page
    plex(9pt, "Allegato " + letter + " · " + statement.title + " · pagina " + str(first) +
      if first == last { "" } else { "–" + str(last) })
    linebreak()
  }
  // Voci extra dell'indice: registro, matrice dei dettagli, tabelle F/G e
  // metodologia emergono dall'inventario, non da un elenco a mano.
  for section in inventory {
    if section.id == "appendices_methodology" {
      for item in section.items {
        if item.kind == "table" and not item.id.starts-with("appendix:") {
          let page = page-of("heading:" + item.id)
          if page != none {
            plex(9pt, item.title + " · pagina " + str(page))
            linebreak()
          }
        }
      }
    }
  }
}
#let repeated-table-title(section, item, count) = table.cell(
  colspan: count,
  fill: if gray-mode { rgb("#F2F2F2") } else { rgb("#F3F6F8") },
  inset: (x: 3pt, y: 2.5pt),
)[
  #grid(columns: (auto, 1fr), column-gutter: 3mm,
    plex(6.8pt, weight: 600, fill: blue, upper(section.family)),
    align(right, plex(7pt, weight: 500, fill: navy, item.title)))
]
#let compact-fits(item, value-start) = {
  // Stessa geometria di compact-period-table; misura senza panic: se un valore
  // eccedesse la colonna (es. un rapporto degenero in percentuale) la tabella
  // cade nel ramo impilato, che ha spazio di wraping, non si ferma.
  let count = item.columns.len()
  let value-count = count - value-start - 1
  let per = calc.min(value-count, 6)
  let label-width = if value-count >= 6 { 65mm } else { 78mm }
  let value-width = (body-width - label-width) / per
  item.rows.all(row => range(value-start, count - 1).all(i =>
    row.cells.at(i) == none or row.units.at(i) == none or
    measure(plex(8pt, display-value(row.cells.at(i), row.units.at(i),
      places: if row.units.at(i) == "eur" { 0 } else { none }))).width <= value-width - 6pt))
}
#let compact-period-table(section, item, value-start, part-size) = context {
  let count = item.columns.len()
  let total = count - value-start - 1
  let per = calc.min(total, part-size)
  let label-width = if total >= 6 { 65mm } else { 78mm }
  let value-width = (body-width - label-width) / per
  // Con più di `part-size` periodi la tabella si divide in parti verticali per
  // gruppi di periodi (M2-02B difetto 5: «mai in orizzontale»): le etichette
  // restano una, i valori girano in blocchi con intestazione ripetuta. Ogni
  // parte porta i propri marcatori «{riga}#parte:N» — dichiarati in Python da
  // `expected_content_inventory` — così nessuna pagina delle parti resta senza
  // copertura e il piano editoriale può vincolare le note anche a esse.
  for (part, offset) in range(0, total, step: per).enumerate() {
    let from = value-start + offset
    let to = calc.min(from + per, count - 1)
    let cells = ()
    for row in item.rows {
      let marker-id = if part == 0 { row.id } else { row.id + "#parte:" + str(part + 1) }
      cells.push(table.cell(breakable: false)[
        #marker((kind: "content", content_id: marker-id))
        #if value-start == 2 {
          cell(row.cells.first(), none, available: label-width - 6pt, size: 6.5pt, fill: muted)
          linebreak()
          cell(row.cells.at(1), row.units.at(1), available: label-width - 6pt)
        } else {
          cell(row.cells.first(), row.units.first(), available: label-width - 6pt)
        }
        #let note = row.cells.last()
        #if part == 0 and note != none and note != "" {
          linebreak()
          cell(note, none, available: label-width - 6pt, size: 6.3pt, fill: muted)
        }
      ])
      for index in range(from, to) {
        cells.push(table.cell(breakable: false, align: right,
          cell(row.cells.at(index), row.units.at(index), available: value-width - 6pt)))
      }
    }
    table(columns: (label-width, ..((value-width,) * (to - from))), inset: (x: 3pt, y: 2.5pt),
      stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
      table.header(
        repeated-table-title(section, item, to - from + 1),
        table.cell(fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") },
          plex(7.2pt, weight: 600, fill: navy, item.columns.at(if value-start == 2 { 1 } else { 0 }))),
        ..item.columns.slice(from, to).map(c => table.cell(
          fill: if gray-mode { rgb("#F7F7F7") } else { rgb("#F8FAFB") }, align: right,
          plex(7pt, weight: 600, fill: navy, c)))),
      ..cells)
    v(5mm)
  }
}
#let data-table(section, item) = context {
  let count = item.columns.len()
  // La periodicità è dichiarata dall'inventario (`value_start`/`part_size`),
  // non indovinata dall'ID: Python e Typst devono vedere la stessa regola,
  // perché `expected_content_inventory` pianifica i marcatori delle parti.
  let periodic-start = if "value_start" in item { item.value_start } else { none }
  let part-size = if "part_size" in item { item.part_size } else { 6 }
  let label-width = if count <= 3 { 65mm } else { 60mm }
  let column-width = (body-width - label-width) / calc.max(1, count - 1)
  let token-ok = (value, width) => value == none or value.split(regex("\\s+")).all(word =>
    measure(plex(8pt, word)).width <= width)
  let amount-ok = (value, unit, width) => (value == none or
    measure(plex(8pt, display-value(value, unit, places: if unit == "eur" { 0 } else { none }))).width <= width)
  let cell-ok = (value, unit, width) => if unit == none { token-ok(value, width) } else { amount-ok(value, unit, width) }
  let fits = count >= 2 and item.rows.all(r =>
    token-ok(r.cells.at(0), label-width - 6pt) and
    r.cells.enumerate().all(pair => pair.at(0) == 0 or
      cell-ok(pair.at(1), r.units.at(pair.at(0)), column-width - 6pt)))
  if periodic-start != none and count - periodic-start - 1 > part-size {
    compact-period-table(section, item, periodic-start, part-size)
  } else if periodic-start != none and count - periodic-start - 1 > 0 and compact-fits(item, periodic-start) {
    compact-period-table(section, item, periodic-start, count - periodic-start - 1)
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
    context {
      let number = counter(page).get().first()
      plex(7.4pt, weight: 600, fill: blue, tracking: 0.6pt,
        upper(section.family) + " · " + (if number < 10 { "0" } else { "" }) + str(number))
    }
    v(3mm)
    safe-prose(16pt, weight: 600, fill: navy, section.title)
    v(2mm)
    if section.subtitle != none {
      safe-prose(8pt, fill: muted, section.subtitle)
    }
    v(5mm)
    if "kpis" in section and section.kpis.len() > 0 {
      kpi-strip(section.kpis)
      v(5mm)
    }
  }
  for (index, item) in section.items.enumerate() {
    if item.kind == "cover" { cover(report, kpis: if "kpis" in section { section.kpis } else { () }) }
    else if item.kind == "table" {
      block(sticky: true, heading(item))
      data-table(section, item)
      v(5mm)
    } else if item.kind == "chart" {
      let chart = item.chart
      // Rilievo 1: la pagina tipo è UNA pagina. Nessun interblocco fra
      // intestazione di sezione e primo grafico; da lì in poi ogni grafico
      // occupa una fascia propria: colonna KPI verticale a sinistra (55 mm),
      // grafico a destra (118 mm), come la v4. La tabella di sintesi resta,
      // a tutta larghezza, sotto la fascia KPI+grafico — è lì anche nella v4
      // (pag. 8 «Conto economico · € migliaia», pag. 11 «Indicatori del
      // piano»): a mancare era solo l'interruzione di pagina, non la tabella.
      let has-kpi = "kpis" in item and item.kpis.len() > 0
      if index > 0 { pagebreak(weak: true) }
      let figure = [
        #safe-prose(14pt, weight: 600, fill: navy, item.title)
        #v(3mm)
        #if has-kpi {
          grid(columns: (55mm, 118mm), column-gutter: 5mm,
            kpi-column(item.kpis),
            chart-component(chart, gray: options.grayscale, indicators: report.indicator_catalog, width-mm: 118))
        } else {
          chart-component(chart, gray: options.grayscale, indicators: report.indicator_catalog)
        }
        #v(4mm)
        #value-table(chart, places: if chart.unit == "eur" { 0 })
      ]
      context {
        if measure(block(width: body-width, figure)).height > 220mm {
          panic("editorial-chart-with-values-does-not-fit")
        }
        block(width: body-width, breakable: false, figure)
      }
      v(5mm)
    } else if item.kind == "note" {
      // Nota di indisponibilità raggruppata (M2-02B integrazione, rilievo 3):
      // corpo ridotto, senza titolo di sezione, subito sotto la tabella che
      // spiega — stile metadati già usato per la nota di riga in
      // `compact-period-table`, mai la resa a pagina intera dei blocchi
      // narrativi.
      let content = [
        #marker((kind: "content", content_id: item.id))
        #safe-prose(7.2pt, fill: muted, item.text)
      ]
      context {
        if measure(block(width: body-width, content)).height > 220mm {
          panic("editorial-availability-note-does-not-fit")
        }
        block(width: body-width, breakable: false, content)
      }
      v(3mm)
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
