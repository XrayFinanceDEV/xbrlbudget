// M2-02 definitive editorial composition. No financial formulas or executable report text.
#let gray-mode = json("options.json").grayscale
#let navy = if gray-mode { rgb("#262626") } else { rgb("#003049") }
#let blue = if gray-mode { rgb("#777777") } else { rgb("#669BBC") }
#let ink = if gray-mode { rgb("#222222") } else { rgb("#1B1F24") }
#let muted = if gray-mode { rgb("#666666") } else { rgb("#5E6B78") }
#let rule = if gray-mode { rgb("#DDDDDD") } else { rgb("#D5DDE4") }
#let page-width = 210mm
#let body-width = 178mm
// Forma `rail+main` (v4, M2-02G traccia A punto 4): una colonna KPI di 47 mm
// a sinistra del `.main`, gutter di 15 pt (5 mm): 47 + 5 + 126 = 178.
#let rail-width = 47mm
#let rail-gutter = 5mm
#let rail-main-width = body-width - rail-width - rail-gutter
#let note-width = body-width
#let note-height = 26mm
#let note-font = 9pt
#let layout-version = "dossier-final-1"

#import "chart-format.typ": kpi-text

// Typst exposes these static files under their legacy family names.
#let plex(..arguments) = {
  let weight = arguments.named().at("weight", default: 400)
  let family = if weight >= 550 { "IBM Plex Sans SmBld" }
    else if weight >= 450 { "IBM Plex Sans Medm" } else { "IBM Plex Sans" }
  text(font: family, ..arguments)
}

#let marker(value) = context metadata(value + (page: here().page()))

// Colonna KPI della pagina tipo (M2-02B): la usano la copertina e le sezioni.
// I valori vengono dall'inventario, cioé dal modello v2; qui solo formattazione.
#let kpi-strip(kpis) = block(width: body-width, breakable: false)[
  #line(length: 100%, stroke: 0.6pt + rule)
  #v(3mm)
  #grid(columns: (1fr,) * kpis.len(), column-gutter: 6mm,
    ..kpis.map(kpi => block[
      #plex(15pt, weight: 600, fill: navy, kpi-text(kpi))
      #v(1.2mm)
      #text(7.4pt, fill: muted, kpi.label)
    ]))
  #v(3mm)
  #line(length: 100%, stroke: 0.4pt + rule)
]

// Rilievo 1: in pagina tipo la colonna KPI è VERTICALE a sinistra del grafico
// (v4: ~55 mm), non una striscia orizzontale in cima alla pagina dopo.
#let kpi-column(kpis) = box(width: 55mm, inset: 0pt)[
  #line(length: 100%, stroke: 0.6pt + rule)
  #for kpi in kpis {
    v(3.4mm)
    plex(13pt, weight: 600, fill: navy, kpi-text(kpi))
    v(0.8mm)
    text(7pt, fill: muted, kpi.label)
  }
  #v(3mm)
  #line(length: 100%, stroke: 0.4pt + rule)
]

// Rail di pagina (v4, M2-02G fase 2 punto 4): la colonna da 47 mm alta quanto
// la pagina, riquadri separati da un filo da 0,7 pt, valore 15 pt/600 su
// etichetta 7,8 pt muted (`kpi_valore` / `kpi_etichetta` dello style
// contract). Il corpo 15 pt è una scelta, non una constant: un KPI lungo
// («3 anni · 2027–2029», una serie di tre valori) scende a 12 e poi a 10 pt,
// e se nemmeno 10 bastano la pagina si rifiuta — mai un testo che esce dalla
// colonna senza dirlo.
#let kpi-rail-item(kpi) = {
  let body = kpi-text(kpi)
  // Il valore va a capo come ogni testo: cio che non puo andare a capo e un
  // token singolo (un importo, un «1.234 / 2.345» senza spazi). La misura è
  // quella, non la stringa intera — lo stesso criterio di `safe-prose`.
  let fits(size) = body.split(regex("\\s+")).all(word =>
    measure(plex(size, weight: 600, word)).width <= rail-width - 6pt)
  let chosen = if fits(15pt) { 15pt } else if fits(12pt) { 12pt } else if fits(10pt) { 10pt }
    else { panic("editorial-kpi-does-not-fit") }
  block(width: rail-width, breakable: false)[
    #line(length: 100%, stroke: 0.7pt + rule)
    #v(7pt)
    #plex(chosen, weight: 600, fill: navy, body)
    #v(2pt)
    #plex(7.8pt, fill: muted, kpi.label)
    #v(7pt)
  ]
}

