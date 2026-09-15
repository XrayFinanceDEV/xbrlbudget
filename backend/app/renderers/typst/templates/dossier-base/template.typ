#import "base.typ": dossier, cover, appendix
#let report = json("model.json")
#let options = json("options.json")
#show: body => dossier(report, options, body)
#cover(report)
#for statement in report.detailed_statements { appendix(statement) }
