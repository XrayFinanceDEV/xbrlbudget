"""Task 16 (b): deterministico prima di Qwen. PDF sintetici (niente dati reali) che i
parser deterministici del vecchio importatore leggono davvero, piu' fake che sollevano
se interrogati (0 chiamate a Qwen quando il deterministico si applica)."""
from __future__ import annotations

from decimal import Decimal as D

import fitz
import pytest

from importers import import_snello
from importers.import_snello import deterministico as DET

FONT = "helv"


def _dest(page, x_right, y, testo, fontsize=8):
    larghezza = fitz.get_text_length(testo, fontname=FONT, fontsize=fontsize)
    page.insert_text((x_right - larghezza, y), testo, fontname=FONT, fontsize=fontsize)


def _riga(page, y, label=None, valore_corrente=None, x_label=20, x_corrente=400):
    if label:
        page.insert_text((x_label, y), label, fontname=FONT, fontsize=8)
    if valore_corrente is not None:
        _dest(page, x_corrente, y, valore_corrente, fontsize=8)


def _pdf_comparativo_bilanciato(path) -> str:
    """Schema di legge a colonne comparative (due date, come i bilanci UE riclassificati
    con codici IV-CEE): captions e importi che chiudono esattamente ad ogni controllo
    incrociato di ``standard_ivcee_parser._parse_column``/``_parse_income_column``. Solo
    la colonna corrente e' popolata: la precedente resta senza importi (il documento e'
    comunque comparato: le due date sono le uniche prove richieste)."""
    doc = fitz.open()

    sp = doc.new_page(width=595, height=842)
    _dest(sp, 400, 40, "31/12/2025")
    _dest(sp, 500, 40, "31/12/2024")
    righe_sp = [
        ("STATO PATRIMONIALE ATTIVO", None),
        ("A) Crediti verso soci", "0,00"),
        ("B) Immobilizzazioni", None),
        ("I. Immateriali", None),
        (None, "100,00"),
        ("II. Materiali", None),
        (None, "900,00"),
        ("III. Finanziarie", None),
        (None, "0,00"),
        ("Totale immobilizzazioni", "1.000,00"),
        ("C) Attivo circolante", None),
        ("I. Rimanenze", None),
        (None, "200,00"),
        ("II. Crediti", None),
        ("Verso clienti - entro l'esercizio successivo", "300,00"),
        ("- oltre l'esercizio successivo", "0,00"),
        (None, "300,00"),
        ("III. Attivita finanziarie", None),
        (None, "0,00"),
        ("IV. Disponibilita liquide", None),
        (None, "500,00"),
        ("Totale attivo circolante", "1.000,00"),
        ("D) Ratei e risconti attivi", "0,00"),
        ("Totale attivo", "2.000,00"),
        ("STATO PATRIMONIALE PASSIVO", None),
        ("A) Patrimonio netto", None),
        ("I. Capitale", "1.000,00"),
        ("IX. Utile dell'esercizio", "200,00"),
        ("Totale patrimonio netto", "1.200,00"),
        ("Totale fondi per rischi e oneri", "0,00"),
        ("C) Trattamento di fine rapporto", "100,00"),
        ("D) Debiti", None),
        ("Verso fornitori - entro l'esercizio successivo", "700,00"),
        ("- oltre l'esercizio successivo", "0,00"),
        ("Totale debiti", "700,00"),
        ("E) Ratei e risconti passivi", "0,00"),
        ("Totale passivo", "2.000,00"),
    ]
    y = 70
    for label, valore in righe_sp:
        _riga(sp, y, label, valore)
        y += 12

    ce = doc.new_page(width=595, height=842)
    _dest(ce, 400, 40, "31/12/2025")
    _dest(ce, 500, 40, "31/12/2024")
    righe_ce = [
        ("Conto economico", None),
        ("A) Valore della produzione", None),
        ("1) Ricavi delle vendite e delle prestazioni", "3.000,00"),
        ("2) Variazione dei lavori in corso", "0,00"),
        ("3) Variazioni dei lavori in corso su ordinazione", "0,00"),
        ("4) Incrementi di immobilizzazioni per lavori interni", "0,00"),
        ("5) Altri ricavi e proventi", "0,00"),
        ("Totale valore della produzione", "3.000,00"),
        ("B) Costi della produzione", None),
        ("6) Per materie prime", "0,00"),
        ("7) Per servizi", "2.000,00"),
        ("8) Per godimento di beni di terzi", "0,00"),
        ("9) Per il personale", "500,00"),
        ("10) Ammortamenti e svalutazioni", "100,00"),
        ("11) Variazioni delle rimanenze di materie prime", "0,00"),
        ("12) Accantonamento per rischi", "0,00"),
        ("13) Altri accantonamenti", "0,00"),
        ("14) Oneri diversi di gestione", "0,00"),
        ("Totale costi della produzione", "2.600,00"),
        ("Differenza tra valore e costi della produzione (A-B)", "400,00"),
        ("C) Proventi e oneri finanziari", None),
        ("15) Proventi da partecipazioni", "0,00"),
        ("16) Altri proventi finanziari", "0,00"),
        ("17) Interessi e altri oneri finanziari", "0,00"),
        ("17 bis) Utili e perdite su cambi", "0,00"),
        ("Totale proventi e oneri finanziari", "0,00"),
        ("D) Rettifiche di valore di attivita e passivita finanziarie", None),
        ("Totale rettifiche di valore di attivita e passivita finanziarie", "0,00"),
        ("Risultato prima delle imposte", "400,00"),
        ("20) Imposte sul reddito dell'esercizio", "200,00"),
        ("21) Utile (perdita) dell'esercizio", "200,00"),
    ]
    y = 70
    for label, valore in righe_ce:
        _riga(ce, y, label, valore)
        y += 12

    doc.save(path)
    doc.close()
    return path


