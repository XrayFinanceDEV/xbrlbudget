from decimal import Decimal as D

import fitz
import pytest

from importers import import_snello as S
from importers.struttura_documento.analisi import Struttura


def _pdf_con_totali(path: str, totale_attivo: str, totale_passivo: str) -> str:
    """Un PDF che stampa 'Totale Attivo'/'Totale Passivo' come li leggerebbe
    _declared_control_totals (nessuna chiamata modello): serve solo a dare ai test
    un'ancora deterministica indipendente dalle righe/voci finte usate altrove."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), f"Totale Attivo {totale_attivo}")
    page.insert_text((50, 70), f"Totale Passivo {totale_passivo}")
    doc.save(path)
    return path


def _pdf_vuoto(path: str) -> str:
    """Una pagina senza testo: ogni test di questo file forza `analizza` (e spesso anche
    `righe_da_pdf`/`leggi_voci`/`leggi_conti`), quindi il contenuto reale del PDF non conta
    per la struttura - ma da Task 15 conta comunque per `totali_stampati()`, che legge il
    file vero indipendentemente da `analizza`. `pdf_colonna_unica` stampa per conto suo
    "STATO PATRIMONIALE ATTIVO/PASSIVO" con un importo sulla stessa riga (1.700,00): un
    dettaglio del fixture pensato per i test di struttura, che qui diventerebbe un'ancora
    deterministica indesiderata e in conflitto con gli importi finti usati in questo file."""
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    return path


def _struttura(modo, **kw):
    base = dict(fonte="vision", route=None, pagine_sp=[1], pagine_ce=[1], pagine_dettaglio=[],
                chiamate_vision=1, secondi=0.1, mappe=[], modo=modo,
                colonne_sp=["saldo_corrente", "saldo_precedente"], colonne_ce=["saldo_corrente", "saldo_precedente"],
                intestazioni_sp=["2025", "2024"], intestazioni_ce=["2025", "2024"], pagine_senza_testo=[])
    base.update(kw)
    return Struttura(**base)


def _voci_quadrate(testo, intestazioni, nota=""):
    if "rilettura" in nota:
        raise AssertionError("non serve rileggere")
    return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                         ("CE.A.1", D("500")), ("CE.B.7", D("400")), ("CE.21", D("100"))],
            "precedente": [], "totali": {"totale_attivo": D("1000"), "totale_passivo": D("1000"), "utile": D("100")}}


def test_legge_macro_include_dettaglio_aggiunge_pagine_dettaglio_al_prompt(tmp_path):
    """Task 18, ruling (c) addendum (owner, dopo la diagnosi AMBIENTA §7-8): quando
    struttura.macro_include_dettaglio e' vero, le pagine_dettaglio entrano ANCHE nel
    prompt macro di SP/CE, non solo nel recupero dettaglio a valle - un "riclassificato
    con codici IVCEE" che e' anche schema di legge coi totali stampati non e' un piano
    dei conti piatto: le sue macro-voci possono stare INTERAMENTE su una pagina che la
    vision ha classificato "dettaglio_conti" per il solo cambio pagina fisico (AMBIENTA:
    "9) per il personale" sta solo a pag.5, mai su una pagina di prospetto_ce)."""
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "7) per servizi 100,00")
    doc.new_page().insert_text((50, 50), "9) per il personale 900,00")
    pdf = str(tmp_path / "due-pagine.pdf")
    doc.save(pdf)
    doc.close()

    testo_visto = []

    def voci(testo, intestazioni, nota=""):
        testo_visto.append(testo)
        return {"corrente": [("CE.B.7", D("100"))], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[], pagine_ce=[1], pagine_dettaglio=[2],
                                     macro_include_dettaglio=True, intestazioni_ce=["CE-2025"])
    with pytest.raises(S.SnelloNonRiuscito):
        # Il fake "voci" non produce un attivo/passivo bilanciato (non e' cio' che
        # interessa qui): quel che conta e' il testo che ha visto, non l'esito finale.
        S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert any("personale" in t for t in testo_visto)


def test_legge_senza_macro_include_dettaglio_non_aggiunge_pagine_dettaglio(tmp_path):
    """Simmetrico: senza il segnale (il comportamento di ogni "legge" precedente a
    questo ruling - `_struttura` di default non lo imposta), le pagine_dettaglio restano
    fuori dal prompt macro."""
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "7) per servizi 100,00")
    doc.new_page().insert_text((50, 50), "9) per il personale 900,00")
    pdf = str(tmp_path / "due-pagine-no-flag.pdf")
    doc.save(pdf)
    doc.close()

    testo_visto = []

    def voci(testo, intestazioni, nota=""):
        testo_visto.append(testo)
        return {"corrente": [("CE.B.7", D("100"))], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[], pagine_ce=[1], pagine_dettaglio=[2],
                                     intestazioni_ce=["CE-2025"])
    with pytest.raises(S.SnelloNonRiuscito):
        S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert not any("personale" in t for t in testo_visto)


def test_legge_che_quadra(tmp_path):
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=_voci_quadrate)
    assert r.bs["sp09_disponibilita_liquide"] == D("1000.00") and r.ce["ce06_servizi"] == D("400.00")
    assert r.report["esito"] == "ok" and r.prior_bs is None
    assert r.bs["_plug_residual"] == 0


def test_legge_oltre_soglia_rilegge_una_volta_poi_squadrato(tmp_path):
    """Task 17 (decisione del proprietario, 2026-09-27): oltre soglia dopo l'unica rilettura
    non ripiega piu' sull'importatore attuale. Si salva il risultato snello con lo sbilancio
    dichiarato (esito 'squadrato'), senza alcun tappo: l'utente lo corregge in Rettifiche."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    chiamate = []
    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        return {"corrente": [("SPA.C.IV.1", D("5000")), ("SPP.A.I", D("900")), ("CE.A.1", D("500")), ("CE.B.7", D("400"))],
                "precedente": [], "totali": {}}
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert len(chiamate) == 3 and any("scarto" in n for n in chiamate)     # SP, CE, una rilettura
    assert r.report["esito"] == "squadrato"
    assert r.report["tappo"]["corrente"] is None
    assert r.report["misura"]["corrente"]["scarto_sp"] == "4100.00"
    assert r.bs["_plug_residual"] == D("0")
    # I dati restano quelli letti (nessun tappo applicato): l'attivo squadrato resta 5000.
    assert r.bs["sp09_disponibilita_liquide"] == D("5000.00")


