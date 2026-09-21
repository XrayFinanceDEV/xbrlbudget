// Report intermedio della pratica (infrannuale + indicatori della crisi
// d'impresa). Stesso impianto del dossier finale per costruzione: colori,
// caratteri, rail, blocchi, tabelle e grafici vengono da `base.typ` e
// `pagine/comuni.typ` del bundle `dossier-base`, letti e verificati byte per
// byte (`intermedio_renderer.IntermedioTemplateBundle`). Qui stanno solo le
// due cose che l'intermedio fa diversamente:
// - il frontespizio, con i testi del report intermedio;
// - il commento di pagina: uno dei sei commenti AI dell'infrannuale, lungo
//   fino a ~750 caratteri, che nel riquadro da quattro righe del finale non
//   entra. Sta in fondo al corpo, con lo stesso titolo e lo stesso filo, alto
//   quanto il testo; il piè di pagina perde il riquadro e il corpo guadagna
//   quello spazio.
#import "base.typ": plex, marker, body-width, page-width, navy, blue, ink, muted, rule, cover-kpi-strip, cover-toc
#import "pagine/comuni.typ": render-page, page-header, block-title, safe-prose
#let report = json("model.json")
#let options = json("options.json")
#let inventory = json("editorial-inventory.json")

#let intermedio(report, options, body) = {
  let accent = if options.grayscale { gray.darken(50%) } else { navy }
  set document(title: report.document.title, author: "Formula Finance",
    description: "Report intermedio della pratica")
  set text(font: "IBM Plex Sans", lang: "it", size: 9pt, fill: ink)
  set par(leading: 3.5pt, justify: false)
  set page(paper: "a4", margin: (left: 16mm, right: 16mm, top: 17mm, bottom: 22mm),
    footer-descent: 4mm,
    header: context {
      if counter(page).get().first() > 1 {
        grid(columns: (1fr, auto), column-gutter: 8mm,
          plex(7pt, weight: 500, fill: muted, report.company.name),
          align(right, plex(7pt, fill: muted, report.document.title)))
      }
    },
    footer: context [
      #line(length: 100%, stroke: 0.5pt + rule)
      #v(1mm)
      #grid(columns: (1fr, auto),
        plex(6.8pt, fill: muted)[Riservato e confidenziale · Formula Finance],
        plex(6.8pt, fill: muted, counter(page).display("1 / 1", both: true)))
    ],
    background: context {
      if counter(page).get().first() == 1 {
        place(top + left, rect(width: page-width, height: 108mm, fill: accent, stroke: none))
      }
      if options.document_state == "draft" {
        place(center + horizon, rotate(-35deg,
          plex(78pt, weight: 600, fill: gray.lighten(75%))[BOZZA]))
      }
    })
  body
}

#let cover-heading(report, company-size) = [
  #plex(8pt, fill: white)[REPORT INFRANNUALE]
  #v(7mm)
  #plex(27pt, weight: 600, fill: white, report.document.title)
  #v(7mm)
  #plex(company-size, weight: 500, fill: white, report.company.name)
  #v(3mm)
  #plex(8.5pt, fill: rgb("#9CC0D8"), report.document.context)
]

#let cover(report, kpis: (), toc: ()) = {
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
  plex(7.5pt, fill: blue, weight: 500, tracking: 0.5pt)[REPORT INTERMEDIO DELLA PRATICA]
  v(3mm)
  plex(16pt, weight: 600, fill: navy)[Situazione infrannuale e proiezione a fine anno.]
  linebreak()
  plex(16pt, weight: 600, fill: navy)[Indicatori della crisi d'impresa.]
  v(3mm)
  plex(8.5pt, fill: muted)[Il periodo osservato a confronto con l'anno di riferimento, la sua proiezione a dodici mesi e la classe di rischio.]
  if kpis.len() > 0 {
    v(6mm)
    cover-kpi-strip(kpis)
  }
  if toc.len() > 0 {
    v(6mm)
    cover-toc(toc)
  }
}

// Il commento del consulente, in fondo alla pagina: `v(1fr)` lo porta dove il
// finale ha il riquadro, e un commento che non entra nella pagina la fa
// traboccare — `IntermedioRenderer` lo rifiuta contando le pagine.
#let commento(testo) = if testo != "" {
  v(1fr)
  block(width: body-width, breakable: false)[
    #line(length: 100%, stroke: 0.7pt + rule)
    #v(2pt)
    #plex(8pt, weight: 600, fill: navy)[Lettura del consulente]
    #if report.document.commenti_stantii {
      h(2mm)
      plex(7pt, fill: muted)[· scritto prima dell'ultima proiezione]
    }
    #v(3pt)
    #safe-prose(9pt, fill: muted, testo)
  ]
}

// I sette segnali extracontabili come nella Stampa: casella, numero, testo.
// Il testo e' lungo (fino a ~250 caratteri) e non sta in una colonna di
// tabella del dossier; un segnale attivo ha la casella piena e il testo in
// inchiostro, uno spento il testo attenuato. «attivo» e' scritto anche in
// parole, perche' in scala di grigi il colore non basta.
#let segnali-block(item) = {
  block-title(item.title)
  v(2mm)
  for entry in item.entries {
    let box-fill = if entry.attivo { if options.grayscale { ink } else { rgb("#B42318") } } else { none }
    let box-stroke = if entry.attivo { none } else { 0.7pt + muted }
    block(width: body-width, breakable: false, spacing: 0pt)[
      #grid(columns: (6mm, 1fr, 18mm), column-gutter: 3mm,
        box(width: 3.4mm, height: 3.4mm, fill: box-fill, stroke: box-stroke, radius: 0.6pt,
          if entry.attivo { align(center + horizon, plex(7pt, weight: 600, fill: white)[✓]) }),
        plex(8.5pt, fill: if entry.attivo { ink } else { muted }, weight: if entry.attivo { 500 } else { 400 },
          str(entry.n) + ". " + entry.label),
        align(right, plex(7.5pt, weight: 600, fill: if entry.attivo { navy } else { muted },
          if entry.attivo { "attivo" } else { "non attivo" })))
      #v(2.5mm)
      #line(length: 100%, stroke: 0.5pt + rule)
      #v(2.5mm)
    ]
  }
}

#show: body => intermedio(report, options, body)
#for spec in inventory {
  if spec.id == "cover" {
    cover(report, kpis: spec.kpis, toc: spec.at("toc", default: ()))
  } else if spec.id == "segnali" {
    page-header(spec)
    for item in spec.items { segnali-block(item) }
  } else {
    render-page(spec, report, options)
    commento(spec.at("comment", default: ""))
  }
}
