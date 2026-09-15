#import "common.typ": value, legend, chart-table, plot-note
#import "native.typ" as native
#let candidate = sys.inputs.at("candidate", default: "native")
#let graph = if candidate == "native" { native.render } else if candidate == "cetz" {
  import "cetz.typ" as cetz
  cetz.render
} else {
  import "primaviz.typ" as prima
  prima.render
}
#let model = json(sys.inputs.at("model", default: "startup.json"))
#let draft = sys.inputs.at("state", default: "final") == "draft"
#let gray = sys.inputs.at("gray", default: "false") == "true"
#let ink = rgb("153f4d")
#set document(title: "Report finale della pratica — " + model.practice.workflow_type, author: "Xray Finance · campione sintetico")
#set page(paper: "a4", margin: (top: 20mm, bottom: 19mm, x: 22mm),
  header: text(size: 8pt, fill: ink)[XRAY FINANCE #h(1fr) REPORT FINALE DELLA PRATICA],
  footer: context {
    line(length: 100%, stroke: 0.4pt + rgb("ccd7dc"))
    v(4pt)
    text(size: 7pt, fill: rgb("60747d"))[Campione sintetico · #model.practice.workflow_type #h(1fr) #counter(page).display("1") / #counter(page).final().first()]
  },
  background: if draft { rotate(-35deg, text(size: 100pt, fill: rgb("e9edef"), weight: "bold")[BOZZA]) } else { none }
)
#set text(font: "Libertinus Serif", size: 10pt, lang: "it", fill: rgb("23343c"))
#set par(justify: true, leading: 0.65em)
#set heading(numbering: none)
#show table.cell: it => {
  set par(justify: false)
  it
}
#set table(stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")))
#show heading.where(level: 1): it => block(above: 16pt, below: 10pt, sticky: true)[
  #text(size: 21pt, weight: "bold", fill: ink, it.body)
]
#show heading.where(level: 2): it => block(above: 12pt, below: 6pt, sticky: true)[
  #text(size: 13pt, weight: "bold", fill: ink, it.body)
]
#let narrative(id) = {
  for n in model.narrative.filter(n => n.id == id) { n.text; v(8pt) }
}
#let chart(id) = {
  let c = model.chart_series.find(c => c.id == id)
  block(breakable: false)[
    #text(size: 12pt, weight: "bold", fill: ink, c.title)
    #v(8pt)
    #graph(c, gray: gray)
    #v(8pt)
    #legend(c, gray: gray)
    #v(6pt)
    #plot-note(c)
  ]
  v(8pt)
  chart-table(c)
  v(12pt)
}
#let statement(field) = {
  let years = model.forecast.years
  let codes = years.map(y => y.at(field).map(l => l.code)).flatten().dedup()
  table(columns: (1.8fr, ..years.map(_ => 1fr)), inset: 6pt,
    stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")),
    table.header([*Voce · EUR*], ..years.map(y => strong(str(y.year)))),
    ..codes.map(code => {
      let label = years.map(y => y.at(field)).flatten().find(l => l.code == code).label
      (text(size: 8pt, label), ..years.map(y => {
        let l = y.at(field).find(l => l.code == code)
        align(right, if l == none { [n.d.] } else { value(l.value) })
      }))
    }).flatten()
  )
}
#v(28mm)
#text(size: 10pt, tracking: 2pt, fill: rgb("b28646"))[ANALISI E PIANIFICAZIONE FINANZIARIA]
#v(10mm)
#text(size: 42pt, weight: "bold", fill: ink)[Report finale\ della pratica]
#v(8mm)
#text(size: 16pt, model.company.name)
#v(14mm)
#line(length: 50mm, stroke: 2pt + rgb("b28646"))
#v(8mm)
#text(size: 12pt)[Percorso: *#model.practice.workflow_type*]
#v(3mm)
#text(size: 12pt)[Orizzonte: *#model.practice.periods.forecast_years.map(str).join(" · ")*]
#v(3mm)
#text(size: 12pt)[Stato del documento: *#if draft { [BOZZA] } else { [FINALE · CAMPIONE] }*]
#v(16mm)
#block(fill: rgb("f0f4f5"), inset: 12pt, width: 100%)[
  *Dati interamente sintetici.* Anteprima editoriale per validare il report.
  I valori sono test tipografici e non rappresentano un'impresa reale.
]
#pagebreak()
#heading(level: 1, outlined: false)[Indice del report]
#outline(title: none, depth: 1)
#v(12pt)
Importi in euro salvo diversa indicazione. I valori non disponibili restano n.d.
Le sezioni non applicabili al percorso sono omesse.
= 02 · Sintesi esecutiva
#narrative("executive_summary")
#statement("income_statement")
= 03 · Origine e qualità dei dati
Percorso #model.practice.workflow_type. Qualità delle fonti: #model.source_data_quality.status.
Stato del modello: #model.readiness.status.
#v(6pt)
#for r in model.source_revisions {
  [*#r.source* — #r.identifier · revisione #r.revision]; v(5pt)
}
= 04 · Rettifiche apportate
#narrative("adjustments_and_closing")
#table(columns: (0.5fr, 2.5fr, 0.8fr), inset: 6pt,
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")),
  table.header([*Rif.*], [*Rettifica e motivazione*], [*Delta EUR*]),
  ..model.adjustments.entries.enumerate().map(((i, a)) => (
    str(i + 1), [#a.edited_label\ #text(size: 8pt, fill: rgb("60747d"), a.explanation)], align(right, value(a.edit_delta))
  )).flatten()
)
Effetto netto dichiarato dal modello: #value(model.adjustments.net_effect) EUR.
#if model.practice.workflow_type == "infrannuale" {
  heading(level: 1)[05 · Dall'infrannuale alla chiusura]
  [Confronto tra progressivo, proiezione e chiusura attesa.]
  let closing = model.at("infrannual_closing", default: none)
  if closing != none {
    [Periodo osservato fino al #closing.period_end.]
    v(8pt)
    table(columns: (1.4fr, 1fr, 1fr, 1fr), inset: 6pt, stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")),
      table.header([*Voce*], [*Progressivo*], [*Proiezione*], [*Chiusura*]),
      ..closing.values.map(l => (l.label, value(l.observed), value(l.automatic), value(l.closing_used))).flatten())
    v(8pt)
    [Segnali extra-contabili dichiarati:]
    for (k, flag) in closing.extra_accounting_alerts.pairs() {
      [#k: #if flag { [presente] } else { [assente] }. ]
    }
  }
}
= 06 · Ipotesi del budget
#narrative("budget_assumptions")
#for section in model.assumption_sections {
  heading(level: 2, section.title)
  for a in section.assumptions {
    [*#a.label* · origine: #a.provenance]; v(4pt)
    [Valori per anno: #a.values.map(value).join([ · ])]; v(6pt)
    let loans = if a.financing_loans == none { () } else { a.financing_loans }
    if loans.len() > 0 {
      table(columns: (2fr, 1fr, 1fr, 0.5fr, 0.6fr), inset: 5pt,
        table.header([*Finanziamento*], [*Importo EUR*], [*Residuo EUR*], [*Anni*], [*Tasso %*]),
        ..loans.map(loan => (text(size: 8pt, loan.name), align(right, value(loan.amount)), align(right, value(loan.opening_residual)), str(loan.duration_years), value(loan.interest_rate))).flatten())
    }
    let differences = if a.temporary_differences == none { () } else { a.temporary_differences }
    if differences.len() > 0 {
      table(columns: (2fr, 1fr, 1fr), inset: 5pt, stroke: (left: none, right: none, top: none, bottom: 0.4pt + rgb("d8e0e3")),
        table.header([*Differenza temporanea*], [*Apertura EUR*], [*Aliquota %*]),
        ..differences.map(d => (text(size: 8pt, d.name), align(right, value(d.opening_amount)), align(right, value(d.tax_rate)))).flatten())
    }
  }
}
= 07 · Conto economico previsionale
#narrative("economic_outlook")
#statement("income_statement")
#v(12pt)
#chart("income_results")
#chart("margins")
= 08 · Stato patrimoniale previsionale
#statement("balance_sheet")
#v(12pt)
#chart("liquidity_debt")
= 09 · Flussi di cassa e sostenibilità finanziaria
#narrative("financial_outlook")
#statement("cashflow")
#v(12pt)
#chart("cashflows")
#chart("coverage")
= 10 · Indicatori e rischi
#narrative("risks_and_actions")
#chart("working_capital_days")
= 11 · Diagnostica e punti da verificare
#for d in model.diagnostics {
  [*#d.severity* · #d.message]; v(6pt)
}
= 12 · Appendici e metodologia
Il renderer legge soltanto il modello canonico. Non genera previsioni o commenti,
non completa valori mancanti e non esegue formule finanziarie.
#v(8pt)
#text(size: 8pt)[Schema: #model.schema_version\
Hash modello: #model.model_hash\
Hash fonti: #model.source_hash]
#v(12pt)
== Matrice delle ipotesi strutturate
#let flatten(data, prefix: "") = {
  if type(data) == dictionary {
    data.pairs().map(((k, val)) => flatten(val, prefix: if prefix == "" { k } else { prefix + " · " + k })).flatten()
  } else if type(data) == array {
    data.enumerate().map(((i, val)) => flatten(val, prefix: prefix + " · " + str(i + 1))).flatten()
  } else {
    ((prefix, if data == none { [n.d.] } else { str(data) }),)
  }
}
#for section in model.assumption_sections {
  for a in section.assumptions {
    for key in ("ce_overrides", "sp_indexing", "pregresso") {
      let data = a.at(key, default: none)
      if data != none {
        heading(level: 2, a.label)
        table(columns: (2fr, 1fr), inset: 5pt,
          table.header([*Parametro*], [*Valore dichiarato*]),
          ..flatten(data).flatten())
      }
    }
  }
}
