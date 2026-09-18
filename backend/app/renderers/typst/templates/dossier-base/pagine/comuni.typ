// Componenti condivisi da tutti i gruppi di pagine del catalogo v4 (M2-02D).
// Ogni pagina del catalogo Python (`dossier_catalog/__init__.py`) è resa da
// `editorial.typ` chiamando `page-header(page)` una volta e poi, per ciascun
// elemento di `page.items`, uno dei componenti qui sotto — dispatch per
// `kind` ("table" · "chart" · "text" · "note" · "index" · "cover").
//
// Un gruppo con un bisogno di resa che questi componenti non coprono (per
// esempio dumbbell/stacked/panel-grid della v4, pagine 12-17: non ancora
// implementate, nessun test le esercita) scrive il proprio componente nel
// proprio file `pagine/<gruppo>.typ`, non qui — questo file resta ciò che
// serve OGGI, dimostrato da una pagina reale, non un catalogo di componenti
// preparati in anticipo.
#import "../base.typ": plex, marker, body-width, rail-width, rail-gutter, rail-main-width, navy, blue, ink, muted, rule, gray-mode, kpi-strip, kpi-column, kpi-rail
#import "../charts.typ": chart-component, value-table, panel-grid
#import "../chart-format.typ": display-value-with-unit

#let safe-prose(size, value, weight: 400, fill: navy, w: body-width) = context {
  if value.split(regex("\\s+")).any(word =>
    measure(plex(size, weight: weight, word)).width > w) {
    panic("editorial-prose-token-does-not-fit")
  }
  plex(size, weight: weight, fill: fill, value)
}

#let cell(value, unit, available: body-width, size: 8pt, fill: ink, weight: 400) = if unit == none {
  // Permit wrapping technical source names at separators without removing text.
  let display = if value == none { "n.d." } else {
    value.replace("_", "_\u{200b}").replace("+", "+\u{200b}")
      .replace("/", "/\u{200b}").replace(".", ".\u{200b}")
  }
  if display.split(regex("[\\s\u{200b}]+")).any(word => measure(plex(size, word)).width > available) {
    panic("editorial-cell-token-does-not-fit")
  }
  plex(size, fill: fill, weight: weight, display)
} else {
  // Euro interi nelle tabelle (decisione del proprietario, 2026-09-17); ogni
  // altra unità porta il proprio suffisso nella stessa cella («17,75%»,
  // «7,57×», «228,12 gg» — v4, Allegati F/G e i grafici di indicatori.py).
  let display = plex(size, fill: fill, weight: weight, display-value-with-unit(value, unit, places: if unit == "eur" { 0 } else { none }))
  if measure(display).width > available { panic("editorial-amount-does-not-fit") }
  display
}

#let heading(item) = [
  #marker((kind: "content", content_id: "heading:" + item.id))
  #safe-prose(14pt, weight: 600, fill: navy, item.title)
  #v(2mm)
]

// Riga «totale» alla maniera della v4: le voci che chiudono un blocco
// (Totale…, EBITDA, Risultato netto, Cassa finale) sono in grassetto e
// separate da un filo più marcato sopra, invece di una banda colorata.
#let total-row(label) = label != none and (
  label.starts-with("Totale") or label in ("EBITDA", "EBIT", "Risultato netto",
    "Risultato ante imposte", "Cassa finale", "Patrimonio netto"))

