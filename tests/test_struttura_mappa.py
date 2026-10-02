import fitz
import pytest

from importers.struttura_documento.mappa import _titolo_pagina, blocchi, mappa_documento, mappa_xbrl
from tests._struttura_fixtures import (MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_bilancio_verifica_senza_titoli,
                                        pdf_ce_poi_prospetto_fiscale, pdf_colonna_unica, pdf_contrapposte,
                                        pdf_intestazione_lunga_ce, pdf_prospetto_ires_costi_indeducibili,
                                        pdf_prospetto_irap_rideterminazione, pdf_sp_poi_rendiconto_senza_ce,
                                        pdf_titoli_spaziati,
                                        pdf_titolo_ce_contrapposte_stessa_riga, pdf_titolo_ce_semplice,
                                        pdf_xbrl_legge, pdf_xbrl_rendiconto_con_attivita_senza_preposizione,
                                        pdf_xbrl_rendiconto_con_intestazione_ripetuta,
                                        pdf_xbrl_rendiconto_dopo_ce,
                                        pdf_xbrl_sp_continuazione_oltre_il_limite,
                                        pdf_xbrl_sp_continuazione_senza_date,
                                        pdf_xbrl_sp_continuazione_tre_pagine_con_totale_passivo)


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


def test_mappa_xbrl_non_assorbe_il_rendiconto_dietro_un_intestazione_ripetuta(tmp_path):
    # Fix round 1, gap 1: il vecchio `_apre_sezione_nuova` guardava solo la riga 0. Una pagina
    # con un running header ("ACME SRL - Bilancio al 31-12-2025") come prima riga e "Rendiconto
    # finanziario" come seconda passava indisturbata e veniva assorbita come continuazione del CE.
    path = pdf_xbrl_rendiconto_con_intestazione_ripetuta(str(tmp_path / "rend2.pdf"))
    mappe = mappa_xbrl(path)
    assert mappe[2]["tipo_pagina"] == "nota_o_testo"
    assert mappe[2]["continuazione"] is False


def test_mappa_pagina_produce_lo_schema(monkeypatch):
    """Sonnet 5.5 (2026-10-02): l'uso forzato di uno strumento (tool_choice tool/any) e' un 400
    su quel modello. La struttura si chiede con l'uscita strutturata (output_config.format),
    che vale anche su Sonnet 5; il ragionamento e' sempre acceso e conta in max_tokens."""
    import json as _json
    from importers.struttura_documento import mappa as m

    class Pensiero:
        type, thinking = "thinking", ""

    class Testo:
        type = "text"
        text = _json.dumps(MAPPA_CONTRAPPOSTE)

    class Uso:
        input_tokens, output_tokens = 3000, 500

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                assert "tool_choice" not in kw and "tools" not in kw
                formato = kw["output_config"]["format"]
                assert formato["type"] == "json_schema" and formato["schema"]["additionalProperties"] is False
                assert kw["max_tokens"] >= 4000
                assert kw["messages"][0]["content"][0]["type"] == "image"
                return type("R", (), {"content": [Pensiero(), Testo()], "usage": Uso(),
                                      "stop_reason": "end_turn"})()

    out = m.mappa_pagina(Client(), b"png")
    assert out["disposizione"] == "sezioni_contrapposte" and out["_token"] == {"in": 3000, "out": 500}


def test_mappa_pagina_senza_testo_o_troncata_solleva():
    from importers.struttura_documento import mappa as m

    class Uso:
        input_tokens, output_tokens = 3000, 4000

    def client(stop, blocchi):
        class C:
            class messages:
                @staticmethod
                def create(**kw):
                    return type("R", (), {"content": blocchi, "usage": Uso(), "stop_reason": stop})()
        return C()

    class Tronco:
        type, text = "text", '{"tipo_pagina": "prospetto_sp", "dispos'

    for stop, blocchi in (("max_tokens", [Tronco()]), ("refusal", []), ("end_turn", [])):
        with pytest.raises(RuntimeError):
            m.mappa_pagina(client(stop, blocchi), b"png")


# --- Task 22, G5 (diagnosi budget_671): pagina di Rendiconto Finanziario mai una pagina SP; ---
# --- continuazione dello SP fra due pagine di prospetto sempre inclusa. -----------------------


def test_titolo_pagina_non_confonde_attivita_senza_apostrofo_in_un_rendiconto(tmp_path):
    # Forma reale di budget_671: "(Plusvalenze)/Minusvalenze derivanti dalla cessione di
    # attivita'" non e' preceduta da un apostrofo ("di attivita'", non "dell'attivita'"): il
    # lookbehind del fix 7 non la esclude, e la riga (6 parole) supera il controllo per riga.
    # La pagina apre comunque "Rendiconto finanziario" in testa: non deve mai diventare
    # "stato patrimoniale".
    path = pdf_xbrl_rendiconto_con_attivita_senza_preposizione(str(tmp_path / "rend3.pdf"))
    with fitz.open(path) as doc:
        assert _titolo_pagina(doc[2]) is None


