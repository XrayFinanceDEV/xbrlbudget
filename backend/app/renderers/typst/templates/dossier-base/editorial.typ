// Dispatcher del catalogo fisso v4 (M2-02D). L'inventario che arriva da
// `dossier_catalog.build_inventory()` è già una lista di PAGINE — non di
// sezioni che il template deve ancora impaginare: ogni pagina porta
// esattamente il contenuto della v4 per quel numero di pagina, e ha diritto
// a esattamente una `pagebreak()`. Il layout di ciascun blocco (tabella,
// grafico, testo, nota, indice) vive in `pagine/comuni.typ`; un gruppo con un
// bisogno di resa che quel file non copre lo scrive nel proprio
// `pagine/<gruppo>.typ` (vedi quei file per lo stato attuale).
#import "base.typ": dossier, cover, body-width, navy, muted, rule, plex, marker
#import "pagine/comuni.typ": page-header, render-item
#let report = json("model.json")
#let options = json("options.json")
#let inventory = json("editorial-inventory.json")
#let note-text-height = 18mm
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
#for page in inventory {
  if page.id != "cover" {
    page-header(page)
  }
  for item in page.items {
    if item.kind == "cover" {
      cover(report, kpis: page.kpis)
    } else {
      render-item(page, item, report, options)
    }
  }
}