def _pdf_comparativo_sbilanciato(path) -> str:
    """Come sopra, ma con "Totale immobilizzazioni" alterato: il controllo incrociato
    interno di ``_parse_column`` (sp02+sp03+sp04 == totale_imm) fallisce, quindi
    ``extract_standard_ivcee_balances`` torna None - il modulo deve dichiararlo
    "oltre_soglia" e proseguire col percorso Qwen, mai adottare un risultato a caso."""
    doc = fitz.open()
    nuova = doc.new_page(width=595, height=842)
    _dest(nuova, 400, 40, "31/12/2025")
    _dest(nuova, 500, 40, "31/12/2024")
    righe_sp = [
        ("STATO PATRIMONIALE ATTIVO", None),
        ("A) Crediti verso soci", "0,00"),
        ("B) Immobilizzazioni", None),
        ("I. Immateriali", None),
        (None, "100,00"),
        ("II. Materiali", None),
        (None, "900,00"),
        ("III. Finanziarie", None),
        (None, "0,00"),
        ("Totale immobilizzazioni", "1.500,00"),
        ("C) Attivo circolante", None),
        ("I. Rimanenze", None),
        (None, "200,00"),
        ("II. Crediti", None),
        ("Verso clienti - entro l'esercizio successivo", "300,00"),
        ("- oltre l'esercizio successivo", "0,00"),
        (None, "300,00"),
        ("III. Attivita finanziarie", None),
        (None, "0,00"),
        ("IV. Disponibilita liquide", None),
        (None, "500,00"),
        ("Totale attivo circolante", "1.000,00"),
        ("D) Ratei e risconti attivi", "0,00"),
        ("Totale attivo", "2.000,00"),
        ("STATO PATRIMONIALE PASSIVO", None),
        ("A) Patrimonio netto", None),
        ("I. Capitale", "1.000,00"),
        ("IX. Utile dell'esercizio", "200,00"),
        ("Totale patrimonio netto", "1.200,00"),
        ("Totale fondi per rischi e oneri", "0,00"),
        ("C) Trattamento di fine rapporto", "100,00"),
        ("D) Debiti", None),
        ("Verso fornitori - entro l'esercizio successivo", "700,00"),
        ("- oltre l'esercizio successivo", "0,00"),
        ("Totale debiti", "700,00"),
        ("E) Ratei e risconti passivi", "0,00"),
        ("Totale passivo", "2.000,00"),
    ]
    y = 70
    for label, valore in righe_sp:
        _riga(nuova, y, label, valore)
        y += 12

    ce = doc.new_page(width=595, height=842)
    _dest(ce, 400, 40, "31/12/2025")
    _dest(ce, 500, 40, "31/12/2024")
    righe_ce = [
        ("Conto economico", None),
        ("A) Valore della produzione", None),
        ("1) Ricavi delle vendite e delle prestazioni", "3.000,00"),
        ("2) Variazione dei lavori in corso", "0,00"),
        ("3) Variazioni dei lavori in corso su ordinazione", "0,00"),
        ("4) Incrementi di immobilizzazioni per lavori interni", "0,00"),
        ("5) Altri ricavi e proventi", "0,00"),
        ("Totale valore della produzione", "3.000,00"),
        ("B) Costi della produzione", None),
        ("6) Per materie prime", "0,00"),
        ("7) Per servizi", "2.000,00"),
        ("8) Per godimento di beni di terzi", "0,00"),
        ("9) Per il personale", "500,00"),
        ("10) Ammortamenti e svalutazioni", "100,00"),
        ("11) Variazioni delle rimanenze di materie prime", "0,00"),
        ("12) Accantonamento per rischi", "0,00"),
        ("13) Altri accantonamenti", "0,00"),
        ("14) Oneri diversi di gestione", "0,00"),
        ("Totale costi della produzione", "2.600,00"),
        ("Differenza tra valore e costi della produzione (A-B)", "400,00"),
        ("C) Proventi e oneri finanziari", None),
        ("15) Proventi da partecipazioni", "0,00"),
        ("16) Altri proventi finanziari", "0,00"),
        ("17) Interessi e altri oneri finanziari", "0,00"),
        ("17 bis) Utili e perdite su cambi", "0,00"),
        ("Totale proventi e oneri finanziari", "0,00"),
        ("D) Rettifiche di valore di attivita e passivita finanziarie", None),
        ("Totale rettifiche di valore di attivita e passivita finanziarie", "0,00"),
        ("Risultato prima delle imposte", "400,00"),
        ("20) Imposte sul reddito dell'esercizio", "200,00"),
        ("21) Utile (perdita) dell'esercizio", "200,00"),
    ]
    y = 70
    for label, valore in righe_ce:
        _riga(ce, y, label, valore)
        y += 12

    doc.save(path)
    doc.close()
    return path


