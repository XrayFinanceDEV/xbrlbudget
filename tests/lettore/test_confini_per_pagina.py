"""Sezioni contrapposte con il confine che si sposta da una pagina all'altra (un export da foglio di calcolo stampato
in PDF): l'importo di sinistra sta a una x sulla pagina dello stato patrimoniale e a un'altra su quella del conto
economico, e i codici di destra cominciano subito dopo. Importi senza punto delle migliaia, interi senza centesimi.
Cifre inventate."""
from decimal import Decimal

import fitz

from importers.lettore.righe import leggi_pdf
from tests.lettore.pdf_sintetico import scrivi_pdf

_CORPO = 9.0
_RIGHE = 14


def _a_destra(x: float, testo: str) -> tuple[float, float, str]:
    """Il token col bordo destro a x (anche un intero nudo, che `scrivi_pdf` allineerebbe a sinistra)."""
    return x - fitz.get_text_length(testo, fontsize=_CORPO), 0.0, testo


def _pagina(sezione: str, x_codice: float, x_importo: float, base: int) -> list[tuple[float, float, str]]:
    voci = []
    for k in range(_RIGHE):
        y = 120 + k * 14
        sinistro = f"{base + 1000 * k + 7}" if k % 4 == 0 else f"{base + 1000 * k + 7},{k + 10}"
        destro = f"{2 * base + 900 * k + 3},{k + 20}"
        x, _, t = _a_destra(x_importo, sinistro)
        voci += [(x_codice, y, f"0{k + 1}05005"), (x_codice + 40, y, f"{sezione} sinistra {k + 1}"), (x, y, t)]
        x, _, t = _a_destra(560, destro)
        voci += [(x_importo + 4, y, f"2{k + 1}05005"), (x_importo + 46, y, f"{sezione} destra {k + 1}"), (x, y, t)]
    return voci


def _documento(tmp_path):
    p = tmp_path / "foglio.pdf"
    scrivi_pdf(p, [_pagina("Conto", 20, 300, 3000), _pagina("Voce", 40, 332, 5000)], a_destra=False)
    return leggi_pdf(str(p))


def test_il_confine_di_ogni_pagina_e_la_colonna_spostata(tmp_path):
    doc = _documento(tmp_path)
    prof = doc.profilo
    assert doc.contrapposto
    assert set(prof.confini) == {1, 2} and prof.confini[2] - prof.confini[1] > 20
    sinistre = [c for c in doc.colonne if c.lato == "L"]
    assert len(sinistre) == 2 and sorted(c.ruolo for c in sinistre) == ["esercizio", "gemella"]
    tenuta = next(c for c in sinistre if c.ruolo == "esercizio")
    assert next(c for c in sinistre if c.ruolo == "gemella").gemella_di == tenuta.indice
    for pagina in (1, 2):
        sinistra = [r for r in doc.righe if r.pagina == pagina and r.lato == "L" and r.celle]
        destra = [r for r in doc.righe if r.pagina == pagina and r.lato == "R" and r.celle]
        assert len(sinistra) == len(destra) == _RIGHE
        # le celle di sinistra di entrambe le pagine stanno nella stessa colonna: un esercizio solo
        assert all(set(r.celle) == {tenuta.indice} for r in sinistra)
        assert all(r.codice.startswith("0") for r in sinistra) and all(r.codice.startswith("2") for r in destra)


def test_l_intero_senza_centesimi_e_un_importo_dove_non_c_e_mai_il_punto(tmp_path):
    doc = _documento(tmp_path)
    prima = next(r for r in doc.righe if r.pagina == 1 and r.lato == "L" and r.celle)
    assert list(prima.celle.values())[0].valore == Decimal(3007)
    assert "3007" not in prima.etichetta