def test_legge_squadrato_non_e_unrisultato_ok_ne_tappo(tmp_path):
    """Lo sbilancio dichiarato non deve confondersi con un tappo entro soglia: il campo
    'tappo' resta assente (None) e l'esito e' un terzo valore distinto."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    def voci(testo, intestazioni, nota=""):
        return {"corrente": [("SPA.C.IV.1", D("5000")), ("SPP.A.I", D("900")), ("CE.A.1", D("500")), ("CE.B.7", D("400"))],
                "precedente": [], "totali": {}}
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert r.report["esito"] not in ("ok", "tappo")
    assert r.report["esito"] == "squadrato"


def test_route_hint_si_inoltra_alla_struttura(tmp_path):
    # Task lotto-b, fix 9: route_hint arriva dal chiamante (pdf_importer.py, la route del
    # classificatore) fino ad analizza_struttura, che lo passa a modo_da_mappe. Il default None
    # non cambia la firma che i test esistenti usano (`analizza=lambda p: ...`).
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    visti = {}

    def analizza(p, *, route_hint=None):
        visti["route_hint"] = route_hint
        return _struttura("legge")

    r = S.importa(pdf, analizza=analizza, leggi_voci=_voci_quadrate, route_hint="TRIAL_BALANCE")
    assert visti["route_hint"] == "TRIAL_BALANCE"
    assert r.report["esito"] == "ok"


def test_route_hint_assente_non_rompe_una_analizza_senza_quel_parametro(tmp_path):
    # Senza route_hint (default None) la chiamata resta quella di sempre, posizionale sola:
    # una `analizza` finta che non accetta affatto quel parametro non deve rompersi.
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=_voci_quadrate)
    assert r.report["esito"] == "ok"


def test_struttura_in_errore_ripiega(tmp_path):
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    def rotta(p):
        raise RuntimeError("sonnet giu'")
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=rotta)
    assert exc.value.report["fase"] == "struttura" and exc.value.report["errore"] == "RuntimeError"


def test_pagina_condivisa_sp_e_ce_si_legge_una_sola_volta(tmp_path):
    """Task lotto-b, fix 8: una pagina "prospetto_sp_e_ce" (SP e CE sulla stessa pagina fisica)
    entra in pagine_sp E pagine_ce (TIPI_SP/TIPI_CE di analisi.py): leggerla due volte manda la
    stessa riga stampata a due chiamate indipendenti, che possono risolverla con due percorsi
    diversi (come budget_397: la stessa riga di debito letta 'SPP.D.O' dalla chiamata SP e
    'SPP.D.E' dalla chiamata CE) e la contano due volte, perche' da_coppie deduplica solo per
    percorso esatto. Una pagina cosi' si legge una volta sola."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    chiamate = []

    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        # stesso debito, percorso diverso alla seconda chiamata SE la pagina viene letta due volte
        percorso = "SPP.D.O" if len(chiamate) == 1 else "SPP.D.E"
        return {"corrente": [("SPA.C.IV.1", D("2100")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                             (percorso, D("1100")), ("CE.A.1", D("500")), ("CE.B.7", D("400")), ("CE.21", D("100"))],
                "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[1], pagine_ce=[1],
                                     mappe=[{"pagina": 1, "tipo_pagina": "prospetto_sp_e_ce"}])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert len(chiamate) == 1
    assert r.report["esito"] == "ok"       # con una lettura sola il debito conta una volta: attivo=passivo=2100


def test_pagina_condivisa_rilettura_dichiara_entrambe_le_sezioni(tmp_path):
    """Fix round 1, minor 4: sulla pagina condivisa la rilettura dopo uno scarto oltre soglia
    rilegge SP e CE insieme (`_leggi_sp_e_ce`), ma la diagnostica `letture` incrementava solo la
    sezione scelta dall'euristica (`sezione`), lasciando l'altra ferma a 1 anche se era stata
    riletta anch'essa. Ora entrambe le sezioni dichiarano la rilettura."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    chiamate = []

    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        debito = D("900") if len(chiamate) == 1 else D("1100")   # 1a chiamata: scarto; 2a: quadra
        return {"corrente": [("SPA.C.IV.1", D("2100")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                             ("SPP.D.E", debito), ("CE.A.1", D("500")), ("CE.B.7", D("400")),
                             ("CE.21", D("100"))],
                "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", pagine_sp=[1], pagine_ce=[1],
                                     mappe=[{"pagina": 1, "tipo_pagina": "prospetto_sp_e_ce"}])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert len(chiamate) == 2
    assert r.report["esito"] == "ok"
    assert r.report["letture"] == {"sp": 2, "ce": 2}


# --- Estensioni Task 8 (rulings del controllo) --------------------------------------------------


def test_legge_vuoto_rilegge_poi_ripiega(tmp_path):
    """esito 'vuoto' (attivo e passivo entrambi zero) si tratta come oltre_soglia: una sola
    rilettura, poi SnelloNonRiuscito con errore 'vuoto' dichiarato."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    chiamate = []
    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        return {"corrente": [], "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["esito"] == "ripiego" and exc.value.report["fase"] == "verifica"
    assert exc.value.report["errore"] == "vuoto"
    assert len(chiamate) == 3   # SP, CE, una rilettura


def test_legge_tappo_entro_soglia_plug_residual(tmp_path):
    """Uno scarto SP entro soglia si tampona (sp16g altri debiti): _plug_residual riporta
    esattamente l'importo del tappo e il report dichiara esito 'tappo'."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))

    def voci(testo, intestazioni, nota=""):
        if intestazioni and intestazioni[0].startswith("SP"):
            return {"corrente": [("SPA.B.II", D("1000")), ("SPA.C.IV", D("550")),
                                 ("SPP.A.I", D("800")), ("SPP.A.IX", D("100")), ("SPP.D.7", D("600"))],
                    "precedente": [], "totali": {}}
        return {"corrente": [("CE.A.1", D("400")), ("CE.B.7", D("300"))], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", intestazioni_sp=["SP-2025"], intestazioni_ce=["CE-2025"])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert r.report["esito"] == "tappo"
    assert r.report["tappo"]["corrente"]["campo"] == "sp16g_altri_debiti_breve"
    assert r.bs["_plug_residual"] == D("50.00")


def test_conti_legge_anche_le_pagine_dettaglio(tmp_path, monkeypatch):
    """Task 18, ruling (b): in modo 'conti' si leggono anche struttura.pagine_dettaglio, non
    solo pagine_sp ∪ pagine_ce - altrimenti una pagina di continuazione del prospetto (debiti/
    servizi che sconfinano oltre le pagine SP/CE gia' individuate, come AMBIENTA pag.3/5)
    resta invisibile e la sua massa e' persa (diagnosi AMBIENTA 2026-09-26, causa radice #1;
    modo 'legge' lo fa gia' da sempre via pagine_dettagli() per enrich_pdf_details)."""
    from importers.import_snello import righe as R

    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    catturato = {}

    def righe_da_pdf_spia(file_path, pagine, ruoli, ocr_text=None):
        catturato["pagine"] = pagine
        return []

    monkeypatch.setattr(R, "righe_da_pdf", righe_da_pdf_spia)

    def leggi_conti(righe, foglie):
        return {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}

    struttura = lambda p: _struttura("conti", pagine_sp=[1, 2], pagine_ce=[2], pagine_dettaglio=[3])
    with pytest.raises(S.SnelloNonRiuscito):
        # foglie vuote (righe_da_pdf finto non ne produce) -> attivo=passivo=0 -> esito
        # "vuoto": qui interessa solo l'insieme di pagine passato a righe_da_pdf, non l'esito.
        S.importa(pdf, analizza=struttura, leggi_conti=leggi_conti)

    assert catturato["pagine"] == {1, 2, 3}


def test_conti_percorso_finto_bilancio_quadra(tmp_path, monkeypatch):
    """Modo 'conti' con un `leggi_conti` finto che assegna i percorsi a righe fabbricate a mano
    (righe_da_pdf monkeypatchato): risultato in bilancio, `_unclassified_mass` sempre presente."""
    from importers.import_snello import righe as R

    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    righe_finte = [
        R.Riga(id="p1r1", pagina=1, lato="L", testo="IMPIANTI", valore=D("1000")),
        R.Riga(id="p1r2", pagina=1, lato="L", testo="BANCA C/C", valore=D("500")),
        R.Riga(id="p1r3", pagina=1, lato="R", testo="CAPITALE SOCIALE", valore=D("1000")),
        R.Riga(id="p1r4", pagina=1, lato="R", testo="FORNITORI ITALIA", valore=D("500")),
    ]
    monkeypatch.setattr(R, "righe_da_pdf", lambda *a, **k: righe_finte)

    def leggi_conti(righe, foglie):
        percorsi = {"p1r1": "SPA.B.II", "p1r2": "SPA.C.IV", "p1r3": "SPP.A.I", "p1r4": "SPP.D.7"}
        for f in foglie:
            f.percorso = percorsi[f.id]
        return {"chiamate": 1, "saltate_prima": 0, "senza_percorso": 0}

    r = S.importa(pdf, analizza=lambda p: _struttura("conti"), leggi_conti=leggi_conti)
    assert r.report["esito"] == "ok" and r.report["modo"] == "conti"
    assert r.bs["sp09_disponibilita_liquide"] == D("500.00")
    assert r.bs["_unclassified_mass"] == D("0")
    assert r.prior_bs is None


def test_eccezione_in_lettura_diventa_ripiego(tmp_path):
    """Un'eccezione del lettore (ContestoEccessivo, o qualunque altra) non esce cruda: diventa
    SnelloNonRiuscito con fase e classe dichiarate."""
    from importers.llm_provider import ContestoEccessivo

    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    def voci(testo, intestazioni, nota=""):
        raise ContestoEccessivo("troppo grande")
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["fase"] == "lettura"
    assert exc.value.report["errore"] == "ContestoEccessivo"


def test_conti_seconda_misura_non_sottrae_l_utile_due_volte(tmp_path, monkeypatch):
    """Riproduce budget_330: dopo normalizza_forma() il foglio e' gia' in forma bilancio (sp13
    = utile CE); la seconda misura() deve verificarlo con quella forma, non riautorilevare
    'verifica' e sottrarre l'utile una seconda volta. Con la doppia sottrazione (bug) un vero
    sbilancio di -250 (oltre soglia 100) viene mascherato in +50 (entro soglia) e la lettura
    esce come falso 'tappo'; corretto, esce come 'oltre_soglia' sul vero -250."""
    from importers.import_snello import righe as R

    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    righe_finte = [
        R.Riga(id="p1r1", pagina=1, lato="L", testo="BANCA C/C", valore=D("250")),
        R.Riga(id="p1r2", pagina=1, lato="R", testo="FORNITORI ITALIA", valore=D("800")),
        R.Riga(id="p1r3", pagina=1, lato="R", testo="RICAVI VENDITE", valore=D("100")),
        R.Riga(id="p1r4", pagina=1, lato="L", testo="COSTI SERVIZI", valore=D("400")),
    ]
    monkeypatch.setattr(R, "righe_da_pdf", lambda *a, **k: righe_finte)

    def leggi_conti(righe, foglie):
        percorsi = {"p1r1": "SPA.C.IV", "p1r2": "SPP.D.7", "p1r3": "CE.A.1", "p1r4": "CE.B.7"}
        for f in foglie:
            f.percorso = percorsi[f.id]
        return {"chiamate": 1, "saltate_prima": 0, "senza_percorso": 0}

    # Modo "conti" non rilegge (nessuna rilettura prevista in questo modo): l'esito
    # oltre soglia si vede direttamente, sul vero -250 (Task 17: si salva con lo
    # sbilancio dichiarato invece di ripiegare).
    r = S.importa(pdf, analizza=lambda p: _struttura("conti"), leggi_conti=leggi_conti)
    assert r.report["esito"] == "squadrato"
    assert r.report["misura"]["corrente"]["scarto_sp"] == "-250.00"
    assert r.report["tappo"]["corrente"] is None
    assert r.bs["_plug_residual"] == D("0")


def test_anomalie_immobilizzazioni_negative(tmp_path):
    """Un'immobilizzazione netta ancora negativa (sp02/sp03/sp04) si azzera - mai spostata su
    un altro campo, mai lasciata negativa - e l'eccedenza tagliata si dichiara in
    report['anomalie']: stessa regola del vecchio importatore
    (situazione_contabile_parser.build_sp_from_vision, ~L5177-5185)."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))

    def voci(testo, intestazioni, nota=""):
        if intestazioni and intestazioni[0].startswith("SP"):
            # dopo il clamp sp03 diventa 0: 0 + sp04(1000) = sp11(1000) + sp13(0), quadra da solo -
            # cosi' il test isola la sola dichiarazione dell'anomalia, senza il tappo che
            # scatterebbe se il clamp lasciasse un vero scarto residuo.
            return {"corrente": [("SPA.B.II", D("-80")), ("SPA.C.IV", D("1000")),
                                 ("SPP.A.I", D("1000")), ("SPP.A.IX", D("0"))],
                    "precedente": [], "totali": {}}
        return {"corrente": [], "precedente": [], "totali": {}}

    struttura = lambda p: _struttura("legge", intestazioni_sp=["SP-2025"], intestazioni_ce=["CE-2025"])
    r = S.importa(pdf, analizza=struttura, leggi_voci=voci)
    assert r.report["esito"] == "ok"
    assert r.report["anomalie"] == [["sp03_immob_materiali", "80.00"]]
    assert r.bs["sp03_immob_materiali"] == D("0.00")


# --- Task 15 (2026-09-27): i totali stampati dal documento come ancora indipendente ----------


def test_conti_totali_stampati_deterministici_come_ancora(tmp_path, monkeypatch):
    """In modo 'conti' oggi stampati=None sempre: un documento che stampa un Totale Attivo
    ben diverso dalla somma classificata (500 contro 5.000,00 dichiarati) deve uscire oltre
    soglia, anche se lo SP interno pareggia da solo (attivo=passivo=500) - senza l'ancora
    deterministica quella sotto-estrazione passerebbe per un bilancio pulito."""
    from importers.import_snello import righe as R

    pdf = _pdf_con_totali(str(tmp_path / "c.pdf"), "5.000,00", "5.000,00")
    righe_finte = [
        R.Riga(id="p1r1", pagina=1, lato="L", testo="BANCA C/C", valore=D("500")),
        R.Riga(id="p1r2", pagina=1, lato="R", testo="CAPITALE SOCIALE", valore=D("500")),
    ]
    monkeypatch.setattr(R, "righe_da_pdf", lambda *a, **k: righe_finte)

    def leggi_conti(righe, foglie):
        percorsi = {"p1r1": "SPA.C.IV", "p1r2": "SPP.A.I"}
        for f in foglie:
            f.percorso = percorsi[f.id]
        return {"chiamate": 1, "saltate_prima": 0, "senza_percorso": 0}

    # Task 17: oltre soglia si salva con lo sbilancio dichiarato (esito "squadrato").
    r = S.importa(pdf, analizza=lambda p: _struttura("conti"), leggi_conti=leggi_conti)
    assert r.report["esito"] == "squadrato"
    assert D(r.report["misura"]["corrente"]["scarto_stampati"]) > 0


def test_conti_senza_totali_stampati_si_comporta_come_prima(tmp_path, monkeypatch):
    """Un documento che non stampa alcun totale (pagina vuota) non cambia comportamento:
    _declared_control_totals torna None su entrambe le chiavi, come lo stampati=None di
    prima."""
    from importers.import_snello import righe as R

    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))
    righe_finte = [
        R.Riga(id="p1r1", pagina=1, lato="L", testo="IMPIANTI", valore=D("1000")),
        R.Riga(id="p1r2", pagina=1, lato="R", testo="CAPITALE SOCIALE", valore=D("1000")),
    ]
    monkeypatch.setattr(R, "righe_da_pdf", lambda *a, **k: righe_finte)

    def leggi_conti(righe, foglie):
        percorsi = {"p1r1": "SPA.B.II", "p1r2": "SPP.A.I"}
        for f in foglie:
            f.percorso = percorsi[f.id]
        return {"chiamate": 1, "saltate_prima": 0, "senza_percorso": 0}

    r = S.importa(pdf, analizza=lambda p: _struttura("conti"), leggi_conti=leggi_conti)
    assert r.report["esito"] == "ok"


def test_legge_preferisce_i_totali_stampati_deterministici_ai_llm(tmp_path):
    """Il PDF stampa Totale Attivo/Passivo 5.000,00 (letti deterministicamente); l'LLM
    dichiara invece, nello stesso campo 'totali', 1.000,00/1.000,00 - gli stessi importi
    delle voci che ha letto: un contraddittorio apparente che, preso per buono,
    nasconderebbe la vera sotto-estrazione. I totali deterministici vincono su quelli
    riportati dall'LLM: lo scarto reale (4.000,00) emerge, oltre soglia."""
    pdf = _pdf_con_totali(str(tmp_path / "c.pdf"), "5.000,00", "5.000,00")

    def voci(testo, intestazioni, nota=""):
        return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("1000"))],
                "precedente": [], "totali": {"totale_attivo": D("1000"), "totale_passivo": D("1000")}}

    # Task 17: oltre soglia si salva con lo sbilancio dichiarato (esito "squadrato").
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert r.report["esito"] == "squadrato"
    assert D(r.report["misura"]["corrente"]["scarto_stampati"]) > 0


