// M2-02A base composition. No financial formulas or executable report text.
#let gray-mode = json("options.json").grayscale
#let navy = if gray-mode { rgb("#262626") } else { rgb("#003049") }
#let blue = if gray-mode { rgb("#777777") } else { rgb("#669BBC") }
#let ink = if gray-mode { rgb("#222222") } else { rgb("#1B1F24") }
#let muted = if gray-mode { rgb("#666666") } else { rgb("#5E6B78") }
#let rule = if gray-mode { rgb("#DDDDDD") } else { rgb("#D5DDE4") }
#let page-width = 210mm
#let body-width = 178mm
#let note-width = body-width
#let note-height = 26mm
#let note-font = 9pt
#let layout-version = "dossier-base-1"

// Typst exposes these static files under their legacy family names.
#let plex(..arguments) = {
  let weight = arguments.named().at("weight", default: 400)
  let family = if weight >= 550 { "IBM Plex Sans SmBld" }
    else if weight >= 450 { "IBM Plex Sans Medm" } else { "IBM Plex Sans" }
  text(font: family, ..arguments)
}

#let marker(value) = context metadata(value + (page: here().page()))

#let note-slot() = block(width: note-width, height: note-height)[
  #line(length: 100%, stroke: 0.7pt + rule)
  #v(2pt)
  #plex(8pt, weight: 600, fill: navy)[Commento di pagina]
  #v(3pt)
  #plex(note-font, fill: muted)[Spazio riservato al commento del dossier.]
]

#let dossier(report, options, body, note-footer: none) = {
  let accent = if options.grayscale { gray.darken(50%) } else { navy }
  set document(title: report.document.title, author: "Formula Finance",
    description: "Base editoriale del report budget")
  set text(font: "IBM Plex Sans", lang: "it", size: 9pt, fill: ink)
  set par(leading: 3pt, justify: false)
  set page(paper: "a4", margin: (left: 16mm, right: 16mm, top: 20mm, bottom: 46mm),
    footer-descent: 4mm,
    header: context align(right, plex(7pt,
      fill: if counter(page).get().first() == 1 { white } else { muted }, report.document.title)),
    footer: context [
      #marker((kind: "page", content_id: "page-shell"))
      #if note-footer == none { note-slot() } else { note-footer() }
      #v(2mm)
      #line(length: 100%, stroke: 0.5pt + rule)
      #v(1mm)
      #grid(columns: (1fr, auto),
        plex(6.8pt, fill: muted)[Bilancio · rettifiche · ipotesi · proiezioni],
        plex(6.8pt, fill: muted, counter(page).display("1")))
    ],
    background: context {
      if counter(page).get().first() == 1 {
        place(top + left,
          rect(width: page-width, height: 108mm, fill: accent, stroke: none))
      }
      if options.document_state == "draft" {
        place(center + horizon, rotate(-35deg,
          plex(78pt, weight: 600, fill: gray.lighten(75%))[BOZZA]))
      }
    })
  body
}

#let cover-heading(report, company-size) = [
    #plex(8pt, fill: white)[REPORT BUDGET]
    #v(7mm)
    #plex(24pt, weight: 600, fill: white, report.document.title)
    #v(7mm)
    #plex(company-size, weight: 500, fill: white, report.company.name)
]

#let cover(report) = {
  marker((kind: "content", content_id: "cover"))
  context {
    let chosen = none
    for size in (17pt, 14pt, 11pt) {
      let candidate = cover-heading(report, size)
      if chosen == none and measure(block(width: body-width, candidate)).height <= 88mm {
        chosen = candidate
      }
    }
    if chosen == none { panic("cover-name-does-not-fit") }
    block(height: 88mm, chosen)
  }
  v(9mm)
  plex(8pt, fill: muted)[PERIMETRO DEL DOCUMENTO]
  v(3mm)
  plex(16pt, weight: 600, fill: navy)[Dati di partenza, ipotesi e risultati del piano]
  v(3mm)
  report.practice.budget_scenario.name
  v(6mm)
  plex(9pt)[Il dossier distingue i dati di partenza dalle proiezioni. I prospetti
    completi sono raccolti nella sezione Allegati.]
  v(5mm)
  plex(8pt, fill: muted)[Base editoriale in sviluppo. Grafici e commenti per pagina
    saranno inseriti nei successivi componenti del dossier.]
}

#let parent-labels(statement, row) = {
  let labels = ()
  let parent = row.parent_id
  while parent != none {
    let item = statement.rows.find(r => r.id == parent)
    labels.insert(0, item.label)
    parent = item.parent_id
  }
  labels.join(" / ")
}

#let statement-table(statement) = {
  let columns = statement.periods.len()
  let label-width = if columns <= 5 { 82mm } else { 65mm }
  let value-width = (body-width - label-width) / columns
  let cells = ()
  for row in statement.rows {
    let strong = row.kind in ("section", "group", "subtotal", "total")
    let background = if row.kind in ("section", "total") {
      if gray-mode { rgb("#F2F2F2") } else { rgb("#EEF3F6") }
    } else { none }
    let parents = parent-labels(statement, row)
    cells.push(table.cell(breakable: false, fill: background)[
      #marker((kind: "row", content_id: "row:" + statement.id + ":" + row.id,
        statement_id: statement.id, row_id: row.id))
      #if parents != "" and row.kind == "detail" {
        plex(6.5pt, fill: muted, parents)
        linebreak()
      }
      #plex(weight: if strong { 600 } else { 400 }, fill: if strong { navy } else { ink }, row.label)
    ])
    for (index, value) in row.values.enumerate() {
      let label = if value != none { value }
        else if row.unavailable_reasons.at(index) == "presentation_header" { "" } else { "n.d." }
      cells.push(table.cell(breakable: false, fill: background,
        align: right, context {
          let amount = plex(8pt, weight: if strong { 600 } else { 400 }, label)
          if measure(amount).width > value-width - 6pt { panic("amount-does-not-fit-base-column") }
          amount
        }))
    }
  }
  set text(size: 8pt)
  table(columns: (label-width, ..((value-width,) * columns)),
    inset: (x: 3pt, y: 3pt), stroke: (left: none, right: none, top: none, bottom: 0.4pt + rule),
    table.header(
      table.cell(colspan: columns + 1, plex(8pt, weight: 600, fill: navy, statement.title)),
      table.cell(plex(7.5pt, weight: 600)[Voce · euro]),
      ..statement.periods.map(p => table.cell(align: right, plex(7pt, weight: 600, p.label)))),
    ..cells)
}

#let appendix(statement) = {
  pagebreak()
  plex(8pt, fill: blue, weight: 600)[ALLEGATI]
  v(3mm)
  plex(16pt, fill: navy, weight: 600, statement.title)
  v(2mm)
  plex(8pt, style: "italic", fill: muted)[Prospetto completo · valori in euro · n.d. = dato non disponibile]
  v(4mm)
  statement-table(statement)
}
