import fitz

from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.analisi import (
    Struttura, _assorbi_continuazioni_perse, analizza_struttura, modo_da_mappe, pagine_tabelle_nota,
    route_da_mappe)
from tests._struttura_fixtures import (MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_contrapposte,
                                       pdf_xbrl_con_tabelle_nota, pdf_xbrl_legge)


def _m(tipo, schema):
    return {"tipo_pagina": tipo, "schema": schema}


def test_route_da_mappe_conti_contro_legge():
    assert route_da_mappe([_m("prospetto_sp", "piano_dei_conti_gerarchico"),
                           _m("prospetto_ce", "piano_dei_conti_gerarchico")]) == ROUTE_TRIAL
    assert route_da_mappe([_m("prospetto_sp", "iv_cee_di_legge"),
                           _m("prospetto_ce", "riclassificato_con_codici_ivcee")]) == ROUTE_IVCEE
    assert route_da_mappe([_m("nota_o_testo", "elenco_piatto")]) is None       # nessun prospetto
    assert route_da_mappe([_m("prospetto_sp", "elenco_piatto"),
                           _m("prospetto_ce", "iv_cee_di_legge")]) is None     # pari: decide il classificatore


def test_xbrl_di_legge_zero_chiamate_e_pagine_dai_titoli(tmp_path):
    s = analizza_struttura(pdf_xbrl_legge(str(tmp_path / "x.pdf")),
                           mappa_pagina_fn=lambda c, png: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.fonte == "xbrl_titoli" and s.chiamate_vision == 0
    assert s.route == ROUTE_IVCEE
    assert s.pagine_sp == [1] and s.pagine_ce == [2]


def test_contrapposte_una_chiamata_per_blocco_e_route_c(tmp_path):
    chiamate = []
    def finta(client, png):
        chiamate.append(png)
        return {**MAPPA_CONTRAPPOSTE, "schema": "piano_dei_conti_gerarchico"}
    s = analizza_struttura(pdf_contrapposte(str(tmp_path / "c.pdf")), mappa_pagina_fn=finta)
    assert s.fonte == "vision" and s.chiamate_vision == len(chiamate) >= 1
    assert s.route == ROUTE_TRIAL


def test_tabelle_nota_dai_titoli_standard(tmp_path):
    path = pdf_xbrl_con_tabelle_nota(str(tmp_path / "n.pdf"))
    pagine = pagine_tabelle_nota(path)
    assert pagine == [4]
    s = analizza_struttura(path, mappa_pagina_fn=lambda c, p: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.pagine_dettaglio == pagine
    assert not set(pagine) & (set(s.pagine_sp) | set(s.pagine_ce))


def test_insiemi_vuoti_non_restringono():
    s = Struttura(fonte="vision", route=None, pagine_sp=[], pagine_ce=[], pagine_dettaglio=[],
                  chiamate_vision=1, secondi=0.1, mappe=[])
    assert s.pagine_macro() is None and s.pagine_dettagli() is None
    s2 = Struttura(fonte="vision", route=ROUTE_IVCEE, pagine_sp=[1, 2], pagine_ce=[3], pagine_dettaglio=[],
                   chiamate_vision=1, secondi=0.1, mappe=[])
    assert s2.pagine_macro() == {1, 2, 3}
    assert s2.pagine_dettagli() == {1, 2}           # senza tabelle di nota: le pagine SP (sottoconti)
    r = s2.report()
    assert r["stato"] == "ok" and r["route_struttura"] == ROUTE_IVCEE and r["pagine_sp"] == [1, 2]
    assert "mappe" not in r                          # il report persistito non porta le mappe intere


def _p(pagina, tipo, schema, ruoli, intest):
    return {"pagina": pagina, "tipo_pagina": tipo, "schema": schema,
            "sezioni": [{"posizione": "unica", "contenuto": "misto",
                         "colonne": [{"ruolo": r, "intestazione": i} for r, i in zip(ruoli, intest)]}]}


def test_modo_conti_o_legge():
    assert modo_da_mappe([_p(1, "prospetto_sp", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "elenco_piatto", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["2025"])]) == "legge"
    # Ruling del controllo (lotto-b, fix 9): un documento "riclassificato con codici IVCEE" e'
    # un elenco di conti denso, non uno schema di legge da leggere come tale — 8 file del banco
    # fallivano cosi'. Prima di questo giro un solo schema riclassificato dava "legge": la
    # vecchia asserzione codificava quella regola, ora sostituita di proposito.
    assert modo_da_mappe([_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]) == "conti"


def test_modo_legge_quando_riclassificato_porta_captions_legali_con_totali(tmp_path, monkeypatch):
    # Task 18, ruling (c) (owner, dopo la diagnosi AMBIENTA §7-8): un "riclassificato con
    # codici IVCEE" che e' ANCHE uno schema di legge puro (captions B)/C)/D), I/II/III,
    # colonne comparative con TOTALI stampati - has_comparative_ivcee_columns) va letto come
    # "legge": i totali di livello superiore si leggono DIRETTAMENTE dalla riga stampata, non
    # si ricostruiscono sommando le foglie (il limite strutturale di marca_totali su una
    # gerarchia a 5 livelli, diagnosi AMBIENTA causa radice #2). Senza `pdf` il comportamento
    # di sempre (fix round 1, Task lotto-b) resta intatto - vedi test sopra.
    monkeypatch.setattr(
        "importers.standard_ivcee_parser.has_comparative_ivcee_columns", lambda pdf: True)
    mappe = [_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, pdf=str(tmp_path / "qualsiasi.pdf")) == "legge"


def test_modo_conti_quando_riclassificato_non_porta_captions_legali(tmp_path, monkeypatch):
    # Simmetrico: senza le colonne comparative (un elenco analitico per mastro senza schema
    # di legge, gli 8 file del banco 26/09 che hanno motivato la regola "riclassificato ->
    # conti" di fix round 1), il documento resta "conti" anche passando `pdf`.
    monkeypatch.setattr(
        "importers.standard_ivcee_parser.has_comparative_ivcee_columns", lambda pdf: False)
    mappe = [_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, pdf=str(tmp_path / "qualsiasi.pdf")) == "conti"


def test_modo_conti_riclassificato_senza_pdf_non_chiama_has_comparative(tmp_path, monkeypatch):
    # Nessun `pdf` (il default): non si deve nemmeno provare ad aprirlo - ogni chiamante che
    # non lo passa (ad es. i test unitari di questo file) resta sul comportamento di sempre a
    # costo zero, mai un tentativo di apertura file su un percorso finto.
    def _esplode(pdf):
        raise AssertionError("has_comparative_ivcee_columns chiamata senza pdf")
    monkeypatch.setattr("importers.standard_ivcee_parser.has_comparative_ivcee_columns", _esplode)
    mappe = [_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe) == "conti"


def test_modo_da_mappe_ignora_pdf_quando_nessuno_schema_e_riclassificato(tmp_path, monkeypatch):
    # Il controllo costa un'apertura file: si prova SOLO quando almeno una pagina e' davvero
    # schema "riclassificato_con_codici_ivcee" - un documento di puro schema di legge
    # (iv_cee_di_legge) non deve nemmeno sfiorare has_comparative_ivcee_columns.
    def _esplode(pdf):
        raise AssertionError("has_comparative_ivcee_columns chiamata senza motivo")
    monkeypatch.setattr("importers.standard_ivcee_parser.has_comparative_ivcee_columns", _esplode)
    mappe = [_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, pdf=str(tmp_path / "qualsiasi.pdf")) == "legge"


def test_modo_conti_per_pareggio_con_indizio_trial_balance():
    # Diagnosi budget_313 (lotto-b, fix 9): un voto in parita' fra schema conti e schema legge,
    # accompagnato dall'indizio del classificatore (route TRIAL_BALANCE), sceglie "conti" — senza
    # l'indizio il pareggio resta "legge" come oggi.
    mappe = [_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"]),
             _p(2, "prospetto_ce", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe) == "legge"
    assert modo_da_mappe(mappe, route_hint=ROUTE_TRIAL) == "conti"


def test_modo_legge_nonostante_indizio_trial_balance_se_il_voto_non_e_in_parita():
    # L'indizio pesa solo su un voto vicino alla parita' (margine <=1 pagina): con una maggioranza
    # netta per lo schema di legge il documento resta letto come "legge".
    mappe = [_p(i, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"]) for i in range(1, 5)]
    mappe.append(_p(5, "prospetto_ce", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["x"]))
    assert modo_da_mappe(mappe, route_hint=ROUTE_TRIAL) == "legge"


def test_modo_legge_con_n1_nonostante_indizio_trial_balance():
    # Fix round 1, gap 3: con una sola pagina, tutta di schema legge, il voto e' UNANIME — non
    # "vicino alla parita'" in alcun senso utile — e l'indizio non ha titolo per ribaltarlo.
    # Prima del fix `margine = n - conti*2 = 1 - 0 = 1 <= MARGINE_PAREGGIO_MODO` scattava lo
    # stesso, dando "conti" su un documento a pagina singola senza un solo voto per "conti".
    mappe = [_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, route_hint=ROUTE_TRIAL) == "legge"


def test_modo_legge_unanime_a_due_pagine_nonostante_indizio_trial_balance():
    # Due pagine, entrambe schema legge (voto unanime, non conteso): l'indizio non decide.
    mappe = [_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"]),
             _p(2, "prospetto_ce", "iv_cee_di_legge", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, route_hint=ROUTE_TRIAL) == "legge"


def test_modo_conti_forma_ambienta_tre_legge_due_conti_con_indizio():
    # Forma AMBIENTA (diagnosi lotto-b): 3 pagine schema legge, 2 schema conti — un voto CONTESO
    # (almeno un voto per lato) e vicino alla parita' (margine 1): con l'indizio TRIAL_BALANCE
    # sceglie "conti"; senza l'indizio resta "legge" come un pareggio non deciso da solo.
    mappe = ([_p(i, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["x"]) for i in (1, 2, 3)]
             + [_p(i, "prospetto_ce", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["x"]) for i in (4, 5)])
    assert modo_da_mappe(mappe) == "legge"
    assert modo_da_mappe(mappe, route_hint=ROUTE_TRIAL) == "conti"


def test_vision_assorbe_pagina_senza_tipo_fra_due_pagine_dello_stesso_prospetto(tmp_path):
    # Lotto-b, fix 6b: la vision ha lasciato "nota_o_testo" una pagina che sta subito dopo un
    # prospetto gia' classificato, con importi veri (come budget_972/614/158): va assorbita come
    # continuazione dello stesso prospetto, non persa in silenzio.
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    for i, riga in enumerate(["voce a  10,00  9,00", "voce b  20,00  19,00", "voce c  30,00  29,00"]):
        p2.insert_text((30, 30 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / "v.pdf")
    doc.save(path)

    mappe = [
        {"pagina": 1, "tipo_pagina": "prospetto_ce", "schema": "iv_cee_di_legge",
         "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False},
        {"pagina": 2, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto", "sezioni": [], "continuazione": False},
    ]
    out = _assorbi_continuazioni_perse(mappe, path)
    assert out[1]["tipo_pagina"] == "prospetto_ce"
    assert out[1]["continuazione"] is True


def test_vision_non_assorbe_oltre_una_nota_integrativa(tmp_path):
    # La stessa pagina "nota_o_testo" con importi non si assorbe se il suo testo apre una
    # sezione diversa (qui: Nota integrativa) — stesso limite di mappa_xbrl (fix 6a).
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((30, 30), "Nota integrativa", fontname="helv", fontsize=10)
    for i, riga in enumerate(["voce a  10,00  9,00", "voce b  20,00  19,00", "voce c  30,00  29,00"]):
        p2.insert_text((30, 50 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / "v2.pdf")
    doc.save(path)

    mappe = [
        {"pagina": 1, "tipo_pagina": "prospetto_sp", "schema": "iv_cee_di_legge",
         "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False},
        {"pagina": 2, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto", "sezioni": [], "continuazione": False},
    ]
    out = _assorbi_continuazioni_perse(mappe, path)
    assert out[1]["tipo_pagina"] == "nota_o_testo"
    assert out[1]["continuazione"] is False


def test_vision_non_assorbe_oltre_un_rendiconto_dietro_un_intestazione_ripetuta(tmp_path):
    # Fix round 1, gap 1: un running header ("ACME SRL - Bilancio al 31-12-2025") come prima riga
    # di testa, con "Rendiconto finanziario" solo sulla seconda, non deve far passare la pagina.
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((30, 30), "ACME SRL - Bilancio al 31-12-2025", fontname="helv", fontsize=8)
    p2.insert_text((30, 44), "Rendiconto finanziario", fontname="helv", fontsize=10)
    for i, riga in enumerate(["voce a  10,00  9,00", "voce b  20,00  19,00", "voce c  30,00  29,00"]):
        p2.insert_text((30, 64 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / "v2b.pdf")
    doc.save(path)

    mappe = [
        {"pagina": 1, "tipo_pagina": "prospetto_ce", "schema": "iv_cee_di_legge",
         "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False},
        {"pagina": 2, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto", "sezioni": [], "continuazione": False},
    ]
    out = _assorbi_continuazioni_perse(mappe, path)
    assert out[1]["tipo_pagina"] == "nota_o_testo"
    assert out[1]["continuazione"] is False


def test_vision_limite_due_pagine_di_continuazione(tmp_path):
    # Stesso bound di mappa_xbrl (fix 6a): al massimo due pagine di continuazione di fila.
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    for _ in range(3):
        pagina = doc.new_page(width=595, height=842)
        for i, riga in enumerate(["voce a  10,00  9,00", "voce b  20,00  19,00", "voce c  30,00  29,00"]):
            pagina.insert_text((30, 30 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / "v3.pdf")
    doc.save(path)

    mappe = [{"pagina": 1, "tipo_pagina": "prospetto_sp", "schema": "iv_cee_di_legge",
              "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False}]
    for p in range(2, 5):
        mappe.append({"pagina": p, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto",
                      "sezioni": [], "continuazione": False})
    out = _assorbi_continuazioni_perse(mappe, path)
    assert [m["tipo_pagina"] for m in out] == ["prospetto_sp", "prospetto_sp", "prospetto_sp", "nota_o_testo"]
    assert [m["continuazione"] for m in out] == [False, True, True, False]


def test_vision_assorbimento_riscrive_lo_schema_col_blocco(tmp_path):
    # Fix round 1, gap 2: una pagina assorbita come continuazione teneva il proprio `schema`
    # stantio (quello che la vision le aveva dato prima di essere assorbita, o il default della
    # pagina mai vista), che continuava a votare in `modo_da_mappe` come se fosse una pagina
    # indipendente. Un CE vero (iv_cee_di_legge) con una pagina di continuazione "elenco_piatto"
    # (schema di conti) dava un voto 1 a 1 — vicino alla parita' — e con l'indizio TRIAL_BALANCE
    # sceglieva "conti" per errore. Dopo il fix lo schema della continuazione e' quello del
    # blocco, il voto e' 2 a 0 per "legge" e l'indizio non ha piu' potere di ribaltarlo.
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    for i, riga in enumerate(["voce a  10,00  9,00", "voce b  20,00  19,00", "voce c  30,00  29,00"]):
        p2.insert_text((30, 30 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / "v4.pdf")
    doc.save(path)

    mappe = [
        {"pagina": 1, "tipo_pagina": "prospetto_ce", "schema": "iv_cee_di_legge",
         "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False},
        {"pagina": 2, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto", "sezioni": [], "continuazione": False},
    ]
    out = _assorbi_continuazioni_perse(mappe, path)
    assert out[1]["tipo_pagina"] == "prospetto_ce" and out[1]["continuazione"] is True
    assert out[1]["schema"] == "iv_cee_di_legge"
    assert modo_da_mappe(out, route_hint=ROUTE_TRIAL) == "legge"


def test_analizza_struttura_passa_route_hint_a_modo_da_mappe(tmp_path, monkeypatch):
    catturato = {}
    from importers.struttura_documento import analisi as A

    originale = A.modo_da_mappe

    def spia(mappe, *, route_hint=None, pdf=None):
        catturato["route_hint"] = route_hint
        catturato["pdf"] = pdf
        return originale(mappe, route_hint=route_hint, pdf=pdf)

    monkeypatch.setattr(A, "modo_da_mappe", spia)
    pdf_path = pdf_xbrl_legge(str(tmp_path / "x.pdf"))
    analizza_struttura(pdf_path, route_hint=ROUTE_TRIAL)
    assert catturato["route_hint"] == ROUTE_TRIAL
    # Task 18, ruling (c): analizza_struttura deve passare il PROPRIO file a modo_da_mappe,
    # non solo route_hint - senza il file, il segnale delle captions legali con totali
    # stampati (has_comparative_ivcee_columns) non e' disponibile a chi decide il modo.
    assert catturato["pdf"] == pdf_path


def test_struttura_porta_colonne_e_pagine_senza_testo(tmp_path):
    from importers.struttura_documento.analisi import analizza_struttura
    from tests._struttura_fixtures import pdf_colonna_unica, MAPPA_COLONNA_UNICA
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    s = analizza_struttura(pdf, mappa_pagina_fn=lambda client, png: MAPPA_COLONNA_UNICA)
    assert s.modo in ("conti", "legge")
    assert s.colonne_sp and all(isinstance(r, str) for r in s.colonne_sp)
    assert s.pagine_senza_testo == []


def test_analizza_struttura_riclassificato_con_captions_legali_e_legge_con_macro_dettaglio(tmp_path):
    # Task 18, ruling (c) (owner, dopo la diagnosi AMBIENTA §7-8): `pdf_colonna_unica` e'
    # esattamente la forma AMBIENTA in miniatura - "riclassificato con codici IVCEE" +
    # colonne comparative "Importo corrente | Importo comparato" con totali stampati.
    # analizza_struttura deve sceglierlo "legge" (non "conti") E accendere
    # macro_include_dettaglio, cosi' che import_snello includa le pagine_dettaglio anche nel
    # prompt macro di SP/CE.
    from importers.struttura_documento.analisi import analizza_struttura
    from tests._struttura_fixtures import pdf_colonna_unica, MAPPA_COLONNA_UNICA
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    s = analizza_struttura(pdf, mappa_pagina_fn=lambda client, png: MAPPA_COLONNA_UNICA)
    assert s.modo == "legge"
    assert s.macro_include_dettaglio is True


def _pdf_ce_con_coda(tmp_path, righe_coda, nome="coda.pdf"):
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((30, 30), "voce 1  100,00", fontname="helv", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    for i, riga in enumerate(righe_coda):
        p2.insert_text((30, 30 + i * 14), riga, fontname="helv", fontsize=8)
    path = str(tmp_path / nome)
    doc.save(path)
    return path


_MAPPE_CE_E_NOTA = [
    {"pagina": 1, "tipo_pagina": "prospetto_ce", "schema": "iv_cee_di_legge",
     "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": []}], "continuazione": False},
    {"pagina": 2, "tipo_pagina": "nota_o_testo", "schema": "elenco_piatto", "sezioni": [], "continuazione": False},
]

# Come l'ultima pagina del CE di budget_115: pochi importi con separatore, tanti zeri e interi < 1.000.
_CODA_CE_115 = ["CONTO ECONOMICO", "iv) da altri 426 164", "17) Interessi e altri oneri finanziari -610 -986",
                "17-bis) Utili e perdite su cambi 0 0", "TOTALE -184 -822",
                "Risultato prima delle imposte 36.929 41.504",
                "21) utile (perdita) dell'esercizio 36.929 41.504"]


def test_continuazione_del_ce_con_il_risultato_si_tiene_anche_con_pochi_importi_con_separatore(tmp_path):
    """Task 27, item 4 (diagnosi budget_115): l'ultima pagina del CE ha 4 importi con separatore
    (< MIN_IMPORTI) ma continua la sezione aperta e porta la riga del risultato: zeri e interi
    sotto 1.000 contano come importi su una pagina cosi', e non si perde 16)/17)."""
    path = _pdf_ce_con_coda(tmp_path, _CODA_CE_115)
    out = _assorbi_continuazioni_perse(_MAPPE_CE_E_NOTA, path)
    assert out[1]["tipo_pagina"] == "prospetto_ce" and out[1]["continuazione"] is True


def test_continuazione_senza_chiusura_o_con_pochi_numeri_non_si_assorbe(tmp_path):
    senza_chiusura = [r for r in _CODA_CE_115 if "utile" not in r and "Risultato" not in r]
    out = _assorbi_continuazioni_perse(_MAPPE_CE_E_NOTA, _pdf_ce_con_coda(tmp_path, senza_chiusura, "a.pdf"))
    assert out[1]["tipo_pagina"] == "nota_o_testo"
    poche = ["CONTO ECONOMICO", "21) utile (perdita) dell'esercizio 36.929 41.504"]
    out = _assorbi_continuazioni_perse(_MAPPE_CE_E_NOTA, _pdf_ce_con_coda(tmp_path, poche, "b.pdf"))
    assert out[1]["tipo_pagina"] == "nota_o_testo"


def test_continuazione_con_chiusura_non_attraversa_una_sezione_diversa(tmp_path):
    coda = ["Nota integrativa"] + _CODA_CE_115
    out = _assorbi_continuazioni_perse(_MAPPE_CE_E_NOTA, _pdf_ce_con_coda(tmp_path, coda, "c.pdf"))
    assert out[1]["tipo_pagina"] == "nota_o_testo"


def test_continuazione_dello_sp_con_totale_passivo(tmp_path):
    mappe = [dict(_MAPPE_CE_E_NOTA[0], tipo_pagina="prospetto_sp"), _MAPPE_CE_E_NOTA[1]]
    coda = ["STATO PATRIMONIALE", "E) Ratei e risconti 0 0", "d) Debiti verso altri 905 810",
            "Altri debiti 18 22", "Ratei e risconti passivi 4.518 3.900", "TOTALE PASSIVO 1.570.211 1.500.000"]
    out = _assorbi_continuazioni_perse(mappe, _pdf_ce_con_coda(tmp_path, coda, "d.pdf"))
    assert out[1]["tipo_pagina"] == "prospetto_sp" and out[1]["continuazione"] is True


def test_nota_che_cita_la_perdita_dell_esercizio_in_prosa_non_e_una_continuazione(tmp_path):
    """La chiusura e' una RIGA che comincia col risultato, non una frase di nota che lo cita
    (budget_272, misurato sul corpus: una pagina di nota con importi sparsi e 'perdita
    dell'esercizio di Euro 5.570' a meta' riga)."""
    coda = ["CONTO ECONOMICO", "1 2 3 4 5 6 7 8", "Si propone di coprire la perdita dell'esercizio di",
            "Euro 5.570 mediante impiego della riserva straordinaria 0 0 12"]
    out = _assorbi_continuazioni_perse(_MAPPE_CE_E_NOTA, _pdf_ce_con_coda(tmp_path, coda, "e.pdf"))
    assert out[1]["tipo_pagina"] == "nota_o_testo"


def _mappa_colonne(ruoli, intestazioni):
    return [{"tipo_pagina": "prospetto_sp", "sezioni": [{"colonne": [
        {"ruolo": r, "intestazione": i} for r, i in zip(ruoli, intestazioni)]}]}]


def test_i_ruoli_di_colonna_vengono_dalle_intestazioni_stampate_se_la_vision_non_da_un_saldo():
    """budget_1445 (Crystal Reports): la vision dichiara [dare, avere, dare, avere] su colonne
    stampate «Periodo fino al 30/06/2026 | Bilancio infrannuale al 30/06/2025 | Diff. % | Diff.
    Valore». Senza una colonna di saldo il lettore prendeva l'ultimo importo: la Diff. Valore."""
    from importers.struttura_documento.analisi import _colonne_di
    intestazioni = ["Periodo fino al 30/06/2026", "Bilancio infrannuale al 30/06/2025 EXC",
                    "Diff. %", "Diff. Valore"]
    ruoli, _ = _colonne_di(_mappa_colonne(["dare", "avere", "dare", "avere"], intestazioni),
                           {"prospetto_sp"})
    assert ruoli == ["saldo_corrente", "saldo_precedente", "percentuale", "variazione"]


def test_intestazioni_dare_avere_lasciano_i_ruoli_della_vision():
    from importers.struttura_documento.analisi import _colonne_di
    ruoli, _ = _colonne_di(_mappa_colonne(["dare", "avere"], ["Dare 2026", "Avere 2026"]),
                           {"prospetto_sp"})
    assert ruoli == ["dare", "avere"]


def test_una_colonna_di_saldo_della_vision_resta():
    from importers.struttura_documento.analisi import _colonne_di
    ruoli, _ = _colonne_di(_mappa_colonne(["saldo_finale", "altro"], ["31/12/2025", "Diff."]),
                           {"prospetto_sp"})
    assert ruoli == ["saldo_finale", "altro"]


def test_la_pagina_dove_si_apre_il_conto_economico_e_anche_una_pagina_ce():
    """budget_1433/1434 (Panificio): il CE comincia in fondo a pagina 1 (titolo, valore della
    produzione, ricavi 892.889,82) e la vision da' pagine_ce=[2]. I ricavi non li leggeva
    nessuno: utile CE -948.971,67 contro -56.081,85 stampato."""
    from importers.struttura_documento.analisi import _pagine_di_apertura
    testi = {1: "Stato patrimoniale\nTOTALE PASSIVO\n1.275.796,13\nConto economico\nA) Valore della produzione",
             2: "5) Altri ricavi e proventi\nB) Costi della produzione"}
    assert _pagine_di_apertura([1], [2], testi) == ([1], [1, 2])


def test_una_pagina_che_cita_il_conto_economico_nel_testo_non_e_una_pagina_ce():
    from importers.struttura_documento.analisi import _pagine_di_apertura
    testi = {1: "Stato patrimoniale\nle voci del conto economico sono in pagina 2", 2: "CONTO ECONOMICO"}
    assert _pagine_di_apertura([1], [2], testi) == ([1], [2])


def test_pagine_non_adiacenti_restano_come_sono():
    from importers.struttura_documento.analisi import _pagine_di_apertura
    testi = {5: "Conto economico", 1: "x"}
    assert _pagine_di_apertura([5, 6], [1, 2], testi) == ([5, 6], [1, 2])


def test_didascalie_di_riga_dichiarate_come_colonne_si_sostituiscono_con_le_colonne_dell_altra_sezione():
    """budget_1433 (Panificio): la vision dichiara come colonne del CE diciassette didascalie di
    riga («5) Altri ricavi e proventi», «B) Costi della produzione»...). Il modello leggeva i
    valori «sotto» quelle colonne e saltava i ricavi. Non sono colonne: si usano quelle dello SP."""
    from importers.struttura_documento.analisi import _colonne_vere
    sp = (["saldo_corrente"], ["11/09/2026"])
    ce = (["variazione"] * 5, ["5) Altri ricavi e proventi", "B) Costi della produzione",
                               "6) Materie prime", "7) Servizi", "Differenza A – B"])
    assert _colonne_vere(ce, sp) == sp
    assert _colonne_vere(sp, ce) == sp           # intestazioni vere: restano
    assert _colonne_vere(ce, ce) == ([], [])     # nessuna alternativa: nessuna intestazione


def test_i_titoli_stampati_decidono_le_pagine_se_la_vision_li_contraddice():
    """budget_1445 (Crystal Reports, 14 pagine): titoli «STATO PATRIMONIALE ATTIVO» a p.1,
    «... PASSIVO» a p.6, «CONTO ECONOMICO» a p.9. La vision dava SP [3, 5] e CE [1, 6, 9, 12,
    13, 14]: pagine del CE PRIMA del suo titolo. La contraddizione col testo fa decidere i titoli."""
    from importers.struttura_documento.analisi import _pagine_dai_titoli
    testi = {n: "voce 1.000,00\n" * 6 for n in range(1, 15)}
    testi[1] = "STATO PATRIMONIALE ATTIVO\n" + testi[1]
    testi[6] = "STATO PATRIMONIALE PASSIVO\n" + testi[6]
    testi[9] = "CONTO ECONOMICO\n" + testi[9]
    sp, ce = _pagine_dai_titoli([3, 5], [1, 6, 9, 12, 13, 14], testi)
    assert sp == [1, 2, 3, 4, 5, 6, 7, 8]
    assert ce == [9, 10, 11, 12, 13, 14]


def test_senza_contraddizione_restano_le_pagine_della_vision():
    from importers.struttura_documento.analisi import _pagine_dai_titoli
    testi = {1: "STATO PATRIMONIALE\n" + "x 1.000,00\n" * 6, 2: "CONTO ECONOMICO\n" + "x 1.000,00\n" * 6,
             3: "x 1.000,00\n" * 6}
    assert _pagine_dai_titoli([1], [2], testi) == ([1], [2])


def test_le_colonne_si_ordinano_come_le_intestazioni_stampate():
    """budget_1445: la vision elenca [Diff. %, Diff. Valore, 2025, 2026], la stampa va da
    sinistra 2026, 2025, Diff. %, Diff. Valore. Il saldo corrente e' la prima colonna, non
    l'ultima (che e' la Diff. Valore)."""
    from importers.struttura_documento.analisi import _ordina_colonne
    parole = [(319, 122, 0, 0, "Periodo"), (334, 132, 0, 0, "30/06/2026"),
              (414, 122, 0, 0, "Biancio"), (390, 141, 0, 0, "30/06/2025"),
              (465, 122, 0, 0, "Diff."), (481, 122, 0, 0, "%"),
              (527, 122, 0, 0, "Diff."), (543, 122, 0, 0, "Valore"),
              (60, 300, 0, 0, "Diff.")]                        # una parola del corpo
    ruoli = ["variazione", "variazione", "saldo_precedente", "saldo_corrente"]
    intest = ["Diff. %", "Diff. Valore", "Bilancio infrannuale al 30/06/2025 EXC",
              "Periodo fino al 30/06/2026"]
    assert _ordina_colonne(ruoli, intest, parole) == (
        ["saldo_corrente", "saldo_precedente", "variazione", "variazione"],
        ["Periodo fino al 30/06/2026", "Bilancio infrannuale al 30/06/2025 EXC", "Diff. %",
         "Diff. Valore"])


def test_intestazioni_non_trovate_lasciano_l_ordine_della_vision():
    from importers.struttura_documento.analisi import _ordina_colonne
    assert _ordina_colonne(["saldo_corrente"], ["Importo"], [(10, 10, 0, 0, "Altro")]) == (
        ["saldo_corrente"], ["Importo"])


def test_la_prima_pagina_del_ce_con_la_coda_dello_sp_sopra_il_titolo_e_anche_sp():
    """budget_1432 (Panificio, situazione contabile): la pagina 2 comincia con crediti, cassa e
    debiti dello SP e apre «Conto Economico» a meta' pagina. La vision dava SP [1] e CE [2]: la
    lettura SP non vedeva la coda del passivo (letto 512.231,24 contro 2.056.081,31)."""
    from importers.struttura_documento.analisi import _pagine_di_apertura
    testi = {1: "Stato Patrimoniale\n" + "x 1.000,00\n" * 6,
             2: "11 CREDITI 229.453,67\n15 CASSA 116.868,27\n23 DEBITI 5.408,36\n"
                "18 PATRIMONIO NETTO 99.239,60\nConto Economico dal 01/01/2026\n" + "y 2,00\n" * 6}
    assert _pagine_di_apertura([1], [2], testi) == ([1, 2], [2])


def test_il_titolo_del_ce_in_testa_alla_pagina_non_la_rende_sp():
    from importers.struttura_documento.analisi import _pagine_di_apertura
    testi = {1: "Stato Patrimoniale\n" + "x 1.000,00\n" * 6,
             2: "Conto Economico\n" + "y 2,00\n" * 6}
    assert _pagine_di_apertura([1], [2], testi) == ([1], [2])


def test_una_situazione_a_sezioni_contrapposte_resta_in_modo_conti(tmp_path, monkeypatch):
    """budget_1432 (Panificio, situazione contabile a sezioni contrapposte con codici conto): la
    vision dice «riclassificato con codici IVCEE» (conti) ma l'eccezione AMBIENTA lo rigirava in
    «legge», e il modello mescolava lordi e fondi (sbilancio 585.819). Conti su due lati non sono
    uno schema di legge: l'eccezione non vale."""
    monkeypatch.setattr(
        "importers.standard_ivcee_parser.has_comparative_ivcee_columns", lambda pdf: True)
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.is_contrapposte_file", lambda pdf: True)
    mappe = [_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]
    assert modo_da_mappe(mappe, pdf=str(tmp_path / "qualsiasi.pdf")) == "conti"
