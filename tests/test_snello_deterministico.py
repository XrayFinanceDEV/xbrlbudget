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
        self.pagine_dettaglio = []
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
    # Task 25: il parser non restituisce nulla (nessuna colonna riconcilia): "vuoto", non
    # "oltre_soglia" (che dichiarerebbe una quadratura mancata dove non c'e' stata lettura).
    assert esito["esito"] == "vuoto"


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


def test_importa_deterministico_massa_oltre_soglia_fa_girare_qwen(tmp_path, monkeypatch):
    # Task 18, ruling (a): un candidato deterministico BILANCIATO ma con una massa non
    # classificata oltre soglia non si adotta piu' - il chiamante prosegue col percorso Qwen
    # di oggi, esattamente come per uno sbilanciato (test sopra), e il report dichiara perche'.
    pdf = str(tmp_path / "verifica-massa-qwen.pdf")
    _pdf_situazione_contabile(pdf)

    def _fake_extract(file_path, return_prior=False, text_override=None):
        bs = {"sp09": D("1000.00"), "sp11": D("1000.00"), "_unclassified_mass": D("80000.00")}
        ce = {f"ce{i:02d}": D("0.00") for i in range(1, 21)}
        return bs, ce, None, None

    monkeypatch.setattr(
        "importers.situazione_contabile_parser.extract_situazione_contabile", _fake_extract)

    chiamato = {"conti": False}

    def _leggi_conti_marcato(righe, foglie):
        chiamato["conti"] = True
        return {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}

    with pytest.raises(import_snello.SnelloNonRiuscito) as exc_info:
        import_snello.importa(
            pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA,
            analizza=_analizza_qualsiasi(_StrutturaStub(modo="conti")),
            leggi_conti=_leggi_conti_marcato,
        )

    assert chiamato["conti"] is True
    report = exc_info.value.report
    assert report["deterministico"]["esito"] == "massa_non_classificata"
    assert report["deterministico"]["unclassified_mass"] == "80000.00"


# --- fix round 1 (review): chiavi diagnostiche con underscore mai scartate -------------

def test_adatta_passa_le_chiavi_con_underscore_senza_scartarle():
    # _map_sc_keys in pdf_importer.py passa ogni chiave con underscore TALE E QUALE
    # (mai un Decimal forzato: alcune sono bool/str) - _adatta deve fare lo stesso, non
    # scartarle come se non fossero un campo sp*/ce*: sono diagnostica dichiarata dal
    # parser, mai un dato inventato al loro posto (CLAUDE.md, "un estrattore dichiara
    # sempre le proprie chiavi diagnostiche, anche a zero").
    dati = {
        "sp09": D("100.00"),
        "_plug_residual": D("5.00"),
        "_skip_declared_reconcile": True,
        "_unclassified_mass": D("12.34"),
        "_contra_reason": "fondo netto",
        "totale_attivo": D("999.00"),  # non underscore, non sp*/ce*: si scarta
    }
    out = DET._adatta(dati)
    assert out["sp09_disponibilita_liquide"] == D("100.00")
    assert out["_plug_residual"] == D("5.00")
    assert out["_skip_declared_reconcile"] is True
    assert out["_unclassified_mass"] == D("12.34")
    assert out["_contra_reason"] == "fondo netto"
    assert "totale_attivo" not in out


