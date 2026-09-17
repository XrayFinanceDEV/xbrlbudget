// Decimal rounding is string based. Never round through a plotting float.
#let precision(unit) = if unit == "ratio" { 3 } else if unit == "days" { 1 } else { 2 }
#let increment(digits) = {
  let result = ""
  let carry = true
  for digit in digits.clusters().rev() {
    let n = int(digit) + if carry { 1 } else { 0 }
    result = (if n == 10 { "0" } else { str(n) }) + result
    carry = n == 10
  }
  (if carry { "1" } else { "" }) + result
}
// `places` sostituisce la precisione dell'unità: le tabelle editoriali lo usano a 0 per gli euro.
#let display-value(value, unit, places: none) = if value == none { "n.d." } else {
  let raw = str(value)
  let negative = raw.starts-with("-")
  let parts = raw.trim(at: start, "-").split(".")
  let places = if places == none { precision(unit) } else { places }
  let fraction = if parts.len() > 1 { parts.at(1) } else { "" }
  let padded = fraction + "0" * (places + 1)
  let digits = parts.first() + padded.slice(0, places)
  if int(padded.slice(places, places + 1)) >= 5 { digits = increment(digits) }
  let integer = digits.slice(0, digits.len() - places)
  let decimal = digits.slice(digits.len() - places)
  let groups = ()
  while integer.len() > 3 {
    groups.insert(0, integer.slice(integer.len() - 3))
    integer = integer.slice(0, integer.len() - 3)
  }
  groups.insert(0, integer)
  let sign = if negative and not digits.clusters().all(d => d == "0") { "−" } else { "" }
  sign + groups.join(".") + if places == 0 { "" } else { "," + decimal }
}
#let unit-label(unit) = (eur: "euro", percent: "%", days: "giorni", ratio: "volte", score: "punti").at(unit)
// Formattazione dei KPI in colonna (v4, M2-02B): sola manipolazione di stringhe
// decimali, nessuna aritmetica finanziaria nel template. Un KPI che il modello
// non fornisce è omesso nell'inventario: qui non esiste via per il «n.d.».
#let trim-decimals(s) = {
  if s.ends-with(",00") { s.slice(0, s.len() - 3) }
  else if s.contains(",") and s.ends-with("0") { s.slice(0, s.len() - 1) }
  else { s }
}
#let money-short(value) = {
  let raw = str(value)
  let negative = raw.starts-with("-")
  let body = raw.trim(at: start, "-")
  let parts = body.split(".")
  let integer = parts.first()
  let fraction = if parts.len() > 1 { parts.at(1) } else { "" }
  let n = integer.len()
  let shift = if n <= 3 { 0 } else if n <= 6 { 3 } else if n <= 9 { 6 } else { 9 }
  let suffix = if n <= 3 { "" } else if n <= 6 { " mila" } else if n <= 9 { " mln" } else { " mld" }
  let head = if shift == 0 { integer } else { integer.slice(0, integer.len() - shift) }
  let tail = if shift == 0 { fraction } else { integer.slice(integer.len() - shift) + fraction }
  let shifted = (if head == "" { "0" } else { head }) + "." + (tail + "00").slice(0, 2)
  (if negative { "−" } else { "" }) + "€ " + trim-decimals(display-value(shifted, "eur", places: 2)) + suffix
}
#let kpi-format(value, unit) = {
  if unit == none { str(value) }
  else if unit == "eur" { money-short(value) }
  else {
    let plain = display-value(value, unit, places: if unit == "score" { 1 } else { 2 })
    if unit == "percent" { trim-decimals(plain) + "%" }
    else if unit == "ratio" { trim-decimals(plain) + "×" }
    else if unit == "days" { trim-decimals(plain) + " gg" }
    else if unit == "score" { trim-decimals(plain) + " punti" }
    else { trim-decimals(plain) }
  }
}
#let kpi-text(kpi) = if kpi.series != none {
  kpi.series.map(v => kpi-format(v, kpi.unit)).join(" / ")
} else if kpi.to != none {
  kpi-format(kpi.value, kpi.unit) + " → " + kpi-format(kpi.to, kpi.unit)
} else {
  kpi-format(kpi.value, kpi.unit)
}