def test_mappa_xbrl_non_scambia_il_rendiconto_per_stato_patrimoniale(tmp_path):
    # Stessa forma, verificata sull'intera mappa_xbrl (non solo _titolo_pagina): la pagina di
    # Rendiconto deve restare nota_o_testo, mai prospetto_sp.
    path = pdf_xbrl_rendiconto_con_attivita_senza_preposizione(str(tmp_path / "rend3.pdf"))
    mappe = mappa_xbrl(path)
    assert mappe[0]["tipo_pagina"] == "prospetto_sp"
    assert mappe[1]["tipo_pagina"] == "prospetto_ce"
    assert mappe[2]["tipo_pagina"] == "nota_o_testo"


def test_mappa_xbrl_continuazione_sp_oltre_il_limite_quando_stampa_totale_passivo(tmp_path):
    # Diagnosi budget_671: tre pagine di continuazione senza titolo proprio dopo l'Attivo - le
    # prime due generiche (dentro il tetto di 2), la terza (oltre il tetto) porta D) DEBITI e
    # "Totale passivo": il totale stampato dal documento decide, e questa pagina non puo'
    # restare fuori da pagine_sp (perderebbe l'intero blocco debiti, come nel file reale).
    path = pdf_xbrl_sp_continuazione_tre_pagine_con_totale_passivo(str(tmp_path / "sp3p.pdf"))
    mappe = mappa_xbrl(path)
    assert [m["tipo_pagina"] for m in mappe] == ["prospetto_sp"] * 4
    assert [m["continuazione"] for m in mappe] == [False, True, True, True]


def test_mappa_xbrl_limite_due_pagine_di_continuazione_resta_invariato(tmp_path):
    # Non regressione: senza "Totale passivo" (pura pagina di riempimento, come il test
    # esistente), il tetto di 2 pagine di continuazione resta quello di sempre - l'eccezione
    # e' solo per una pagina che chiude davvero lo SP col totale stampato.
    path = pdf_xbrl_sp_continuazione_oltre_il_limite(str(tmp_path / "lim.pdf"))
    mappe = mappa_xbrl(path)
    assert [m["tipo_pagina"] for m in mappe] == ["prospetto_sp", "prospetto_sp", "prospetto_sp", "nota_o_testo"]
    assert [m["continuazione"] for m in mappe] == [False, True, True, False]


# --- Task 22, G5, fix round 1 (review, punto 3): la stessa guardia (_apre_sezione_nuova) -----
# --- vale anche sul percorso vision (blocchi()/mappa_documento), non solo su mappa_xbrl. -----


def test_blocchi_non_fonde_un_rendiconto_nel_blocco_sp_precedente(tmp_path):
    # Prima del fix, il Rendiconto (senza preposizione davanti ad "attivita'") sarebbe stato
    # letto come "stato patrimoniale" da _titolo_pagina - lo STESSO titolo del blocco SP
    # immediatamente precedente - e blocchi() li avrebbe fusi in un solo blocco, riusando
    # l'immagine della pagina SP (una sola chiamata vision) anche per il Rendiconto.
    path = pdf_sp_poi_rendiconto_senza_ce(str(tmp_path / "sp_rend.pdf"))
    b = blocchi(path)
    assert [x.pagine for x in b] == [[1], [2]]
    assert b[0].titolo == "stato patrimoniale"
    assert b[1].titolo is None

    chiamate = []

    def finta(client, png):
        chiamate.append(png)
        return dict(MAPPA_COLONNA_UNICA)

    mappa_documento(path, mappa_pagina_fn=finta)
    assert len(chiamate) == 2                     # due blocchi separati, due chiamate


def test_apre_sezione_nuova_non_esclude_i_normali_tipi_di_pagina(tmp_path):
    # Nessun'altra forma gia' coperta dalla suite perde il proprio titolo per colpa della
    # guardia: colonna unica, sezioni contrapposte, CE semplice e CE a sezioni contrapposte
    # restano tutti riconosciuti come prima (non iniziano mai per "nota integrativa"/
    # "rendiconto finanziario"/"relazione"/"verbale").
    path_unica = pdf_colonna_unica(str(tmp_path / "u.pdf"))
    with fitz.open(path_unica) as doc:
        assert _titolo_pagina(doc[0]) == "stato patrimoniale"
    path_contrapposte = pdf_contrapposte(str(tmp_path / "c.pdf"))
    with fitz.open(path_contrapposte) as doc:
        assert _titolo_pagina(doc[0]) == "stato patrimoniale"
    path_ce = pdf_titolo_ce_semplice(str(tmp_path / "ce.pdf"), "CONTO ECONOMICO")
    with fitz.open(path_ce) as doc:
        assert _titolo_pagina(doc[0]) == "conto economico"
    path_ce2 = pdf_titolo_ce_contrapposte_stessa_riga(str(tmp_path / "ce2.pdf"))
    with fitz.open(path_ce2) as doc:
        assert _titolo_pagina(doc[0]) == "conto economico"