// Il catalogo v4 tiene ogni tabella a un massimo di 5 colonne di valore (vincolo
// del proprietario, 2026-09-17): questo dispatcher non spacca più per periodi
// in verticale (`compact-period-table`/`value_start`/`part_size` del vecchio
// inventario generico non servono a nessuna pagina di questa fase — un gruppo
// che tornasse a servirne uno, per esempio le tabelle F/G, se lo scrive da sé,
// prendendo questa funzione a modello). Resta il ramo impilato per etichette
// lunghe o importi che non entrano nella colonna.
#let data-table(spec, item, w: body-width) = context {
  let count = item.columns.len()
  let label-width = if count <= 3 { calc.min(65mm, w * 0.42) } else { calc.min(60mm, w * 0.40) }
  let column-width = (w - label-width) / calc.max(1, count - 1)
  let token-ok = (value, width) => value == none or value.split(regex("\\s+")).all(word =>
    measure(plex(8pt, word)).width <= width)
  let amount-ok = (value, unit, width) => (value == none or
    measure(plex(8pt, display-value-with-unit(value, unit, places: if unit == "eur" { 0 } else { none }))).width <= width)
  let cell-ok = (value, unit, width) => if unit == none { token-ok(value, width) } else { amount-ok(value, unit, width) }
  let fits = count >= 2 and item.rows.all(r =>
    token-ok(r.cells.at(0), label-width - 6pt) and
    r.cells.enumerate().all(pair => pair.at(0) == 0 or
      cell-ok(pair.at(1), r.units.at(pair.at(0)), column-width - 6pt)))
  if fits {
    let cells = ()
    for row in item.rows {
      let total = total-row(row.cells.at(0))
      for (index, value) in row.cells.enumerate() {
        cells.push(table.cell(breakable: false,
          stroke: if total { (top: 0.7pt + ink) } else { (:) })[
          #if index == 0 { marker((kind: "content", content_id: row.id)) }
          #cell(value, row.units.at(index),
            available: if index == 0 { label-width - 8pt } else { column-width - 8pt },
            fill: if total { navy } else { ink }, weight: if total { 600 } else { 400 })
        ])
      }
    }
    // Griglia della v4: intestazione 7,2 pt/500 muted con un filo scuro sotto,
    // righe da 4 pt di respiro separate da un filo chiaro, numeri a destra.
    // Nessun fondo colorato: la gerarchia la fanno i fili e il peso.
    table(columns: (label-width, ..((column-width,) * (count - 1))),
      inset: (x: 4pt, y: 4pt),
      align: (column, row) => if column == 0 { left } else { right },
      stroke: (column, row) => (left: none, right: none, top: none,
        bottom: if row == 0 { 0.7pt + ink } else { 0.5pt + rule }),
      table.header(..item.columns.map(c => plex(7.2pt, weight: 500, fill: muted, c))),
      ..cells)
  } else {
    // Long labels, large exact amounts: room to wrap, label | "col: value" lines.
    let label-column = calc.min(65mm, w * 0.45)
    let cells = ()
    for row in item.rows {
      cells.push(table.cell(breakable: false)[
        #marker((kind: "content", content_id: row.id))
        #cell(row.cells.first(), row.units.first(), available: label-column - 6pt)
      ])
      cells.push(table.cell(breakable: false)[
        #for index in range(1, count) {
          plex(7pt, weight: 600, fill: muted, item.columns.at(index) + ": ")
          cell(row.cells.at(index), row.units.at(index), available: w - label-column - 6pt)
          if index < count - 1 { linebreak() }
        }
      ])
    }
    table(columns: (label-column, w - label-column), inset: (x: 4pt, y: 4pt),
      stroke: (column, row) => (left: none, right: none, top: none,
        bottom: if row == 0 { 0.7pt + ink } else { 0.5pt + rule }),
      table.header(
        plex(7.2pt, weight: 500, fill: muted, item.columns.first()),
        plex(7.2pt, weight: 500, fill: muted)[Valori]),
      ..cells)
  }
}

#let table-block(spec, item, w: body-width) = {
  block(sticky: true, heading(item))
  data-table(spec, item, w: w)
  v(5mm)
}

// Pagina tipo (v4, M2-02B · forma di pagina M2-02G fase 2 punto 4): la colonna
// KPI accanto al grafico è il comportamento storico di una pagina `single`; in
// una pagina `rail+main` i KPI stanno nel rail della pagina e il grafico occupa
// la colonna principale (126 mm), in una `full+panels` due grafici si affiancano
// a 86 mm. La larghezza la dichiara Python in `width_mm` (è la stessa che
// `editorial_plan.py` rivuole nel marcatore), qui si legge soltanto.
#let chart-figure(item, gray: false, indicators: (), w: body-width) = {
  let has-kpi = "kpis" in item and item.kpis.len() > 0
  let width-mm = if "width_mm" in item { str(item.width_mm) }
    else if has-kpi { "118" } else { none }
  let show-values = "value_table" not in item or item.value_table
  [
    #safe-prose(14pt, weight: 600, fill: navy, item.title)
    #v(3mm)
    #if has-kpi {
      grid(columns: (55mm, w - 55mm - 5mm), column-gutter: 5mm,
        kpi-column(item.kpis),
        chart-component(item.chart, gray: gray, indicators: indicators, width-mm: width-mm))
    } else {
      chart-component(item.chart, gray: gray, indicators: indicators, width-mm: width-mm)
    }
    // La tabellina dei valori sotto il grafico (traccia A, punto 5) è il
    // comportamento storico delle pagine che non dichiarano forma: nella v4 i
    // numeri stanno solo nelle tavole di pagina, e una pagina `rail+main` o
    // `full+panels` la numeri duplicati non li deve avere.
    #if show-values {
      v(4mm)
      value-table(item.chart, places: if item.chart.unit == "eur" { 0 })
    }
  ]
}

#let chart-block(item, gray: false, indicators: (), w: body-width) = {
  let figure = chart-figure(item, gray: gray, indicators: indicators, w: w)
  context {
    if measure(block(width: w, figure)).height > 220mm {
      panic("editorial-chart-with-values-does-not-fit")
    }
    block(width: w, breakable: false, figure)
  }
  v(5mm)
}

// `panel_grid` (traccia A, punto 3): il blocco unico che la v4 chiama
// «pannelli affiancati». I figli restano chart-item normali, con il proprio
// marcatore e la propria larghezza dichiarata da Python.
#let panel-block(item, gray: false, indicators: (), w: body-width) = {
  let children = item.items.map(child => chart-figure(child, gray: gray,
    indicators: indicators, w: (w - 6mm) / calc.max(1, item.items.len())))
  context {
    if measure(block(width: w, panel-grid(..children))).height > 220mm {
      panic("editorial-panel-grid-does-not-fit")
    }
    block(width: w, breakable: false, panel-grid(..children))
  }
  v(5mm)
}