def test_rilettura_per_soli_totali_stampati_dichiara_la_causa(tmp_path):
    """Round 1 (review, 2026-09-27): quando lo scarto interno (SP e CE) e' entro soglia ma il
    totale stampato dal documento non concorda con le voci lette, la nota della rilettura deve
    parlare del totale stampato (non 'voci mancanti, doppie...', un messaggio pensato per un
    vero sbilancio interno) e il report finale deve dichiarare causa='stampati'."""
    pdf = _pdf_con_totali(str(tmp_path / "c.pdf"), "5.000,00", "5.000,00")
    note_viste = []

    def voci(testo, intestazioni, nota=""):
        note_viste.append(nota)
        return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("1000"))],
                "precedente": [], "totali": {}}

    # Task 17: oltre soglia si salva con avviso (esito "squadrato"), la causa resta dichiarata.
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert r.report["esito"] == "squadrato"
    assert r.report["causa"] == "stampati"
    rilettura = [n for n in note_viste if n]
    assert len(rilettura) == 1   # solo SP: scarto_stampati>soglia sceglie sempre quella sezione
    assert "stampat" in rilettura[0].lower()
    assert "voci mancanti" not in rilettura[0].lower()


def test_legge_usa_i_totali_llm_quando_il_documento_non_ne_stampa(tmp_path):
    """Senza un totale stampato deterministico (pagina vuota), i totali riportati
    dall'LLM restano l'unica ancora, come prima di questo task."""
    pdf = _pdf_vuoto(str(tmp_path / "c.pdf"))

    def voci(testo, intestazioni, nota=""):
        return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("1000"))],
                "precedente": [], "totali": {"totale_attivo": D("1000"), "totale_passivo": D("1000")}}

    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert r.report["esito"] == "ok"
