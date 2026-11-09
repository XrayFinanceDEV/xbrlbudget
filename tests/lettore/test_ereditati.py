"""Le copie in `importers/lettore/_ereditati.py` restano uguali ai privati da cui vengono (Fase 2, Task 1).

Un test di deriva cade quando il modulo vecchio cambia: decidi se portare la correzione nel lettore
(aggiorna la copia e il commit d'origine scritto in `_ereditati.py`) o se la differenza e' voluta.
"""
import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest

from importers import (detail_enrichment, mineru_adapter, schema_legge_generico, standard_ivcee_parser,
                       xbrl_reso_parser)
from importers import situazione_contabile_parser as scp
from importers.import_snello import conti as conti_snello
from importers.import_snello import righe as righe_snello
from importers.lettore import _ereditati as e

PACCHETTO = Path(e.__file__).parent

ETICHETTE = [
    "A) STATO PATRIMONIALE - ATTIVO", "STATO PATRIMONIALE PASSIVO", "S T A T O P A T R I M O N I A L E", "Conto economico",
    "BILANCIO DI ESERCIZIO AL 31/12/2025 PASSIVO E PATRIMONIO NETTO", "Passivo e netto", "Attivo", "TOTALE ATTIVO",
    "Totale attivo circolante", "II - Crediti", "B) Immobilizzazioni", "4) Debiti verso banche", "22) Imposte sul reddito",
    "esigibili entro l'esercizio successivo", "Debiti oltre 12 mesi", "21) Utile (perdita) dell'esercizio",
    "A-B+C+D TOTALE CONTO ECONOMICO", "II TOTALE DEBITI", "d5) da altri", "c), d), e) trattamento di fine rapporto",
    "TOTALI DEBITI ( D )", "di cui per leasing", "Descrizione", "Pagina 3 di 8", "Crediti verso clienti", "",
    "Ris. prima delle imposte", "Diff. tra valore e costi della produzione", "Totale rett. di valore",
    "Debiti verso fornitori di", "Altri ricavi e proventi,", "Ricavi delle vendite e", "Pag. 2", "Utente: admin",
]

TOKEN = ["1.234", "1.234.567", "123", "1.500.000,00", "-", "(1.234)", "31/12/2025", "31-12-2025", "01/01/25", "2025",
         "12.345.678", "1.23", "abc", "100%"]


@pytest.mark.parametrize("percorso", sorted(PACCHETTO.glob("*.py")), ids=lambda p: p.name)
def test_nessun_privato_da_fuori(percorso):
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "importers":
            fuori = n.module != "importers.lettore" and not n.module.startswith("importers.lettore.")
            privati = [a.name for a in n.names if a.name.startswith("_")]
            assert not (fuori and privati), f"{percorso.name}:{n.lineno} importa {privati} da {n.module}"
        elif isinstance(n, ast.Attribute) and n.attr.startswith("_") and not n.attr.startswith("__"):
            if isinstance(n.value, ast.Name) and n.value.id in ("reso", "schema_legge_generico", "xbrl_reso_parser"):
                pytest.fail(f"{percorso.name}:{n.lineno} legge {n.value.id}.{n.attr}")


def _uguali(copia, originale, ingressi, nome, modulo):
    for x in ingressi:
        assert copia(x) == originale(x), (
            f"{nome} ha preso una strada diversa da {modulo} su {x!r}: decidi se portare la correzione in "
            f"importers/lettore/_ereditati.py")


def _costante(copia, originale, nome, modulo):
    if isinstance(copia, re.Pattern):
        assert (copia.pattern, copia.flags) == (originale.pattern, originale.flags), (
            f"{nome} e' cambiata in {modulo}: decidi se portare la correzione nel lettore")
    else:
        assert copia == originale, f"{nome} e' cambiata in {modulo}: decidi se portare la correzione nel lettore"


def test_deriva_forma_strutturale():
    _uguali(e.forma_strutturale, schema_legge_generico._forma_strutturale, ETICHETTE, "forma_strutturale",
            "schema_legge_generico")


def test_deriva_intestazione():
    _uguali(e.intestazione, schema_legge_generico._intestazione, ETICHETTE, "intestazione", "schema_legge_generico")


def test_deriva_parole_testata():
    _costante(e.PAROLE_TESTATA, schema_legge_generico._PAROLE_TESTATA, "PAROLE_TESTATA", "schema_legge_generico")


