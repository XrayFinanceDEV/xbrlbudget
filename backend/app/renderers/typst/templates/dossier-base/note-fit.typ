// Fixed native measurement for literal editorial footer comments.
#import "base.typ": plex, muted
#let input = json("note-fit-input.json")
#set text(font: "IBM Plex Sans", lang: "it", size: 9pt)
#set par(leading: 3pt, justify: false)

#for note in input.notes {
  context {
    let width = float(note.width_pt) * 1pt
    let height = float(note.height_pt) * 1pt
    let text-body = plex(float(note.font_size_pt) * 1pt, fill: muted, note.text)
    let measured = measure(block(width: width, text-body))
    let overflow = note.text.split(regex("\\s+")).any(word =>
      measure(plex(float(note.font_size_pt) * 1pt, word)).width > width)
    let fits = note.text != "" and measured.height <= height and note.text.split("\n").len() <= note.max_lines and not overflow
    metadata((id: note.id, fits: fits, width_pt: note.width_pt, height_pt: note.height_pt,
      font_size_pt: note.font_size_pt, max_lines: note.max_lines))
  }
}
