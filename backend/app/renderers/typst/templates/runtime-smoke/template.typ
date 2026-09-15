// Runtime acceptance template only. The complete dossier is implemented later.
#let report = json("model.json")
#let options = json("options.json")
#set document(title: report.document.title, author: "Formula Finance")
#set text(font: "Libertinus Serif", lang: "it", size: 11pt)
#set page(paper: "a4", margin: 20mm,
  background: if options.document_state == "draft" {rotate(-35deg, text(60pt, fill: gray.lighten(65%), [BOZZA]))},
  footer: context align(right, counter(page).display("1")))
#text(25pt, weight: "bold", report.document.title)
#parbreak()
#report.company.name
#parbreak()
#report.practice.budget_scenario.name
#parbreak()
Verifica del runtime di compilazione. Il dossier definitivo segue il piano editoriale.
#parbreak()
Hash del modello: #report.model_hash