def test_deriva_piede():
    _costante(e.PIEDE, schema_legge_generico._PIEDE, "PIEDE", "schema_legge_generico")


def test_deriva_e_differenza():
    from decimal import Decimal as D
    casi = [
        [[D(10), D(4), D(6)], [D(8), D(3), D(5)], [D(5), D(5), D(0)], [D(9), D(1), D(8)]],
        [[D(10), D(4), D(6)], [D(8), D(3), D(5)], [D(5), D(5), D(0)], [D(9), D(1), D(7)]],
        [[D(4), D(10), D(6)], [D(3), D(8), D(5)], [D(1), D(9), D(8)]],
        [[D(10), D(4), None], [D(8), D(3), D(5)]],
        [[D(0), D(0), D(0)]] * 4,
        [[D(10), D(4), D("6.01")], [D(8), D(3), D("5.00")], [D(9), D(1), D("8.01")]],
        [[D(10), D(4), D(-6)], [D(8), D(3), D(-5)], [D(9), D(1), D(-8)]],
    ]
    for matrice in casi:
        for k, a, b in ((2, 0, 1), (0, 1, 2), (1, 0, 2)):
            assert e.e_differenza(matrice, k, a, b) == schema_legge_generico._e_differenza(matrice, k, a, b), (
                "e_differenza ha preso una strada diversa da schema_legge_generico: decidi se portare la "
                "correzione in importers/lettore/_ereditati.py")


def test_deriva_frase_aperta():
    _uguali(e.frase_aperta, xbrl_reso_parser._frase_aperta, ETICHETTE + ["Costi per servizi, ", "Debiti per",
                                                                         "Debiti verso Banche A"],
            "frase_aperta", "xbrl_reso_parser")


def test_deriva_fascia_margine():
    _costante(e.FASCIA_MARGINE, xbrl_reso_parser._FASCIA_MARGINE, "FASCIA_MARGINE", "xbrl_reso_parser")


def test_deriva_chiave_ripetuta():
    _uguali(e.chiave_ripetuta, xbrl_reso_parser._chiave_ripetuta,
            ETICHETTE + ["Pag. 2", "Pag. 13", "Acme S.r.l. - P.IVA 01234567890", "Generato il 12/03/2026"],
            "chiave_ripetuta", "xbrl_reso_parser")


def test_deriva_amount_like():
    _costante(e.AMOUNT_LIKE, standard_ivcee_parser._AMOUNT_LIKE, "AMOUNT_LIKE", "standard_ivcee_parser")
    _uguali(lambda t: bool(e.AMOUNT_LIKE.match(t)), lambda t: bool(standard_ivcee_parser._AMOUNT_LIKE.match(t)),
            TOKEN, "AMOUNT_LIKE", "standard_ivcee_parser")


def test_deriva_date_re():
    _costante(e.DATE_RE, standard_ivcee_parser._DATE_RE, "DATE_RE", "standard_ivcee_parser")
    _uguali(lambda t: bool(e.DATE_RE.fullmatch(t)), lambda t: bool(standard_ivcee_parser._DATE_RE.fullmatch(t)),
            TOKEN, "DATE_RE", "standard_ivcee_parser")


def _pagina(*righe):
    """Righe di parole nella forma `(x0, y0, x1, y1, testo, ...)` che i due lettori si passano."""
    return [[(0, 0, 1, 1, t) for t in riga] for riga in righe]


CHIUSURE = [
    _pagina(["Crediti", "1.000,00", "900,00"], ["TOTALE", "ATTIVITA'", "5.000,00", "4.000,00"]),
    _pagina(["Costi", "100,00"], ["TOTALE", "COSTI", "500,00", "400,00"]),
    _pagina(["Ricavi", "100,00"], ["TOTALE", "RICAVI", "500,00"]),
    _pagina(["Totale", "Attivita':", "Totale", "Passivita':"], ["Crediti", "1.000,00"]),
    _pagina(["Perdita", "Esercizio", "15.063,40"], ["2.329.010,83", "2.329.010,83"]),
    _pagina(["Totale", "a", "pareggio", "1.000,00", "1.000,00"], ["Pag.", "8", "di", "8"]),
    _pagina(["Immobilizzazioni", "1.000,00"], ["Crediti", "500,00"]),
    _pagina(["2.000,00", "2.000,00"]),
    _pagina(["0,00", "0,00"]),
    _pagina(["Utile", "d'esercizio", "100,00"]),
    _pagina(["Totale", "passivo", "100,00"]),
    _pagina(),
]


