#import "@preview/cetz:0.5.2"
#import "@preview/cetz-plot:0.1.4": plot
#import "common.typ": palette, segments, limits
#let render(chart, gray: false) = {
  let colors = palette(gray: gray)
  let (lo, hi) = limits(chart)
  cetz.canvas(length: 1pt, {
    plot.plot(size: (370, 110), axis-style: "scientific-auto",
      x-min: -0.5, x-max: chart.categories.len() - 0.5, y-min: lo, y-max: hi,
      x-tick-step: none, x-ticks: chart.categories.enumerate().map(((i, y)) => (i, text(size: 8pt, str(y)))),
      y-grid: true, y-format: v => text(size: 7pt, str(calc.round(v, digits: 1))), legend: none,
      {
        plot.add-hline(0, style: (stroke: 0.6pt + rgb("7e939b")))
        if chart.id == "coverage" {
          plot.add-hline(1, style: (stroke: (paint: rgb("b28646"), thickness: 0.8pt, dash: "dashed")))
        }
        for (si, s) in chart.series.enumerate() {
          for segment in segments(s.values) {
            if chart.id in ("income_results", "cashflows") {
              let bw = 0.7 / chart.series.len()
              plot.add-bar(segment.map(((i, v)) => (i - 0.35 + (si + 0.5) * bw, v)),
                bar-width: bw * 0.95, style: (fill: colors.at(si), stroke: none))
            } else {
              plot.add(segment, mark: "o", mark-size: 4,
                style: (stroke: 1.6pt + colors.at(si)), mark-style: (fill: colors.at(si), stroke: none))
            }
          }
        }
      }
    )
  })
}