#let text-block(item, w: body-width) = {
  let content = [
    #marker((kind: "content", content_id: item.id))
    #safe-prose(14pt, weight: 600, fill: navy, item.title)
    #v(2mm)
    #safe-prose(9pt, fill: muted, item.text, w: w)
  ]
  context {
    if measure(block(width: w, content)).height > 220mm { panic("editorial-text-does-not-fit") }
    block(width: w, breakable: false, content)
  }
  v(5mm)
}

#let note-block(item, w: body-width) = {
  // Nota compatta senza titolo di sezione, stile metadati.
  let content = [
    #marker((kind: "content", content_id: item.id))
    #safe-prose(7.2pt, fill: muted, item.text, w: w)
  ]
  context {
    if measure(block(width: w, content)).height > 220mm { panic("editorial-availability-note-does-not-fit") }
    block(width: w, breakable: false, content)
  }
  v(3mm)
}

// Indice a link-list (v4 pagina 19): ogni voce risolve la propria pagina
// fisica dal vivo via `query(metadata)`, senza che Python debba conoscere in
// anticipo su quale pagina finirà ciascun allegato.
#let index-block(item, w: body-width) = context {
  marker((kind: "content", content_id: item.id))
  safe-prose(14pt, weight: 600, fill: navy, item.title)
  v(2mm)
  let values = query(metadata).map(node => node.value)
  let page-of(id) = {
    let hits = values.filter(v => v.kind == "content" and v.content_id == id)
    if hits.len() == 0 { none } else { hits.first().page }
  }
  for entry in item.entries {
    let number = page-of(entry.target)
    if number == none { panic("index-entry-without-target-page") }
    grid(columns: (1fr, auto), plex(8pt, entry.label), plex(8pt, weight: 600, str(number)))
    v(1mm)
    line(length: 100%, stroke: 0.4pt + rule)
    v(1.5mm)
  }
}

// Intestazione di pagina tipo: occhiello (gruppo · numero pagina), titolo
// neutro, sottotitolo di metodo, striscia KPI orizzontale. Una pagina fisica
// per voce del catalogo: `pagebreak()` qui, mai dentro il ciclo degli item.
//
// In una pagina `rail+main` la striscia non si disegna: gli stessi KPI
// scendono nel rail a sinistra del contenuto (traccia A, punto 4), e
// disegnarli due volte sarebbe un duplicato, non un rinforzo.
#let page-header(spec) = {
  pagebreak()
  context {
    let number = counter(page).get().first()
    plex(7.5pt, weight: 500, fill: blue, tracking: 0.5pt,
      upper(spec.family) + " · " + (if number < 10 { "0" } else { "" }) + str(number))
  }
  v(5pt)
  safe-prose(16pt, weight: 600, fill: navy, spec.title)
  v(5pt)
  if spec.subtitle != none {
    safe-prose(9pt, fill: muted, spec.subtitle)
  }
  v(11pt)
  if spec.kpis.len() > 0 and spec.form != "rail+main" {
    kpi-strip(spec.kpis)
    v(5mm)
  }
}

#let render-item(spec, item, report, options, w: body-width) = {
  if item.kind == "table" { table-block(spec, item, w: w) }
  else if item.kind == "chart" { chart-block(item, gray: options.grayscale, indicators: report.indicator_catalog, w: w) }
  else if item.kind == "panel" { panel-block(item, gray: options.grayscale, indicators: report.indicator_catalog, w: w) }
  else if item.kind == "note" { note-block(item, w: w) }
  else if item.kind == "index" { index-block(item, w: w) }
  else { text-block(item, w: w) }
}

// Render di una pagina: il dispatcher `rail+main` mette il rail (colonna da
// 47 mm) accanto ai soli blocchi che la dichiarano — la `.row` della v4, non
// l'intera pagina — e lascia il resto a larghezza intera.
#let render-page(spec, report, options) = {
  page-header(spec)
  let items = spec.items
  let index = 0
  while index < items.len() {
    let item = items.at(index)
    let in-rail = "rail" in item and item.rail
    if in-rail {
      // Una corsa di blocchi contigui `rail: true` finisce dentro la `.row`.
      let end = index
      while end < items.len() and "rail" in items.at(end) and items.at(end).rail {
        end = end + 1
      }
      grid(columns: (rail-width, rail-main-width), column-gutter: rail-gutter,
        kpi-rail(spec.rail),
        {
          for position in range(index, end) {
            render-item(spec, items.at(position), report, options, w: rail-main-width)
          }
        })
      index = end
    } else {
      render-item(spec, item, report, options)
      index = index + 1
    }
  }
}

// Dispatch di un elemento di pagina per `kind` — tranne "cover", che
// `editorial.typ` rende direttamente con `cover()` di `base.typ` (ha bisogno
// dell'intero `report`, non solo dell'item). `report`/`options` vengono
// passati dal chiamante, mai letti da variabili globali qui.