#let kpi-rail(kpis) = context box(width: rail-width)[
  #for kpi in kpis { kpi-rail-item(kpi) }
  #line(length: 100%, stroke: 0.7pt + rule)
]

#let note-slot() = block(width: note-width, height: note-height)[
  #line(length: 100%, stroke: 0.7pt + rule)
  #v(2pt)
  #plex(8pt, weight: 600, fill: navy)[Lettura del consulente]
  #v(3pt)
  #plex(note-font, fill: muted)[Spazio riservato al commento del dossier.]
]

#let dossier(report, options, body, note-footer: none) = {
  let accent = if options.grayscale { gray.darken(50%) } else { navy }
  set document(title: report.document.title, author: "Formula Finance",
    description: "Dossier editoriale del report budget")
  set text(font: "IBM Plex Sans", lang: "it", size: 9pt, fill: ink)
  set par(leading: 3.5pt, justify: false)
  // Margini dallo style contract (`page.margini`: 17 / 16 / 19 / 16 mm). Il
  // fondo NON è 19 mm: nello spazio sotto il corpo stanno il riquadro di
  // commento (18 mm) e il piè di pagina (10 mm, `page.pie_pagina`), che in
  // Typst vivono nel footer, e perciò richiedono 46 mm. Il corpo guadagna
  // 3 mm in altezza, e nessuna misura del piano editoriale dipende da quel
  // bordo: contano gli slot dei contenuti, non la posizione della pagina.
  set page(paper: "a4", margin: (left: 16mm, right: 16mm, top: 17mm, bottom: 46mm),
    footer-descent: 4mm,
    header: context {
      if counter(page).get().first() > 1 {
        grid(columns: (1fr, auto), column-gutter: 8mm,
          plex(7pt, weight: 500, fill: muted, report.company.name),
          align(right, plex(7pt, fill: muted, report.document.title)))
      }
    },
    footer: context [
      #marker((kind: "page", content_id: "page-shell"))
      #if note-footer == none { note-slot() } else { note-footer() }
      #v(2mm)
      #line(length: 100%, stroke: 0.5pt + rule)
      #v(1mm)
      #grid(columns: (1fr, auto),
        plex(6.8pt, fill: muted)[Riservato e confidenziale · Formula Finance],
        plex(6.8pt, fill: muted, counter(page).display("1 / 1", both: true)))
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

// La riga di contesto sotto il nome dell'azienda (v4: «Bilancio al 30
// settembre 2026 · chiusura attesa 2026 · piano 2027–2029»): percorso,
// scenario di origine, anno base e periodo di piano in una riga sola, dove la
// v4 li mette. Prima erano un blocco «Perimetro del documento» a quattro
// caselle sotto la banda, che la v4 non ha.
#let cover-context(report) = {
  let years = report.document.budget_years
  let plan = if years.len() == 1 { str(years.first()) }
    else { str(years.first()) + "–" + str(years.last()) }
  let workflow = if report.practice.workflow_type == "infrannuale" { "Bilancio infrannuale" }
    else if report.practice.workflow_type == "startup" { "Piano startup" }
    else { "Bilancio annuale" }
  let origin = if report.practice.source_scenario != none {
    let months = report.practice.source_scenario.period_months
    if months == none { report.practice.source_scenario.name }
    else { report.practice.source_scenario.name + " · " + str(months) + " mesi" }
  } else { report.practice.budget_scenario.name }
  (workflow + " · " + origin + " · anno base " + str(report.practice.budget_scenario.base_year)
    + " · piano " + plan)
}

