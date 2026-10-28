"""Gli avvisi sui fondi dichiarati dal percorso snello (lotto week-43).

budget_1452 (1STOP): i fondi ammortamento degli immateriali (1.086,25) superano il costo storico
(1.000). Il clamp a zero e' giusto, ma l'utente vedeva solo un generico «bilancio sbilanciato di
86,25»: l'avviso deve dire che e' il fondo a superare il lordo, cioe' un errore del documento.

Run: python -m pytest tests/test_avvisi_fondi_snello.py -v
"""
from importers.pdf_importer import _avvisi_fondi_snello


def test_un_fondo_oltre_il_lordo_si_dichiara_come_errore_del_documento():
    avvisi = _avvisi_fondi_snello(
        {"immobilizzazioni_negative_tagliate": [["sp02_immob_immateriali", "86.25"]]})
    assert len(avvisi) == 1
    assert avvisi[0].startswith("FONDO OLTRE IL COSTO STORICO")
    assert "sp02_immob_immateriali eccedenza 86.25" in avvisi[0]
    assert "errore del documento" in avvisi[0]


def test_il_fondo_gia_nettato_si_dichiara_ancora():
    avvisi = _avvisi_fondi_snello({"fondi_gia_nettati": [["SPA.C.II.1.F", "-300.00"]]})
    assert avvisi and avvisi[0].startswith("FONDO GIA' NETTATO") and "SPA.C.II.1 -300.00" in avvisi[0]


def test_senza_diagnostica_nessun_avviso():
    assert _avvisi_fondi_snello({}) == []
    assert _avvisi_fondi_snello({"fondi_gia_nettati": [], "immobilizzazioni_negative_tagliate": []}) == []
