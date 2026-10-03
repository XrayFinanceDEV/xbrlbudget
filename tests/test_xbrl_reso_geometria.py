"""Task 26, fix 2: il PDF reso da XBRL letto dalla geometria quando il testo a blocchi non basta.

PDF sintetici (niente dati reali): ogni riga e' la didascalia a sinistra e gli importi allineati a
destra sotto le intestazioni a data (``gg/mm/aaaa``), una cella vuota e' una cella non scritta. Il
prospetto e' lo stesso dei test del lettore a blocchi (``tests/test_xbrl_reso_parser.py``).
"""
from __future__ import annotations

import re
from decimal import Decimal as D

import fitz

from importers import xbrl_reso_parser as X
from tests.test_xbrl_reso_parser import (
    CE_ABBREVIATO,
    DATE,
    SP_ABBREVIATO,
    _abbreviato,
    _sostituisci,
)

_IMP = re.compile(r"^-?\(?\d{1,3}(?:\.\d{3})*\)?$|^-$")
X_COL = (464.0, 542.0)


def _destra(pagina, x, y, testo, size=9):
    larghezza = fitz.get_text_length(testo, fontname="helv", fontsize=size)
    pagina.insert_text((x - larghezza, y), testo, fontname="helv", fontsize=size)


def _riga(pagina, y, riga):
    """Una riga di prospetto: didascalia (anche a capo, a passo stretto) e importi alla stessa altezza
    della prima riga di didascalia. Un importo ``None`` e' una cella vuota."""
    parti = riga.split("\n")
    importi = []
    while parti and (_IMP.match(parti[-1].strip()) or parti[-1] == "<vuoto>"):
        importi.insert(0, parti.pop().strip())
    for k, linea in enumerate(parti):
        pagina.insert_text((40, y + 12 * k), linea.rstrip(), fontname="helv", fontsize=9)
    for x, v in zip(X_COL, importi):
        if v != "<vuoto>":
            _destra(pagina, x, y, v)
    return y + 12 * max(len(parti), 1) + 3.5


def _pdf(tmp_path, pagine, nome="geo.pdf", data_fmt="/", copertina=None, numero_pagina=False):
    """``pagine``: elenchi di righe; una riga che e' ``DATE`` stampa le intestazioni di colonna."""
    doc = fitz.open()
    for i, righe in enumerate(pagine):
        pagina = doc.new_page(width=595, height=842)
        y = 60.0
        if i == 0 and copertina:
            for linea in copertina:
                pagina.insert_text((40, y), linea, fontname="helv", fontsize=9)
                y += 14
            y += 200
        for riga in righe:
            if riga == DATE or re.fullmatch(r"\d\d-\d\d-\d{4}( \d\d-\d\d-\d{4})?", riga.replace("\n", " ")):
                for x, d in zip(X_COL, ("31-12-2025", "31-12-2024")):
                    _destra(pagina, x, y, d.replace("-", data_fmt))
                y += 14
                continue
            y = _riga(pagina, y, riga)
        if numero_pagina:
            pagina.insert_text((446, 798), str(i + 1), fontname="helv", fontsize=9)
    path = str(tmp_path / nome)
    doc.save(path)
    doc.close()
    return path


def _sp_vuoto_riserva():
    return _sostituisci(SP_ABBREVIATO, "IV - Riserva legale\n50.547\n10.500",
                        "IV - Riserva legale\n50.547\n<vuoto>")


def test_date_con_barre_si_riconoscono(tmp_path):
    f = _pdf(tmp_path, [SP_ABBREVIATO, CE_ABBREVIATO])
    assert X.riconosci(f) is True


def test_una_cella_vuota_e_uno_zero_nella_sua_colonna(tmp_path):
    # Riserva legale stampata solo nella colonna 2025: l'ordine degli importi non dice di che anno e'
    sp = _sp_vuoto_riserva()
    f = _pdf(tmp_path, [sp, CE_ABBREVIATO])
    r = X.estrai(f)
    assert r["adottabile"], r["rifiuto"]
    assert r.get("lettura") == "geometria"
    assert r["bs"]["sp12c_riserva_legale"] == D("50547")
    assert r["anni"] == [2025, 2024]


def test_la_colonna_vuota_non_scivola_nell_altra_colonna(tmp_path):
    # la cella vuota e' nella colonna 2025 (la prima): il solo importo appartiene al 2024
    sp = _sostituisci(SP_ABBREVIATO, "IV - Riserva legale\n50.547\n10.500",
                      "IV - Riserva legale\n<vuoto>\n10.500")
    f = _pdf(tmp_path, [sp, CE_ABBREVIATO])
    r = X.estrai(f)
    # il 2025 non quadra piu' (manca la riserva): rifiutato, mai adottato con l'importo sulla colonna sbagliata
    assert not r["adottabile"]
    assert r["rifiuto"]["controllo"] != "prospetto_non_letto"