def test_tentativo_situazione_contabile_non_scarta_la_massa_non_classificata(tmp_path, monkeypatch):
    # Un bilancio di verifica riconosciuto (il gate is_situazione_contabile passa) il cui
    # estrattore dichiara una massa non classificata materiale (qui 80.000,00, ben oltre la
    # soglia di verifica.soglia() su un attivo di 1.000,00 = 100,00): il candidato quadra come
    # foglio (fallback lecito, gia' contato una volta), ma Task 18 (ruling a) NON lo adotta piu'
    # a occhi chiusi solo perche' quadra - un fallback che assorbe una massa materiale sposta
    # comunque un aggregato reale (ce05 in ce06, personale in ce08d... diagnosi banco TM 589/590,
    # 2026-09-27), e va lasciato al percorso Qwen. La massa dichiarata dal parser sottostante
    # sopravvive comunque nel report (mai un hardcoded zero, mai scartata in silenzio): e'
    # dichiarata, non nascosta, solo non best-effort-adottata.
    pdf = str(tmp_path / "verifica-massa.pdf")
    _pdf_situazione_contabile(pdf)

    def _fake_extract(file_path, return_prior=False, text_override=None):
        bs = {"sp09": D("1000.00"), "sp11": D("1000.00"),
              "_unclassified_mass": D("80000.00"), "_unclassified_mass_measured": D("1")}
        # ce non vuoto (come build_iv_cee, che riempie sempre ce01..ce20 a zero): un
        # dict vuoto sarebbe "falsy" e cadrebbe nel cancello di applicabilita', mai
        # nella verifica che questo test vuole esercitare.
        ce = {f"ce{i:02d}": D("0.00") for i in range(1, 21)}
        return bs, ce, None, None

    monkeypatch.setattr(
        "importers.situazione_contabile_parser.extract_situazione_contabile", _fake_extract)

    esito = DET.tentativo(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA)

    assert esito["adottato"] is False
    assert esito["parser"] == "situazione_contabile_parser"
    assert esito["esito"] == "massa_non_classificata"
    assert esito["unclassified_mass"] == "80000.00"


def test_tentativo_situazione_contabile_adotta_se_la_massa_e_entro_soglia(tmp_path, monkeypatch):
    # Simmetrico al test sopra (Task 18, ruling a): una massa non classificata piccola, entro
    # la stessa soglia di verifica.soglia() (max(100, 0,1% dell'attivo) - qui 100,00 su un
    # attivo di 1.000,00), non blocca l'adozione - la regola guarda la MASSA, non la sua
    # semplice presenza (dichiarare sempre le proprie chiavi diagnostiche, anche piccole, resta
    # obbligatorio: CLAUDE.md).
    pdf = str(tmp_path / "verifica-massa-piccola.pdf")
    _pdf_situazione_contabile(pdf)

    def _fake_extract(file_path, return_prior=False, text_override=None):
        bs = {"sp09": D("1000.00"), "sp11": D("1000.00"), "_unclassified_mass": D("50.00")}
        ce = {f"ce{i:02d}": D("0.00") for i in range(1, 21)}
        return bs, ce, None, None

    monkeypatch.setattr(
        "importers.situazione_contabile_parser.extract_situazione_contabile", _fake_extract)

    esito = DET.tentativo(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA)

    assert esito["adottato"] is True
    assert esito["esito"] in ("ok", "tappo")
    assert esito["bs"]["_unclassified_mass"] == D("50.00")


def test_importa_surfaces_la_massa_non_classificata_del_deterministico(tmp_path, monkeypatch):
    pdf = str(tmp_path / "qualsiasi.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    finto = {
        "adottato": True, "parser": "situazione_contabile_parser", "esito": "ok",
        "bs": {"sp09_disponibilita_liquide": D("1000.00"), "sp11_capitale": D("1000.00"),
              "_unclassified_mass": D("80000.00")},
        "ce": {},
        "tappo": None,
        "misura": {"attivo": D("1000.00"), "passivo": D("1000.00"), "utile_ce": D("0.00"),
                  "sp13": D("0.00"), "forma": "bilancio", "scarto_sp": D("0.00"),
                  "scarto_ce": D("0.00"), "scarto_stampati": D("0.00")},
    }
    monkeypatch.setattr("importers.import_snello.deterministico.tentativo", lambda *a, **kw: finto)

    risultato = import_snello.importa(pdf, analizza=_analizza_qualsiasi(_StrutturaStub(modo="conti")))

    assert risultato.bs["_unclassified_mass"] == D("80000.00")
    assert risultato.report["deterministico"]["unclassified_mass"] == "80000.00"
    # diag non e' uno scheletro vuoto costruito a mano che pare pulito: dichiara la fonte,
    # e porta comunque tutte le chiavi che il resto del codice legge (mai un KeyError).
    assert risultato.report["diag"]["fonte"] == "situazione_contabile_parser"
    for chiave in ("non_mappati", "escluse", "lato_irrisolti", "risultato_duplicato", "padri_esclusi"):
        assert risultato.report["diag"][chiave] == []