def test_deriva_chiude_sezione():
    for p in CHIUSURE:
        assert e.chiude_sezione(p) == detail_enrichment._chiude_sezione(p), (
            f"chiude_sezione ha preso una strada diversa da detail_enrichment su {p!r}: decidi se portare la "
            "correzione in importers/lettore/_ereditati.py")


def test_deriva_sezione_della_chiusura():
    for p in CHIUSURE:
        assert e.sezione_della_chiusura(p) == detail_enrichment._sezione_della_chiusura(p), (
            f"sezione_della_chiusura ha preso una strada diversa da detail_enrichment su {p!r}: decidi se "
            "portare la correzione in importers/lettore/_ereditati.py")


def test_deriva_lista_concatenata():
    for vivo in ([], [True], [False], [True, False, True], [False, False, True, True, False, True],
                 [True] * 5, [False] * 4, [True, True, False, False, False, True]):
        assert e.lista_concatenata(vivo) == righe_snello._lista_concatenata(vivo), (
            f"lista_concatenata ha preso una strada diversa da import_snello.righe su {vivo!r}: decidi se "
            "portare la correzione in importers/lettore/_ereditati.py")


HTML = [
    "<table><tr><td>A</td><td>1.234</td></tr></table>",
    "<table><tr><th>Voce</th><th>2025</th><th>2024</th></tr><tr><td>Ricavi</td><td>10</td><td>20</td></tr></table>",
    "<table><tr><td>a<br>b</td><td> x </td></tr><tr><td></td></tr></table>",
    "<table><tr><td>mai chiusa",
    "<p>niente tabella</p>",
    "<table><tr><td>1</td></tr><tr><td>2</td><td>3</td></tr></table><table><tr><td>4</td></tr></table>",
    "<table><tr><td><b>grassetto</b> e testo</td></tr></table>",
    "",
]


def test_deriva_table_html_parser():
    for html in HTML:
        a, b = e.TableHTMLParser(), mineru_adapter._TableHTMLParser()
        a.feed(html)
        b.feed(html)
        assert a.rows == b.rows, (
            f"TableHTMLParser ha preso una strada diversa da mineru_adapter su {html!r}: decidi se portare la "
            "correzione in importers/lettore/_ereditati.py")


IMPORTI_FONDI = [
    {}, {"sp03b": Decimal("-200"), "sp03": Decimal("50")}, {"sp02a": Decimal("10"), "sp02g": Decimal("-5")},
    {"sp04d": Decimal("-1"), "sp06a": Decimal("-3")}, {"sp03": Decimal("-7")}, {"sp03b": Decimal("0")},
]


def test_deriva_netta_fondi_negativi():
    assert e.IMMOBILIZZAZIONI == conti_snello._IMMOBILIZZAZIONI
    for imp in IMPORTI_FONDI:
        assert e.netta_fondi_negativi(dict(imp)) == conti_snello._netta_fondi_negativi(dict(imp)), (
            f"netta_fondi_negativi ha preso una strada diversa da import_snello.conti su {imp!r}: decidi se portare "
            "la correzione in importers/lettore/_ereditati.py")


def test_deriva_clamp_immobilizzazioni_negative():
    for bs in ({}, {"sp03_immob_materiali": Decimal("-200")}, {"sp02_immob_immateriali": Decimal("5"),
               "sp04_immob_finanziarie": Decimal("-0.5")}, {"sp06_crediti_breve": Decimal("-9")}):
        a, b = dict(bs), dict(bs)
        assert e.clamp_immobilizzazioni_negative(a) == conti_snello._clamp_immobilizzazioni_negative(b) and a == b, (
            f"clamp_immobilizzazioni_negative ha preso una strada diversa da import_snello.conti su {bs!r}: decidi "
            "se portare la correzione in importers/lettore/_ereditati.py")


