from decimal import Decimal as D

from importers import llm_provider
from importers.import_snello import lettura as L
from importers.import_snello.righe import Riga


def _riga(i, testo, valore="10", totale=False, lato="L"):
    return Riga(id=f"p1r{i}", pagina=1, lato=lato, testo=testo, valore=None if valore is None else D(valore), totale=totale)


def test_percorsi_numerati_e_seconda_chiamata_sulle_saltate():
    righe = [_riga(0, "ATTIVITA'", None)] + [_riga(i, f"conto {i}") for i in range(1, 4)]
    foglie = righe[1:]
    chiamate = []
    def chiama(system, user, max_tokens):
        chiamate.append(user)
        if len(chiamate) == 1:
            assert "# ATTIVITA'" in user and "LEGENDA" in system
            return "1 SPA.B.II.2\n3 SPP.D.7\nrumore"
        assert "2|conto 2" in user and "1|conto 1" not in user
        return "2 CE.B.7"
    esito = L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert [f.percorso for f in foglie] == ["SPA.B.II.2", "CE.B.7", "SPP.D.7"]
    assert esito == {"chiamate": 2, "saltate_prima": 1, "senza_percorso": 0}


def test_percorsi_a_blocchi_con_max_tokens_proporzionato():
    righe = [_riga(i, f"c{i}") for i in range(1, 131)]
    visti = []
    def chiama(system, user, max_tokens):
        visti.append(max_tokens)
        return "\n".join(f"{l.split('|')[0]} X" for l in user.splitlines() if "|" in l)
    L.percorsi_dei_conti(righe, righe, chiama=chiama)
    assert len(visti) == 3 and max(visti) <= 40 + 14 * L.BLOCCO


def test_voci_di_legge_converte_importi():
    def chiama_json(system, user, schema, max_tokens):
        assert "2025" in user and "LEGENDA" in system
        return {"corrente": [["SPA.B.I.1", 118720.39]], "precedente": [["SPA.B.I.1", 125571]],
                "totali": {"totale_attivo": 2161054, "totale_passivo": None, "utile": 7422}}
    out = L.voci_di_legge("riga|Costi di impianto|118.720,39", ["31-12-2025", "31-12-2024"], chiama_json=chiama_json)
    assert out["corrente"] == [("SPA.B.I.1", D("118720.39"))]
    assert out["precedente"] == [("SPA.B.I.1", D("125571"))]
    assert out["totali"]["totale_attivo"] == D("2161054")


def test_indice_fuori_blocco_ignorato():
    """Il modello puo' allucinare un id che non fa parte del blocco corrente (per esempio
    l'id di una riga di un blocco diverso, o di una riga vista solo come contesto '#'):
    quella riga non deve ricevere un percorso."""
    r_a = _riga(1, "conto a")
    r_b = _riga(2, "conto b")
    righe = [r_a, r_b]
    foglie = [r_a]  # solo r_a e' nel giro corrente

    def chiama(system, user, max_tokens):
        assert "1|conto b" not in user  # r_b non e' nel testo del blocco
        return "0 SPA.A\n1 SPP.B"  # il modello risponde anche per l'indice 1 (r_b), fuori blocco

    L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert r_a.percorso == "SPA.A"
    assert r_b.percorso is None


def test_identita_non_uguaglianza_di_campi_evita_falsi_positivi():
    """Riga e' un dataclass: due oggetti distinti con campi identici (compreso l'id)
    comparano uguali con `==`. Il controllo di appartenenza al giro deve essere per
    identita' dell'oggetto, non per uguaglianza di campi, altrimenti un indice allucinato
    che punta a un oggetto "gemello" ma estraneo al giro riceverebbe comunque un percorso."""
    r0 = Riga(id="dup", pagina=1, lato="L", testo="conto duplicato", valore=D("10"), totale=False)
    r1 = Riga(id="dup", pagina=1, lato="L", testo="conto duplicato", valore=D("10"), totale=False)
    assert r0 == r1 and r0 is not r1

    righe = [r0, r1]
    foglie = [r1]  # solo r1 e' nel giro; r0 e' un oggetto distinto, non nel giro

    chiamate = []
    def chiama(system, user, max_tokens):
        chiamate.append(user)
        # il modello risponde con l'indice 0 (r0), che non fa parte del blocco inviato
        return "0 SPA.A"

    esito = L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert r0.percorso is None
    assert r1.percorso is None  # il modello non ha mai risposto per l'indice 1
    assert esito["senza_percorso"] == 1
    assert len(chiamate) == 2  # un giro, poi il ripasso sulle saltate


