import fitz

from importers.struttura_documento.mappa import _titolo_pagina, blocchi, mappa_documento, mappa_xbrl
from tests._struttura_fixtures import (MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_bilancio_verifica_senza_titoli,
                                        pdf_ce_poi_prospetto_fiscale, pdf_colonna_unica, pdf_contrapposte,
                                        pdf_intestazione_lunga_ce, pdf_prospetto_ires_costi_indeducibili,
                                        pdf_prospetto_irap_rideterminazione, pdf_titoli_spaziati,
                                        pdf_titolo_ce_contrapposte_stessa_riga, pdf_titolo_ce_semplice,
                                        pdf_xbrl_legge, pdf_xbrl_rendiconto_dopo_ce,
                                        pdf_xbrl_sp_continuazione_oltre_il_limite,
                                        pdf_xbrl_sp_continuazione_senza_date)


def test_blocchi_filtro_prosa_e_confine_sp_ce(tmp_path):
    b = blocchi(pdf_xbrl_legge(str(tmp_path / "x.pdf")))
    assert [x.pagine for x in b] == [[1], [2]]                  # la pagina 3 (prosa) non entra
    assert b[0].titolo == "stato patrimoniale" and b[1].titolo == "conto economico"


def test_titoli_spaziati_non_confondono_sp_e_ce(tmp_path):
    # Difetto A (Task 7b): un gestionale che stampa "S I T U A Z I O N E" lettera per lettera, con
    # un conto CE la cui descrizione contiene "ATTIVITA'" — oggi _titolo_pagina non riconosce il
    # titolo spaziato e cade sul fallback largo di TITOLI_SP, fondendo le pagine CE nel blocco SP.
    path = pdf_titoli_spaziati(str(tmp_path / "s.pdf"))
    b = blocchi(path)
    assert [x.pagine for x in b] == [[1, 2], [3, 4]]
    assert b[0].titolo == "stato patrimoniale" and b[1].titolo == "conto economico"

    chiamate = []

    def finta(client, png):
        chiamate.append(png)
        return dict(MAPPA_CONTRAPPOSTE)

    mappa_documento(path, mappa_pagina_fn=finta)
    assert len(chiamate) == 2


def test_pagine_senza_titolo_non_si_riusano_mai(tmp_path):
    # Rilievo (b) del riesame: un bilancio di verifica misto SP/CE senza titoli aveva finito per
    # riusare la stessa mappa su piu' pagine (sole uguali intestazioni di colonna), uscendo
    # sbilanciato. Senza un titolo a dimostrarlo, ogni pagina resta un blocco — e una chiamata — a
    # se' anche se l'intestazione di colonna e' identica.
    path = pdf_bilancio_verifica_senza_titoli(str(tmp_path / "v.pdf"))
    b = blocchi(path)
    assert [x.pagine for x in b] == [[1], [2], [3], [4], [5]]
    assert all(x.titolo is None for x in b)

    chiamate = []

    def finta(client, png):
        chiamate.append(png)
        return dict(MAPPA_CONTRAPPOSTE)

    mappa_documento(path, mappa_pagina_fn=finta)
    assert len(chiamate) == 5


def test_titolo_ce_oltre_le_15_righe_ma_dentro_1500_caratteri(tmp_path):
    # Rilievo (a) del riesame: "BILANCIO 4 SEZIONI" stampa un'intestazione aziendale lunga (20+
    # righe brevi) prima delle parole di sezione: una finestra di sole 15 righe perde il CE.
    path = pdf_intestazione_lunga_ce(str(tmp_path / "l.pdf"))
    b = blocchi(path)
    assert len(b) == 1 and b[0].titolo == "conto economico"


def test_prima_pagina_del_blocco_mantiene_la_continuazione_dichiarata(tmp_path):
    # Terzo giro del riesame: con ogni pagina senza titolo che e' ormai un blocco a se'
    # (k == 0 sempre), mappa_documento forzava "continuazione": k > 0, cioe' sempre False sulla
    # prima (e unica) pagina di ciascun blocco — anche quando il modello stesso aveva dichiarato
    # "continuazione": True su una pagina "dettaglio_conti" che continua il prospetto precedente
    # con le stesse colonne. leggi_documento la scartava, e una pagina intera di conti spariva.
    path = pdf_bilancio_verifica_senza_titoli(str(tmp_path / "v.pdf"))

    def finta(client, png):
        return {**MAPPA_CONTRAPPOSTE, "tipo_pagina": "dettaglio_conti", "continuazione": True}

    mappe = mappa_documento(path, mappa_pagina_fn=finta)
    assert [m["continuazione"] for m in mappe] == [True, True, True, True, True]


