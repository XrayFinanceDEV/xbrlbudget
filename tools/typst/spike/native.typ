#import "common.typ": palette, segments, limits
#let render(chart, gray: false) = {
  let colors = palette(gray: gray)
  let (lo, hi) = limits(chart)
  let w = 420pt; let h = 135pt; let ox = 44pt; let oy = 8pt
  let pw = w - ox - 8pt; let ph = h - oy - 24pt
  let xp(i) = ox + (i + 0.5) / chart.categories.len() * pw
  let yp(v) = oy + (hi - v) / (hi - lo) * ph
  box(width: w, height: h)[
    #for k in range(5) {
      let v = lo + k / 4 * (hi - lo)
      place(top + left, dx: ox, dy: yp(v), line(length: pw, stroke: 0.4pt + rgb("dde5e8")))
      place(top + left, dx: 0pt, dy: yp(v) - 4pt, box(width: ox - 5pt, align(right, text(size: 7pt, str(calc.round(v, digits: 1))))))
    }
    #place(top + left, dx: ox, dy: yp(0), line(length: pw, stroke: 0.8pt + rgb("7e939b")))
    #if chart.id == "coverage" {
      place(top + left, dx: ox, dy: yp(1), line(length: pw, stroke: (paint: rgb("b28646"), thickness: 0.8pt, dash: "dashed")))
    }
    #for (si, s) in chart.series.enumerate() {
      for segment in segments(s.values) {
        if chart.id in ("income_results", "cashflows") {
          for (i, v) in segment {
            let bw = pw / chart.categories.len() * 0.7 / chart.series.len()
            let x = xp(i) - pw / chart.categories.len() * 0.35 + si * bw
            place(top + left, dx: x, dy: calc.min(yp(v), yp(0)), rect(width: bw - 1pt, height: calc.max(calc.abs(yp(v) - yp(0)), 0.5pt), fill: colors.at(si), stroke: none))
          }
        } else {
          for j in range(segment.len() - 1) {
            let (a, b) = (segment.at(j), segment.at(j + 1))
            place(top + left, dx: xp(a.at(0)), dy: yp(a.at(1)), line(end: (xp(b.at(0)) - xp(a.at(0)), yp(b.at(1)) - yp(a.at(1))), stroke: (paint: colors.at(si), thickness: 1.6pt, dash: if gray and si == 1 { "dashed" } else { "solid" })))
          }
          for (i, v) in segment {
            place(top + left, dx: xp(i) - 2.5pt, dy: yp(v) - 2.5pt, circle(radius: 2.5pt, fill: colors.at(si)))
          }
        }
      }
    }
    #for (i, y) in chart.categories.enumerate() {
      place(top + left, dx: xp(i) - 15pt, dy: oy + ph + 6pt, text(size: 8pt, str(y)))
    }
  ]
}