def test_importa_somma_il_plug_residual_del_parser_a_quello_del_tappo_lean(tmp_path, monkeypatch):
    pdf = str(tmp_path / "qualsiasi-tappo.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    finto = {
        "adottato": True, "parser": "standard_ivcee_parser", "esito": "tappo",
        "bs": {"sp09_disponibilita_liquide": D("1000.00"), "sp11_capitale": D("900.00"),
              "_plug_residual": D("50.00")},
        "ce": {},
        "tappo": {"campo": "sp16g_altri_debiti_breve", "importo": "100.00", "soglia": "10.00"},
        "misura": {"attivo": D("1000.00"), "passivo": D("900.00"), "utile_ce": D("0.00"),
                  "sp13": D("0.00"), "forma": "bilancio", "scarto_sp": D("100.00"),
                  "scarto_ce": D("0.00"), "scarto_stampati": D("0.00")},
    }
    monkeypatch.setattr("importers.import_snello.deterministico.tentativo", lambda *a, **kw: finto)

    risultato = import_snello.importa(pdf, analizza=_analizza_qualsiasi(_StrutturaStub(modo="conti")))

    # 50,00 dichiarati dal parser + 100,00 del tappo lean: mai l'uno al posto dell'altro.
    assert risultato.bs["_plug_residual"] == D("150.00")


def test_prova_standard_ivcee_tenta_anche_la_colonna_singola(tmp_path):
    """Task 23: prima, un documento senza due colonne affiancate non veniva
    nemmeno passato a ``extract_standard_ivcee_balances``/``_income`` — il
    ramo compatto del modulo (mastri piatti a colonna singola, budget_289/352)
    non veniva mai raggiunto dal percorso snello per NESSUN file. Ora il gate
    lo tenta comunque, e un documento che quadra si adotta a zero chiamate."""
    from tests.test_standard_ivcee_parser import _write_flat_mastri_pdf

    pdf = str(tmp_path / "flat-mastri.pdf")
    _write_flat_mastri_pdf(pdf)

    esito = DET.tentativo(pdf)

    assert esito["adottato"] is True
    assert esito["parser"] == "standard_ivcee_parser"
    assert esito["esito"] in ("ok", "tappo")
    assert esito["bs"]["sp16a_debiti_banche_breve"] == D("110.00")


def test_prova_standard_ivcee_colonna_singola_non_riconosciuta_non_blocca(tmp_path):
    """Un documento a colonna singola che il ramo compatto non riconosce
    affatto (nessuna "stato patrimoniale") deve tornare ``None`` da
    ``_prova_standard_ivcee`` — mai un dizionario "oltre_soglia" che
    bloccherebbe il tentativo successivo di situazione_contabile_parser per
    un file che questo parser non ha nemmeno provato a leggere."""
    from importers.import_snello.deterministico import _prova_standard_ivcee

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Relazione sulla gestione", fontsize=10)
    page.insert_text((50, 70), "Un testo qualsiasi, senza alcuno schema di bilancio.", fontsize=9)
    pdf = str(tmp_path / "prosa.pdf")
    doc.save(pdf)
    doc.close()

    assert _prova_standard_ivcee(pdf) is None