def test_continuazione_riusa_la_mappa_senza_chiamare(tmp_path):
    path = pdf_colonna_unica(str(tmp_path / "u.pdf"))
    chiamate = []

    def finta(client, png):
        chiamate.append(png)
        return dict(MAPPA_COLONNA_UNICA)

    mappe = mappa_documento(path, mappa_pagina_fn=finta)
    assert len(chiamate) == 1 and [m["pagina"] for m in mappe] == [1, 2]
    assert mappe[1]["continuazione"] is True and mappe[1]["sezioni"] == MAPPA_COLONNA_UNICA["sezioni"]
    assert mappe[0]["_chiamate"] == 1


def test_una_chiamata_per_blocco_e_cache(tmp_path):
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    n = {"v": 0}

    def finta(client, png):
        n["v"] += 1
        return dict(MAPPA_CONTRAPPOSTE)

    prima = mappa_documento(path, mappa_pagina_fn=finta, cache_dir=str(tmp_path / "cache"))
    seconda = mappa_documento(path, mappa_pagina_fn=finta, cache_dir=str(tmp_path / "cache"))
    assert n["v"] == 1 and prima == seconda and prima[0]["disposizione"] == "sezioni_contrapposte"


def test_prospetto_irap_non_e_conto_economico(tmp_path):
    # Task 28: pagina 6 del pilota FORMETAL-TEST, un prospetto di rideterminazione IRAP.
    # "Rettifiche costi" e "Rettifiche ricavi" sono due righe stampate separate da diverse
    # righe di conto: l'alternativa costi\b.*\bricavi di TITOLI_CE, senza limite di riga,
    # le fondeva in un titolo "conto economico" che non c'e'.
    path = pdf_prospetto_irap_rideterminazione(str(tmp_path / "irap.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[0]) is None


def test_prospetto_ires_non_e_conto_economico(tmp_path):
    # Task 28: pagina 5 dello stesso pilota, il prospetto IRES dei costi indeducibili. "COSTI
    # D'IMPIANTO" (una riga di conto) e "Ricavi imponibili" (una riga successiva) sono la
    # stessa coppia di parole che il vecchio pattern risolveva a distanza qualunque.
    path = pdf_prospetto_ires_costi_indeducibili(str(tmp_path / "ires.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[0]) is None


def test_titolo_ce_contrapposte_stessa_riga_resta_riconosciuto(tmp_path):
    # Task 28: il layout per cui l'alternativa costi\b.*\bricavi esiste — "COSTI, SPESE E
    # PERDITE" e "RICAVI E PROFITTI" sulla STESSA riga stampata — deve continuare a funzionare
    # dopo aver ristretto l'alternativa alla riga.
    path = pdf_titolo_ce_contrapposte_stessa_riga(str(tmp_path / "contrapposte.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[0]) == "conto economico"


def test_titoli_diretti_ce_restano_riconosciuti(tmp_path):
    # Task 28: CONTO ECONOMICO e SITUAZIONE ECONOMICA, i due segnali diretti di TITOLI_CE, non
    # devono muoversi per la correzione dell'alternativa costi/ricavi.
    for titolo in ("CONTO ECONOMICO", "SITUAZIONE ECONOMICA"):
        path = pdf_titolo_ce_semplice(str(tmp_path / f"{titolo}.pdf"), titolo)
        with fitz.open(path) as doc:
            assert _titolo_pagina(doc[0]) == "conto economico"


def test_pagina_fiscale_senza_titolo_comincia_un_blocco_suo(tmp_path):
    # Task 28, test 5: una pagina di CE vero seguita da una pagina fiscale senza intestazione
    # di colonna propria. Con il titolo corretto la seconda pagina non eredita piu' la mappa
    # della prima: due blocchi, non uno solo.
    path = pdf_ce_poi_prospetto_fiscale(str(tmp_path / "ce_fiscale.pdf"))
    b = blocchi(path)
    assert [x.pagine for x in b] == [[1], [2]]
    assert b[0].titolo == "conto economico" and b[1].titolo is None


def test_titolo_pagina_non_confonde_attivita_di_un_rendiconto(tmp_path):
    # Diagnosi budget_671 (lotto-b, fix 7): "Flussi finanziari derivanti dall'attivita' operativa"
    # non e' un titolo di Stato Patrimoniale. Il vecchio TITOLI_SP (`attivit[aà]'?\s`, senza
    # contesto di titolo) ci cadeva su qualunque pagina di Rendiconto Finanziario.
    path = pdf_xbrl_rendiconto_dopo_ce(str(tmp_path / "rend.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[2]) is None


def test_titoli_sp_reali_restano_riconosciuti_dopo_la_correzione(tmp_path):
    # La correzione di fix 7 non deve perdere i titoli SP reali: "STATO PATRIMONIALE ATTIVO"
    # (via "stato patrimoniale") e "ATTIVITA'" da sola su una riga corta (via il nuovo controllo
    # per riga, senza preposizione articolata davanti).
    path = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[0]) == "stato patrimoniale"        # "STATO PATRIMONIALE ATTIVO"
    path2 = pdf_contrapposte(str(tmp_path / "cc.pdf"))
    with fitz.open(path2) as doc2:
        assert _titolo_pagina(doc2[0]) == "stato patrimoniale"       # titolo + "ATTIVITA'"/"PASSIVITA'"


def test_mappa_xbrl_continuazione_senza_ripetere_le_date(tmp_path):
    # Diagnosi budget_671 (lotto-b, fix 6a): il vero passivo su pagina 2 non ripete ne' il
    # titolo ne' le date della pagina 1, ed era classificato "nota_o_testo" perche' mappa_xbrl
    # richiedeva l'uguaglianza esatta della tupla di date per riconoscere una continuazione.
    path = pdf_xbrl_sp_continuazione_senza_date(str(tmp_path / "sp2p.pdf"))
    mappe = mappa_xbrl(path)
    assert [m["tipo_pagina"] for m in mappe] == ["prospetto_sp", "prospetto_sp"]
    assert mappe[0]["continuazione"] is False
    assert mappe[1]["continuazione"] is True


def test_mappa_xbrl_limite_due_pagine_di_continuazione(tmp_path):
    # Bound del fix 6: al massimo due pagine di continuazione di fila, poi il blocco si chiude.
    path = pdf_xbrl_sp_continuazione_oltre_il_limite(str(tmp_path / "lim.pdf"))
    mappe = mappa_xbrl(path)
    assert [m["tipo_pagina"] for m in mappe] == ["prospetto_sp", "prospetto_sp", "prospetto_sp", "nota_o_testo"]
    assert [m["continuazione"] for m in mappe] == [False, True, True, False]


def test_mappa_xbrl_non_assorbe_il_rendiconto_dopo_il_ce(tmp_path):
    # Bound del fix 6: una pagina che apre una sezione nuova (Rendiconto finanziario) non
    # diventa mai una continuazione, anche se non ha titolo di prospetto proprio e ha importi.
    path = pdf_xbrl_rendiconto_dopo_ce(str(tmp_path / "rend.pdf"))
    mappe = mappa_xbrl(path)
    assert mappe[0]["tipo_pagina"] == "prospetto_sp"
    assert mappe[1]["tipo_pagina"] == "prospetto_ce"
    assert mappe[2]["tipo_pagina"] == "nota_o_testo"
    assert mappe[2]["continuazione"] is False


def test_mappa_pagina_produce_lo_schema(monkeypatch):
    from importers.struttura_documento import mappa as m

    class Blocco:
        type = "tool_use"
        input = {**MAPPA_CONTRAPPOSTE}

    class Uso:
        input_tokens, output_tokens = 3000, 500

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                assert kw["tool_choice"] == {"type": "tool", "name": "struttura"}
                assert kw["messages"][0]["content"][0]["type"] == "image"
                return type("R", (), {"content": [Blocco()], "usage": Uso()})()

    out = m.mappa_pagina(Client(), b"png")
    assert out["disposizione"] == "sezioni_contrapposte" and out["_token"] == {"in": 3000, "out": 500}