DESCRIZIONI_CESPITI = [
    "F/AMM. LAV. STR. SU BENI DI TERZ", "LAV. STR. SU BENI DI TERZI", "F.DO AMM.TO AUTOMEZZI", "IMPIANTI GENERICI",
    "FONDO AMMORTAMENTO IMPIANTI DI PRODU", "F.DO AMM. MACCH. ORD. UFF", "COSTI DI IMPIANTO", "SOFTWARE", "AVVIAMENTO",
    "TERRENI", "ATTREZZATURA VARIA", "IMMOBILIZZAZIONI IN CORSO", "F.DO AMM.COSTR.LEGGERE", "DIRITTI UTILIZZO", "",
    "CASSA", "F/AMM.IMP.GENERICI/SPECIFICI", "MOBILI E ARREDI", "F.DI AMMOR.TO MARCHI",
]


def test_deriva_dettagli_dei_cespiti():
    for d in DESCRIZIONI_CESPITI:
        assert e.dettaglio_sp02(d) == scp._sp02_detail_field(d) and e.dettaglio_sp03(d) == scp._sp03_detail_field(d), (
            f"dettaglio_sp02/03 ha preso una strada diversa da situazione_contabile_parser su {d!r}: decidi se "
            "portare la correzione in importers/lettore/_ereditati.py")


def test_deriva_testa_del_fondo():
    _costante(e.FONDO_AMM_HEAD_RE, scp._FONDO_AMM_HEAD_RE, "FONDO_AMM_HEAD_RE", "situazione_contabile_parser")


DESCRIZIONI_PAROLE_CHIAVE = [
    "FABBRICATI INDUSTRIALI", "F.DO AMM. MACCHINARI", "FONDO AMMORTAMENTO IMMOBILIZZAZIONI", "CASSA", "BANCA C/C",
    "CLIENTI ITALIA", "ERARIO C/IVA", "RIMANENZE FINALI MERCI", "FONDO TFR DIPENDENTI", "FONDI RISCHI E ONERI",
    "CAPITALE SOCIALE", "RISERVA LEGALE", "DEBITI VERSO BANCHE", "MUTUI PASSIVI", "RATEI PASSIVI", "DEBITI TRIBUTARI",
    "IRAP", "ACQUISTI", "SERVIZI", "Materie prime, sussidiarie, di consumo e di merci", "Costi per godimento di beni di terzi",
    "Ricavi delle vendite e delle prestazioni", "Altri ricavi e proventi", "Interessi passivi e altri oneri finanziari",
    "Ammortamento immobilizzazioni materiali", "Imposte sul reddito", "CARBURANTI", "Voce stranissima", "",
]


def test_deriva_tabelle_sp():
    _costante(e._SP_ATTIVO_RULES, scp._SP_ATTIVO_RULES, "_SP_ATTIVO_RULES", "situazione_contabile_parser")
    _costante(e._SP_PASSIVO_RULES, scp._SP_PASSIVO_RULES, "_SP_PASSIVO_RULES", "situazione_contabile_parser")
    _costante(e._FONDO_AMM_CANON, scp._FONDO_AMM_CANON, "_FONDO_AMM_CANON", "situazione_contabile_parser")
    _costante(e._CE_COST_FIELDS, scp._CE_COST_FIELDS, "_CE_COST_FIELDS", "situazione_contabile_parser")
    _costante(e._CE_REVENUE_FIELDS, scp._CE_REVENUE_FIELDS, "_CE_REVENUE_FIELDS", "situazione_contabile_parser")


def test_deriva_regola_sp_e_resolve_ce():
    for lato in ("attivo", "passivo"):
        _uguali(lambda d: e._regola_sp(d.upper(), lato), lambda d: scp._regola_sp(d.upper(), lato),
                DESCRIZIONI_PAROLE_CHIAVE, f"_regola_sp({lato})", "situazione_contabile_parser")
    _uguali(lambda d: e._canon_fondo_amm(d.upper()), lambda d: scp._canon_fondo_amm(d.upper()),
            DESCRIZIONI_PAROLE_CHIAVE, "_canon_fondo_amm", "situazione_contabile_parser")
    _uguali(lambda d: e._is_fondo_amm(d.upper()), lambda d: scp._is_fondo_amm(d.upper()),
            DESCRIZIONI_PAROLE_CHIAVE, "_is_fondo_amm", "situazione_contabile_parser")
    for direzione in ("costi", "ricavi"):
        _uguali(lambda d: e._resolve_ce_field(d, direzione), lambda d: scp._resolve_ce_field(d, direzione),
                DESCRIZIONI_PAROLE_CHIAVE, f"_resolve_ce_field({direzione})", "situazione_contabile_parser")
