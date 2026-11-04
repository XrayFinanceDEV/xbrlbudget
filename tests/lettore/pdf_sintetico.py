"""PDF sintetici per i test del lettore: testo posato a coordinate esatte, nel riferimento visualizzato."""
import fitz

from importers.lettore import leggi_importo

_CORPO = 9.0


def scrivi_pdf(path, pagine, *, a_destra=True, rotazione=0, larghezza=595, altezza=842):
    """Scrive `pagine` (liste di `(x, y, testo)`) in `path`.

    `y` e' la linea di base nel riferimento visualizzato. Con `a_destra` la x e' il bordo destro dei token
    che sono importi, il sinistro degli altri. Con `rotazione` la pagina e' ruotata, e il testo e' scritto
    in modo che a schermo resti orizzontale.
    """
    doc = fitz.open()
    for voci in pagine:
        pagina = doc.new_page(width=larghezza, height=altezza)
        if rotazione:
            pagina.set_rotation(rotazione)
        for x, y, testo in voci:
            if a_destra and leggi_importo(testo) is not None:
                x = x - fitz.get_text_length(testo, fontsize=_CORPO)
            punto = fitz.Point(x, y) * pagina.derotation_matrix
            pagina.insert_text(punto, testo, fontsize=_CORPO, rotate=(-rotazione) % 360)
    doc.save(str(path))
    doc.close()