def _pdf_situazione_contabile(path) -> str:
    """Una pagina qualsiasi (il testo del bilancio di verifica arriva da text_override,
    mai dal text layer del PDF: extract_situazione_contabile apre comunque il file)."""
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


_TESTO_BILANCIO_DI_VERIFICA = "\n".join([
    "**", "ATTIVITA'",
    "01/01/001", "CASSA CONTANTI", "1.000,00",
    "01/01/002", "CREDITI VARI UNO", "0,00",
    "01/01/003", "CREDITI VARI DUE", "0,00",
    "01/01/004", "CREDITI VARI TRE", "0,00",
    "01/01/005", "CREDITI VARI QUATTRO", "0,00",
    "**", "PASSIVITA'",
    "02/01/001", "CAPITALE SOCIALE", "1.000,00",
    "02/01/002", "DEBITI VARI UNO", "0,00",
    "02/01/003", "DEBITI VARI DUE", "0,00",
    "02/01/004", "DEBITI VARI TRE", "0,00",
    "02/01/005", "DEBITI VARI QUATTRO", "0,00",
])


def _leggi_conti_solleva(righe, foglie):
    raise AssertionError("Qwen (leggi_conti) non doveva essere chiamato: il deterministico si applica")


def _leggi_voci_solleva(testo, intestazioni, **kw):
    raise AssertionError("Qwen (leggi_voci) non doveva essere chiamato: il deterministico si applica")


def _trascrivi_solleva(*a, **kw):
    raise AssertionError("Qwen (trascrivi) non doveva essere chiamato: il deterministico si applica")


def _analizza_qualsiasi(struttura_stub):
    def _fn(path, route_hint=None):
        return struttura_stub
    return _fn


class _StrutturaStub:
    """Una struttura minima e coerente: basta perche' importa() non tenti nulla oltre
    al deterministico prima di adottarlo. modo/pagine sono irrilevanti (il
    deterministico gira PRIMA di chiunque li usi)."""

    def __init__(self, modo="conti"):
        self.modo = modo
        self.pagine_sp = [1]
        self.pagine_ce = [1]
        self.colonne_sp = ["saldo_corrente"]
        self.colonne_ce = ["saldo_corrente"]
        self.mappe = []
        self.intestazioni_sp = []
        self.intestazioni_ce = []
        self.pagine_senza_testo = set()

    def report(self):
        return {"modo": self.modo}

    def pagine_dettagli(self):
        return set(self.pagine_sp)


