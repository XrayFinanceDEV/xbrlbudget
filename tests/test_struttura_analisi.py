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