def test_parse_compact_balance_rifiuta_un_estrazione_tutta_a_zero(tmp_path):
    """Attivo = Passivo = 0 non e' una quadratura (CLAUDE.md, "Quadratura,
    diagnostica e verdetti"): misurato sul corpus reale (budget_355/356, un
    "bilancio provvisorio" a mastri piatti a colonna singola stampato
    davvero a zero ovunque), dove le voci opzionali del Task 23 (
    ``fin_imm_i``/``fin_att_i`` facoltativi, "Totale fondi per rischi"
    facoltativo...) smettevano di sollevare e restituivano un dizionario
    "pulito" a zero — ogni controllo incrociato chiude per coincidenza
    quando tutto vale zero, ed era il bilancio piu' pulito del corpus prima
    del guardiano. Stesso schema di didascalie di ``_write_flat_mastri_pdf``,
    importi tutti a zero: deve tornare ``None``, mai un bilancio vuoto."""
    from importers.standard_ivcee_parser import extract_standard_ivcee_balances

    doc = fitz.open()
    sp = doc.new_page()
    righe = [
        ("STATO PATRIMONIALE ATTIVO", None),
        (" B) Immobilizzazioni", None),
        (" I) Immobilizzazioni immateriali", None),
        ("   1) Costi di impianto e di ampliamento", "0,00"),
        ("   Totale Immobilizzazioni immateriali", "0,00"),
        (" II) Immobilizzazioni materiali", None),
        ("   2) Impianti e macchinario", "0,00"),
        ("   Totale Immobilizzazioni materiali", "0,00"),
        (" Totale Immobilizzazioni (B)", "0,00"),
        ("C) Attivo circolante", None),
        (" I) Rimanenze", None),
        ("   1) Materie prime, sussidiarie e di consumo", "0,00"),
        ("   Totale Rimanenze", "0,00"),
        (" II) Crediti", None),
        ("   1) Verso clienti", "0,00"),
        ("   Totale Crediti", "0,00"),
        (" IV) Disponibilita liquide", None),
        ("   1) Depositi bancari e postali", "0,00"),
        (" Totale Disponibilita liquide", "0,00"),
        (" Totale Attivo circolante (C)", "0,00"),
        ("D) Ratei e risconti attivi", "0,00"),
        (" TOTALE STATO PATRIMONIALE ATTIVO", "0,00"),
        ("STATO PATRIMONIALE PASSIVO", None),
        ("A) Patrimonio netto", None),
        (" I) Capitale", "0,00"),
        (" IX) Utile (perdita) dell'esercizio", "0,00"),
        (" Totale Patrimonio Netto (A)", "0,00"),
        ("B) Fondi per rischi e oneri", None),
        ("C) Trattamento di fine rapporto di lavoro subordinato", "0,00"),
        ("D) Debiti", None),
        (" 7) Debiti verso fornitori", None),
        ("   a) Debiti verso fornitori esigibili entro l'esercizio successivo", "0,00"),
        (" Totale debiti verso fornitori", "0,00"),
        (" Totale debiti (D)", "0,00"),
        ("E) Ratei e risconti passivi", "0,00"),
        (" TOTALE STATO PATRIMONIALE PASSIVO", "0,00"),
    ]
    y = 40
    for label, valore in righe:
        _riga(sp, y, label=label, valore_corrente=valore)
        y += 14
    pdf = str(tmp_path / "vuoto.pdf")
    doc.save(pdf)
    doc.close()

    current, _prior = extract_standard_ivcee_balances(pdf)

    assert current is None


def test_un_vuoto_del_parser_standard_non_ferma_la_ricerca(tmp_path, monkeypatch):
    # Task 26 fix 3: un candidato ``vuoto`` (il parser standard si e' applicato per un falso
    # positivo, es. l'intestazione "dal 01/01/2025 al 31/12/2025" letta come due colonne data,
    # ma non ha restituito nulla) viene saltato: la ricerca prosegue verso la situazione
    # contabile, e il report elenca ogni candidato provato col suo esito.
    pdf = str(tmp_path / "verifica-dopo-vuoto.pdf")
    _pdf_situazione_contabile(pdf)
    monkeypatch.setattr(DET, "_prova_standard_ivcee",
                        lambda f: {"adottato": False, "parser": "standard_ivcee_parser", "esito": "vuoto"})

    esito = DET.tentativo(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA)

    assert esito["adottato"] is True
    assert esito["parser"] == "situazione_contabile_parser"
    assert esito["candidati"] == [
        {"parser": "standard_ivcee_parser", "esito": "vuoto"},
        {"parser": "situazione_contabile_parser", "esito": esito["esito"]},
    ]


def test_un_standard_che_si_applica_e_non_quadra_chiude_ancora_la_ricerca(tmp_path, monkeypatch):
    # Solo il ``vuoto`` e' saltato: un candidato che ha letto e non quadra chiude come prima.
    pdf = str(tmp_path / "verifica-dopo-oltre.pdf")
    _pdf_situazione_contabile(pdf)
    monkeypatch.setattr(DET, "_prova_standard_ivcee",
                        lambda f: {"adottato": False, "parser": "standard_ivcee_parser", "esito": "oltre_soglia"})

    esito = DET.tentativo(pdf, ocr_text=_TESTO_BILANCIO_DI_VERIFICA)

    assert esito["parser"] == "standard_ivcee_parser"
    assert esito["esito"] == "oltre_soglia"
    assert "candidati" not in esito