# --- unita': deterministico.tentativo -------------------------------------------------

def test_standard_ivcee_parser_riconosce_uno_schema_comparato(tmp_path):
    pdf = str(tmp_path / "comparativo.pdf")
    _pdf_comparativo_bilanciato(pdf)

    esito = DET.tentativo(pdf)

    assert esito["adottato"] is True
    assert esito["parser"] == "standard_ivcee_parser"
    assert esito["esito"] in ("ok", "tappo")
    assert esito["bs"]["sp09_disponibilita_liquide"] == D("500.00")
    assert esito["bs"]["sp11_capitale"] == D("1000.00")
    assert esito["ce"]["ce06_servizi"] == D("2000.00")


def test_standard_ivcee_parser_non_riconciliato_e_oltre_soglia(tmp_path):
    pdf = str(tmp_path / "comparativo-rotto.pdf")
    _pdf_comparativo_sbilanciato(pdf)

    esito = DET.tentativo(pdf)

    assert esito["adottato"] is False
    assert esito["parser"] == "standard_ivcee_parser"
    assert esito["esito"] == "oltre_soglia"


def test_situazione_contabile_riconosce_un_bilancio_di_verifica(tmp_path):
    pdf = str(tmp_path / "verifica.pdf")
    _pdf_situazione_contabile(pdf)

    esito = DET.tentativo(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA)

    assert esito["adottato"] is True
    assert esito["parser"] == "situazione_contabile_parser"
    assert esito["esito"] in ("ok", "tappo")
    assert esito["bs"]["sp09_disponibilita_liquide"] == D("1000.00")
    assert esito["bs"]["sp11_capitale"] == D("1000.00")


def test_nessun_parser_applicabile_su_prosa_qualsiasi(tmp_path):
    pdf = str(tmp_path / "prosa.pdf")
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((50, 50), "Relazione sulla gestione: nessun numero qui dentro.")
    doc.save(pdf)
    doc.close()

    esito = DET.tentativo(pdf)

    assert esito == {"adottato": False, "parser": None, "esito": "non_applicabile"}


# --- integrazione: importa() non chiama Qwen quando il deterministico si applica ------

def test_importa_adotta_il_deterministico_a_zero_chiamate_qwen(tmp_path, monkeypatch):
    pdf = str(tmp_path / "comparativo.pdf")
    _pdf_comparativo_bilanciato(pdf)

    risultato = import_snello.importa(
        pdf,
        analizza=_analizza_qualsiasi(_StrutturaStub(modo="conti")),
        leggi_conti=_leggi_conti_solleva,
        leggi_voci=_leggi_voci_solleva,
        trascrivi=_trascrivi_solleva,
    )

    assert risultato.report["esito"] in ("ok", "tappo")
    assert risultato.report["fonte"] == "deterministico:standard_ivcee_parser"
    assert risultato.report["deterministico"]["parser"] == "standard_ivcee_parser"
    assert risultato.report["deterministico"]["esito"] in ("ok", "tappo")
    assert risultato.bs["sp09_disponibilita_liquide"] == D("500.00")
    assert risultato.report["letture"] == {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}


def test_importa_deterministico_sbilanciato_fa_girare_qwen(tmp_path):
    pdf = str(tmp_path / "comparativo-rotto.pdf")
    _pdf_comparativo_sbilanciato(pdf)

    chiamato = {"conti": False}

    def _leggi_conti_marcato(righe, foglie):
        chiamato["conti"] = True
        return {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}

    with pytest.raises(import_snello.SnelloNonRiuscito):
        # Le foglie senza percorso (nessun leggi_conti "vero" chiamato) fanno fallire
        # la verifica: quel che conta qui e' che leggi_conti SIA stato interrogato -
        # cioe' che il percorso Qwen sia effettivamente girato, non il suo esito.
        import_snello.importa(
            pdf,
            analizza=_analizza_qualsiasi(_StrutturaStub(modo="conti")),
            leggi_conti=_leggi_conti_marcato,
        )

    assert chiamato["conti"] is True