def test_trascrivi_pagine_transcribe_righe_dedup_bordo(tmp_path, monkeypatch):
    import fitz

    # Concorrenza a 1: le tre strisce di una stessa pagina vanno elaborate in ordine,
    # cosi' la sequenza restituita e' deterministica e il test puo' verificare il dedup
    # della riga di bordo che le strisce si sovrappongono a vicenda.
    monkeypatch.setattr(llm_provider, "GX10_CONCORRENZA", 1)

    pdf_path = tmp_path / "pagina.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.save(str(pdf_path))
    doc.close()

    risposte = [
        {"righe": [["riga 1", 1, 1], ["bordo", 9, 9]]},
        {"righe": [["bordo", 9, 9], ["riga 2", 2, 2]]},
        {"righe": [["riga 3", 3, 3]]},
    ]
    chiamate = []

    def chiama_json(system, contenuto, schema, max_tokens):
        chiamate.append(contenuto)
        assert contenuto[1]["type"] == "image_url"
        return risposte[len(chiamate) - 1]

    out = L.trascrivi_pagine(str(pdf_path), [1], chiama_json=chiama_json, strisce=3, dpi=50)
    assert out.splitlines() == ["riga 1 | 1 | 1", "bordo | 9 | 9", "riga 2 | 2 | 2", "riga 3 | 3 | 3"]
    assert len(chiamate) == 3


# --- Fix round 1 --------------------------------------------------------------------------


def test_indice_di_un_altro_blocco_dello_stesso_giro_non_assegnato():
    """Un id allucinato nella risposta del blocco 1 che appartiene al blocco 2 (stesso giro,
    quindi presente in `da_fare`) non deve ricevere un percorso: solo la risposta del blocco
    che possiede davvero quella riga puo' assegnargliela. Qui il blocco 2 non risponde affatto
    per la propria riga 65 (nemmeno al ripasso sulle saltate), quindi resta senza percorso."""
    righe = [_riga(i, f"c{i}") for i in range(70)]
    foglie = righe  # BLOCCO=60 -> blocco 1: righe 0..59, blocco 2: righe 60..69

    def chiama(system, user, max_tokens):
        if "0|c0" in user:  # blocco 1
            risposte = [f"{i} X" for i in range(60)]
            risposte.append("65 X")  # allucina un indice del blocco 2
            return "\n".join(risposte)
        # blocco 2 (primo giro e ripasso): risponde per le proprie righe tranne la 65
        return "\n".join(f"{i} X" for i in range(60, 70) if i != 65)

    esito = L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert righe[65].percorso is None
    assert esito["senza_percorso"] == 1


def test_blocco_non_sovrascrive_una_riga_assegnata_da_un_altro_blocco():
    """Il blocco 1 risponde correttamente per la riga 5 (di sua proprieta'); il blocco 2
    allucina anche lui un percorso per la riga 5 (che non gli appartiene): la riga 5 deve
    tenere il percorso del blocco 1, mai quello, sbagliato, del blocco 2."""
    righe = [_riga(i, f"c{i}") for i in range(70)]
    foglie = righe

    def chiama(system, user, max_tokens):
        if "0|c0" in user:  # blocco 1: risposta corretta, riga 5 compresa
            return "\n".join(f"{i} corretto" for i in range(60))
        # blocco 2: risponde per le proprie righe, e allucina anche l'indice 5 (blocco 1)
        risposte = [f"{i} sbagliato" for i in range(60, 70)]
        risposte.append("5 sbagliato")
        return "\n".join(risposte)

    L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert righe[5].percorso == "corretto"


def test_trascrivi_pagine_non_deduplica_dentro_la_stessa_striscia(tmp_path, monkeypatch):
    import fitz

    monkeypatch.setattr(llm_provider, "GX10_CONCORRENZA", 1)
    pdf_path = tmp_path / "una_pagina.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.save(str(pdf_path))
    doc.close()

    risposte = [
        {"righe": [["dup", 5, 5], ["dup", 5, 5]]},  # striscia 0: due righe identiche adiacenti
        {"righe": [["altra", 3, 3]]},               # striscia 1
    ]
    chiamate = []
    def chiama_json(system, contenuto, schema, max_tokens):
        chiamate.append(1)
        return risposte[len(chiamate) - 1]

    out = L.trascrivi_pagine(str(pdf_path), [1], chiama_json=chiama_json, strisce=2, dpi=50)
    assert out.splitlines() == ["dup | 5 | 5", "dup | 5 | 5", "altra | 3 | 3"]


def test_trascrivi_pagine_non_confronta_oltre_la_pagina(tmp_path, monkeypatch):
    import fitz

    monkeypatch.setattr(llm_provider, "GX10_CONCORRENZA", 1)
    pdf_path = tmp_path / "due_pagine.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.new_page(width=200, height=300)
    doc.save(str(pdf_path))
    doc.close()

    risposte = [
        {"righe": [["riga 1", 1, 1], ["X", 9, 9]]},   # pagina 1, unica striscia
        {"righe": [["X", 9, 9], ["riga 2", 2, 2]]},   # pagina 2, unica striscia
    ]
    chiamate = []
    def chiama_json(system, contenuto, schema, max_tokens):
        chiamate.append(1)
        return risposte[len(chiamate) - 1]

    out = L.trascrivi_pagine(str(pdf_path), [1, 2], chiama_json=chiama_json, strisce=1, dpi=50)
    assert out.splitlines() == ["riga 1 | 1 | 1", "X | 9 | 9", "X | 9 | 9", "riga 2 | 2 | 2"]
