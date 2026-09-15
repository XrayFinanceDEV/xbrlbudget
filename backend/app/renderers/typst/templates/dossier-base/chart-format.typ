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
#let display-value(value, unit) = if value == none { "n.d." } else {
  let raw = str(value)
  let negative = raw.starts-with("-")
  let parts = raw.trim(at: start, "-").split(".")
  let places = precision(unit)
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
  sign + groups.join(".") + "," + decimal
}
#let unit-label(unit) = (eur: "euro", percent: "%", days: "giorni", ratio: "volte", score: "punti").at(unit)