#let cover-heading(report, company-size) = [
    #plex(8pt, fill: white)[REPORT BUDGET]
    #v(7mm)
    #plex(27pt, weight: 600, fill: white, report.document.title)
    #v(7mm)
    #plex(company-size, weight: 500, fill: white, report.company.name)
    #v(3mm)
    #plex(8.5pt, fill: rgb("#9CC0D8"), cover-context(report))
]

// Striscia KPI di copertina (v4): quattro colonne separate da un filo
// verticale, non la striscia di pagina tipo (che i separatori non li ha).
#let cover-kpi-strip(kpis) = context {
  let column-width = body-width / kpis.len()
  // Il valore si adatta alla colonna come nel rail: un KPI lungo
  // («3 anni · 2027–2029») scende di corpo invece di andare a capo e
  // spingere l'etichetta fuori riga.
  // La misura è sulla riga intera, non parola per parola: «3 anni · 2027–2029»
  // ha parole strette e una riga larga, e andando a capo spingeva l'etichetta
  // fuori allineamento rispetto alle altre tre colonne.
  let fits(size) = kpis.all(kpi =>
    measure(plex(size, weight: 600, kpi-text(kpi))).width <= column-width - 10mm)
  let size = if fits(15pt) { 15pt } else if fits(12pt) { 12pt } else { 10pt }
  block(width: body-width, breakable: false)[
    #line(length: 100%, stroke: 0.6pt + rule)
    #v(3.5mm)
    #grid(columns: (1fr,) * kpis.len(), column-gutter: 0mm,
      ..kpis.enumerate().map(((index, kpi)) => block(width: 100%, inset: (
          left: if index == 0 { 0mm } else { 5mm }, right: 5mm))[
        #if index > 0 {
          place(left, dx: -5mm, dy: -1mm, line(angle: 90deg, length: 13mm, stroke: 0.6pt + rule))
        }
        #plex(size, weight: 600, fill: navy, kpi-text(kpi))
        #v(1.2mm)
        #plex(7.8pt, fill: muted, kpi.label)
      ]))
    #v(3.5mm)
    #line(length: 100%, stroke: 0.4pt + rule)
  ]
}

// Indice di copertina (v4: 13 voci su due colonne, col numero di pagina a
// destra). Il numero arriva da Python insieme all'etichetta: il catalogo dà
// una pagina fisica per voce e il piano editoriale lo verifica sul documento
// compilato, quindi non serve risolverlo qui con `query`, che alla prima
// passata di introspezione è vuota. Una sola tabella a quattro colonne, non
// due cicli di blocchi: le righe devono stare in un'altezza data, e un ciclo
// di `v()` non la governa.
#let cover-toc(entries) = {
  let cell(entry) = if entry == none { (none, none) } else {
    (plex(8pt, entry.label), align(right, plex(8pt, weight: 600, str(entry.page))))
  }
  let half = calc.ceil(entries.len() / 2)
  let left-column = entries.slice(0, half)
  let right-column = entries.slice(half)
  let rows = ()
  for index in range(half) {
    let left = cell(left-column.at(index, default: none))
    let right = cell(right-column.at(index, default: none))
    rows += (left.at(0), left.at(1), right.at(0), right.at(1))
  }
  table(columns: (1fr, auto, 1fr, auto), column-gutter: (4mm, 10mm, 4mm),
    inset: (x: 0pt, y: 3pt), stroke: (x, y) => (bottom: 0.4pt + rule), ..rows)
}

#let cover(report, kpis: (), toc: ()) = {
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
  v(8mm)
  plex(7.5pt, fill: blue, weight: 500, tracking: 0.5pt)[REPORT FINALE DELLA PRATICA]
  v(3mm)
  plex(16pt, weight: 600, fill: navy)[Dati di partenza, ipotesi e risultati del piano.]
  linebreak()
  plex(16pt, weight: 600, fill: navy)[Un percorso leggibile e commentato.]
  v(3mm)
  plex(8.5pt, fill: muted)[Sintesi della pratica e delle proiezioni economiche, patrimoniali e finanziarie.]
  if kpis.len() > 0 {
    v(6mm)
    cover-kpi-strip(kpis)
  }
  if toc.len() > 0 {
    v(6mm)
    cover-toc(toc)
  }
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