def test_il_prospetto_comincia_sulla_copertina(tmp_path):
    righe = SP_ABBREVIATO
    cop = ["SOCIETA' DI PROVA SRL", "Bilancio di esercizio al 31/12/2025"]
    f = _pdf(tmp_path, [righe[:5], righe[5:], CE_ABBREVIATO], copertina=cop)
    # il titolo e le prime righe stanno in fondo alla prima pagina, il resto sulla seconda
    r = X.estrai(f)
    assert r["adottabile"], r["rifiuto"]
    assert r["bs"]["sp02_immob_immateriali"] == D("21798")


def test_il_numero_di_pagina_nudo_in_fondo_non_e_un_importo(tmp_path):
    f = _pdf(tmp_path, [_sp_vuoto_riserva(), CE_ABBREVIATO], numero_pagina=True)
    r = X.estrai(f)
    assert r["adottabile"], r["rifiuto"]


def test_scadenza_stampata_con_le_celle_vuote_e_zero(tmp_path):
    sp = _sostituisci(_sp_vuoto_riserva(), "esigibili oltre l'esercizio successivo\n10.275\n0",
                      "esigibili oltre l'esercizio successivo")
    sp = _sostituisci(sp, "Totale debiti\n793.146\n650.637", "Totale debiti\n782.871\n650.637")
    sp = _sostituisci(sp, "Totale passivo\n1.672.717\n1.618.085", "Totale passivo\n1.662.442\n1.618.085")
    sp = _sostituisci(sp, "Totale attivo\n1.672.717\n1.618.085", "Totale attivo\n1.662.442\n1.618.085")
    # attivo e passivo scendono di 10.275: togliamo lo stesso importo dalle disponibilita' liquide
    sp = _sostituisci(sp, "II - Immobilizzazioni materiali\n379.283\n201.732",
                      "II - Immobilizzazioni materiali\n369.008\n201.732")
    sp = _sostituisci(sp, "Totale immobilizzazioni (B)\n405.476\n363.920",
                      "Totale immobilizzazioni (B)\n395.201\n363.920")
    sp = _sostituisci(sp, "Totale attivo circolante (C)\n1.267.232\n1.254.156",
                      "Totale attivo circolante (C)\n1.267.232\n1.254.156")
    f = _pdf(tmp_path, [sp, CE_ABBREVIATO])
    r = X.estrai(f)
    assert r["adottabile"], r["rifiuto"]
    assert r["bs"]["sp16_debiti_breve"] == D("782871")


def test_un_totale_che_non_si_riproduce_resta_rifiutato_anche_con_la_geometria(tmp_path):
    sp = _sostituisci(_sp_vuoto_riserva(), "Totale crediti\n1.252.972\n1.185.768",
                      "Totale crediti\n1.252.973\n1.185.768")
    f = _pdf(tmp_path, [sp, CE_ABBREVIATO])
    r = X.estrai(f)
    assert r["adottabile"] is False
    assert r["rifiuto_geometria"]["controllo"] in ("totale", "aggregati_del_totale", "attivo_campi")


def test_un_documento_che_il_lettore_a_blocchi_adotta_non_passa_dalla_geometria(tmp_path):
    f = _abbreviato(tmp_path)
    r = X.estrai(f)
    assert r["adottabile"], r["rifiuto"]
    assert "lettura" not in r


def test_un_importo_fuori_dalle_colonne_rifiuta(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    _destra(p, X_COL[0], 60, "31/12/2025")
    _destra(p, X_COL[1], 60, "31/12/2024")
    p.insert_text((40, 80), "Stato patrimoniale", fontname="helv", fontsize=9)
    p.insert_text((40, 94), "Attivo", fontname="helv", fontsize=9)
    p.insert_text((40, 108), "B) Immobilizzazioni", fontname="helv", fontsize=9)
    p.insert_text((40, 122), "I - Immobilizzazioni immateriali", fontname="helv", fontsize=9)
    _destra(p, 300, 122, "1.000")
    path = str(tmp_path / "fuori.pdf")
    doc.save(path)
    try:
        X._leggi_righe_geometria(fitz.open(path))
        assert False, "doveva rifiutare"
    except X._Rifiuto as exc:
        assert exc.controllo == "importo_fuori_colonna"
