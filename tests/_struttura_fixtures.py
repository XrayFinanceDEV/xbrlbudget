"""PDF sintetici con text layer, nelle tre famiglie della spec. Niente dati reali."""
import fitz

FONT = "helv"


def _riga(page, y, colonne):
    """colonne: [(x, testo, allinea_destra)] — i numeri sono allineati a destra sull'ancora."""
    for x, testo, destra in colonne:
        if not testo:
            continue
        if destra:
            larghezza = fitz.get_text_length(testo, fontname=FONT, fontsize=8)
            page.insert_text((x - larghezza, y), testo, fontname=FONT, fontsize=8)
        else:
            page.insert_text((x, y), testo, fontname=FONT, fontsize=8)


def pdf_contrapposte(path: str) -> str:
    """Una pagina, ATTIVITA' a sinistra e PASSIVITA' a destra, piano dei conti a 3 livelli,
    colonne 'Saldo non rettificato | Rettifiche | Saldo finale' per lato."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((300, 40), "STATO PATRIMONIALE", fontname=FONT, fontsize=10)
    page.insert_text((30, 60), "ATTIVITA'", fontname=FONT, fontsize=9)
    page.insert_text((450, 60), "PASSIVITA'", fontname=FONT, fontsize=9)
    for x0 in (30, 450):
        page.insert_text((x0, 80), "Conto", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 60, 80), "Descrizione", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 230, 76), "Saldo non", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 230, 86), "rettificato", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 290, 80), "Rettifiche", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 345, 80), "Saldo finale", fontname=FONT, fontsize=8)
    sinistra = [("05", "IMMOBILIZZAZIONI MATERIALI", "1.500,00", "", "1.500,00"),
                ("05.01", "IMPIANTI", "1.000,00", "", "1.000,00"),
                ("05.01.01", "Impianti generici", "1.000,00", "", "1.000,00"),
                ("05.03", "ATTREZZATURE", "500,00", "", "500,00"),
                ("05.03.01", "Attrezzatura varia", "500,00", "", "500,00"),
                ("11", "CREDITI COMMERCIALI", "800,00", "", "800,00"),
                ("11.01", "Clienti Italia", "800,00", "", "800,00"),
                ("19", "DISPONIBILITA' LIQUIDE", "200,00", "50,00", "250,00"),
                ("19.01", "Banca c/c", "200,00", "50,00", "250,00")]
    destra = [("23", "CAPITALE E RISERVE", "1.000,00", "", "1.000,00"),
              ("23.01", "Capitale sociale", "1.000,00", "", "1.000,00"),
              ("33", "DEBITI COMMERCIALI", "900,00", "", "900,00"),
              ("33.01", "Fornitori Italia", "900,00", "", "900,00"),
              ("41", "FONDI AMMORTAMENTO", "400,00", "", "400,00"),
              ("41.01", "F.do amm. impianti", "400,00", "", "400,00"),
              ("", "Utile del periodo", "250,00", "", "250,00"),
              ("", "Totale a pareggio", "2.550,00", "", "2.550,00")]
    for x0, righe in ((30, sinistra), (450, destra)):
        y = 100
        for codice, testo, a, b, c in righe:
            _riga(page, y, [(x0, codice, False), (x0 + 60, testo, False),
                            (x0 + 280, a, True), (x0 + 335, b, True), (x0 + 395, c, True)])
            y += 12
    doc.save(path)
    return path


def pdf_colonna_unica(path: str) -> str:
    """Due pagine, riclassificato in colonna unica con codici IV CEE + conto, colonne
    'Importo corrente | Importo comparato', fondi come righe negative nell'attivo.
    La seconda pagina continua la prima senza ristampare il titolo di sezione."""
    doc = fitz.open()
    intestazioni = [(400, "Importo corrente", True), (500, "Importo comparato", True)]
    righe_p1 = [(20, "", "STATO PATRIMONIALE ATTIVO", "1.700,00", "1.600,00"),
                (26, "", "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "", "II. Immobilizzazioni Materiali", "900,00", "950,00"),
                (34, "", "2) Impianti e macchinario", "900,00", "950,00"),
                (38, "", "Costo storico", "1.000,00", "1.000,00"),
                (44, "BII2 104.00011", "IMPIANTI GENERICI", "1.000,00", "1.000,00"),
                (38, "", "Fondo ammortamento", "-100,00", "-50,00"),
                (44, "BII2A 114.00011", "F.AMM. IMPIANTI GENERICI", "-100,00", "-50,00"),
                (26, "", "C) Attivo circolante", "800,00", "650,00"),
                (30, "", "II. Crediti", "800,00", "650,00"),
                (34, "", "1) verso clienti", "800,00", "650,00"),
                (38, "", "- entro esercizio successivo", "800,00", "650,00")]
    righe_p2 = [(44, "CII1A 208.00001", "CLIENTI ITALIA", "800,00", "650,00"),
                (20, "", "STATO PATRIMONIALE PASSIVO", "1.700,00", "1.600,00"),
                (26, "", "A) Patrimonio netto", "1.000,00", "1.000,00"),
                (30, "", "I) Capitale", "1.000,00", "1.000,00"),
                (44, "AI 301.00001", "CAPITALE SOCIALE", "1.000,00", "1.000,00"),
                (26, "", "D) Debiti", "700,00", "600,00"),
                (30, "", "7) Debiti verso fornitori", "700,00", "600,00"),
                (44, "D7 401.00001", "FORNITORI ITALIA", "700,00", "600,00")]
    for righe in (righe_p1, righe_p2):
        page = doc.new_page(width=595, height=842)
        page.insert_text((20, 30), "BILANCIO RICLASSIFICATO UE", fontname=FONT, fontsize=9)
        _riga(page, 50, [(20, "Descrizione", False)] + intestazioni)
        y = 70
        for x, codice, testo, a, b in righe:
            _riga(page, y, [(x, (codice + " " + testo).strip(), False), (400, a, True), (500, b, True)])
            y += 12
        page.insert_text((20, 820), "Continua..", fontname=FONT, fontsize=7)
    doc.save(path)
    return path


def pdf_xbrl_legge(path: str) -> str:
    """Tre pagine: SP e CE nello schema civilistico con due date, più una pagina di nota
    con prosa e nessun importo. Piè di pagina della tassonomia."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]
    sp = [(30, "Stato patrimoniale", "", ""), (34, "Attivo", "", ""),
          (38, "B) Immobilizzazioni", "", ""),
          (42, "I - Immobilizzazioni immateriali", "100", "90"),
          (42, "II - Immobilizzazioni materiali", "900", "950"),
          (42, "Totale immobilizzazioni (B)", "1.000", "1.040"),
          (38, "C) Attivo circolante", "", ""),
          (42, "II - Crediti", "", ""),
          (46, "esigibili entro l'esercizio successivo", "600", "500"),
          (46, "esigibili oltre l'esercizio successivo", "100", "80"),
          (46, "Totale crediti", "700", "580"),
          (42, "IV - Disponibilita' liquide", "300", "200"),
          (42, "Totale attivo circolante (C)", "1.000", "780"),
          (38, "Totale attivo", "2.000", "1.820"),
          (34, "Passivo", "", ""),
          (38, "A) Patrimonio netto", "", ""),
          (42, "I - Capitale", "1.000", "1.000"),
          (42, "IX - Utile (perdita) dell'esercizio", "200", "(20)"),
          (42, "Totale patrimonio netto", "1.200", "980"),
          (38, "D) Debiti", "", ""),
          (42, "esigibili entro l'esercizio successivo", "800", "840"),
          (42, "Totale debiti", "800", "840"),
          (38, "Totale passivo", "2.000", "1.820")]
    ce = [(30, "Conto economico", "", ""), (34, "A) Valore della produzione", "", ""),
          (38, "1) ricavi delle vendite e delle prestazioni", "3.000", "2.500"),
          (38, "Totale valore della produzione", "3.000", "2.500"),
          (34, "B) Costi della produzione", "", ""),
          (38, "7) per servizi", "2.000", "1.900"),
          (38, "9) per il personale", "", ""),
          (42, "a) salari e stipendi", "500", "450"),
          (42, "Totale costi per il personale", "500", "450"),
          (38, "Totale costi della produzione", "2.500", "2.350"),
          (34, "Differenza tra valore e costi della produzione (A - B)", "500", "150"),
          (34, "20) Imposte sul reddito dell'esercizio", "300", "170"),
          (34, "21) Utile (perdita) dell'esercizio", "200", "(20)")]
    for righe in (sp, ce):
        page = doc.new_page(width=595, height=842)
        _riga(page, 50, intest)
        y = 70
        for x, testo, a, b in righe:
            _riga(page, y, [(x, testo, False), (380, a, True), (480, b, True)])
            y += 12
        page.insert_text((20, 820), "Bilancio di esercizio al 31-12-2025  Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04",
                         fontname=FONT, fontsize=6)
    nota = doc.new_page(width=595, height=842)
    nota.insert_text((30, 60), "Nota integrativa", fontname=FONT, fontsize=10)
    for i in range(20):
        nota.insert_text((30, 90 + i * 14), "I criteri di valutazione adottati sono conformi alle disposizioni del codice civile.",
                         fontname=FONT, fontsize=8)
    doc.save(path)
    return path


def pdf_titoli_spaziati(path: str) -> str:
    """Un gestionale a sezioni contrapposte che stampa i titoli lettera per lettera:
    'S I T U A Z I O N E' / 'P A T R I M O N I A L E' sulle pagine SP (lati anch'essi spaziati
    'A T T I V I T A' / 'P A S S I V I T A'), 'S I T U A Z I O N E' / 'E C O N O M I C A' sulle
    pagine CE (lati normali 'COSTI, SPESE E PERDITE' / 'RICAVI E PROFITTI'). Le intestazioni di
    colonna sono identiche sulle quattro pagine; un conto di CE contiene la parola "ATTIVITA'"
    nella descrizione (capita in un piano dei conti reale), a riprova che non decide piu' il
    titolo della pagina (difetto A, Task 7b)."""
    doc = fitz.open()
    intestazione = "CONTO CONTO DESCRIZIONE CONTO DESCRIZIONE CONTO SALDO SALDO"

    def _pagina(titolo1, titolo2, lato1, lato2, conti):
        page = doc.new_page(width=595, height=842)
        page.insert_text((30, 30), titolo1, fontname=FONT, fontsize=10)
        page.insert_text((30, 44), titolo2, fontname=FONT, fontsize=10)
        page.insert_text((30, 58), lato1, fontname=FONT, fontsize=9)
        page.insert_text((30, 72), lato2, fontname=FONT, fontsize=9)
        page.insert_text((30, 88), intestazione, fontname=FONT, fontsize=8)
        y = 108
        for codice, testo, saldo in conti:
            _riga(page, y, [(30, codice, False), (90, testo, False), (400, saldo, True)])
            y += 14

    sp_conti = [("05", "IMMOBILIZZAZIONI MATERIALI", "1.500,00"),
                ("11", "CREDITI COMMERCIALI", "800,00"),
                ("19", "DISPONIBILITA' LIQUIDE", "250,00"),
                ("23", "CAPITALE E RISERVE", "1.000,00"),
                ("33", "DEBITI COMMERCIALI", "900,00"),
                ("41", "FONDI AMMORTAMENTO", "400,00")]
    ce_conti = [("61", "MATERIE PRIME", "1.200,00"),
                ("62", "SERVIZI", "600,00"),
                ("80", "RIMBORSO ATTIVITA' FINANZIARIE", "100,00"),
                ("71", "RICAVI DI VENDITA", "3.000,00"),
                ("72", "ALTRI RICAVI", "150,00"),
                ("73", "PROVENTI DIVERSI", "50,00")]
    for _ in range(2):
        _pagina("S I T U A Z I O N E", "P A T R I M O N I A L E", "A T T I V I T A", "P A S S I V I T A", sp_conti)
    for _ in range(2):
        _pagina("S I T U A Z I O N E", "E C O N O M I C A", "COSTI, SPESE E PERDITE", "RICAVI E PROFITTI", ce_conti)
    doc.save(path)
    return path


def pdf_xbrl_con_nota(path: str) -> str:
    """Cinque pagine come un vero xbrl di legge, con la nota integrativa che difetto B scambiava
    per un secondo prospetto: copertina, SP (titolo in prima riga + date), CE (titolo in prima
    riga + date), testa di nota integrativa + prosa, e una tabella di nota che ripete «conto
    economico» nel testo, le stesse date e >= 5 importi. NON estende `pdf_xbrl_legge`: altri test
    dipendono dalla sua forma a tre pagine."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    copertina = doc.new_page(width=595, height=842)
    copertina.insert_text((30, 60), "Ragione sociale S.r.l.", fontname=FONT, fontsize=11)
    copertina.insert_text((30, 80), "Bilancio d'esercizio al 31-12-2025", fontname=FONT, fontsize=10)

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    sp_righe = [(30, "B) Immobilizzazioni", "", ""),
                (34, "Totale immobilizzazioni (B)", "900,00", "950,00"),
                (30, "C) Attivo circolante", "", ""),
                (34, "Totale attivo circolante (C)", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00"),
                (30, "A) Patrimonio netto", "", ""),
                (34, "Totale patrimonio netto", "700,00", "650,00"),
                (30, "D) Debiti", "", ""),
                (34, "Totale debiti", "500,00", "500,00"),
                (30, "Totale passivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in sp_righe:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 40), "Conto economico", fontname=FONT, fontsize=10)
    _riga(ce, 60, intest)
    ce_righe = [(30, "A) Valore della produzione", "", ""),
                (34, "Totale valore della produzione", "2.000,00", "1.800,00"),
                (30, "B) Costi della produzione", "", ""),
                (34, "Totale costi della produzione", "1.200,00", "1.100,00"),
                (30, "Differenza tra valore e costi della produzione (A - B)", "800,00", "700,00"),
                (30, "21) Utile (perdita) dell'esercizio", "500,00", "450,00")]
    y = 80
    for x, testo, a, b in ce_righe:
        _riga(ce, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    nota = doc.new_page(width=595, height=842)
    nota.insert_text((30, 40), "Nota integrativa", fontname=FONT, fontsize=10)
    for i in range(15):
        nota.insert_text((30, 70 + i * 14), "I criteri di valutazione sono conformi al codice civile.",
                          fontname=FONT, fontsize=8)

    tabella_nota = doc.new_page(width=595, height=842)
    tabella_nota.insert_text((30, 40), "Dettaglio della voce B.10 del conto economico", fontname=FONT, fontsize=9)
    _riga(tabella_nota, 60, intest)
    dettaglio = [(30, "Ammortamento immobilizzazioni immateriali", "100,00", "90,00"),
                 (30, "Ammortamento immobilizzazioni materiali", "150,00", "140,00"),
                 (30, "Svalutazione crediti", "50,00", "40,00"),
                 (30, "Altre svalutazioni", "30,00", "20,00"),
                 (30, "Totale", "330,00", "290,00")]
    y = 80
    for x, testo, a, b in dettaglio:
        _riga(tabella_nota, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    doc.save(path)
    return path


def pdf_xbrl_con_tabelle_nota(path: str) -> str:
    """Cinque pagine come un vero xbrl di legge, ma con una VERA tabella di nota integrativa
    (titolo fisso della tassonomia OIC, «Analisi delle variazioni e della scadenza dei debiti»):
    pagina 1 SP, pagina 2 CE (con lo stesso pie' di pagina e le stesse due date di
    `pdf_xbrl_legge`), pagina 3 «Nota integrativa» di sola prosa, pagina 4 la tabella di nota
    (>= 6 importi), pagina 5 di sola prosa (senza importi, cosi' non si aggiunge alla tabella)."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    sp_righe = [(30, "B) Immobilizzazioni", "", ""),
                (34, "Totale immobilizzazioni (B)", "900,00", "950,00"),
                (30, "C) Attivo circolante", "", ""),
                (34, "Totale attivo circolante (C)", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00"),
                (30, "A) Patrimonio netto", "", ""),
                (34, "Totale patrimonio netto", "700,00", "650,00"),
                (30, "D) Debiti", "", ""),
                (34, "Totale debiti", "500,00", "500,00"),
                (30, "Totale passivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in sp_righe:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14
    sp.insert_text((20, 820), "Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04",
                   fontname=FONT, fontsize=6)

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 40), "Conto economico", fontname=FONT, fontsize=10)
    _riga(ce, 60, intest)
    ce_righe = [(30, "A) Valore della produzione", "", ""),
                (34, "Totale valore della produzione", "2.000,00", "1.800,00"),
                (30, "B) Costi della produzione", "", ""),
                (34, "Totale costi della produzione", "1.200,00", "1.100,00"),
                (30, "Differenza tra valore e costi della produzione (A - B)", "800,00", "700,00"),
                (30, "21) Utile (perdita) dell'esercizio", "500,00", "450,00")]
    y = 80
    for x, testo, a, b in ce_righe:
        _riga(ce, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14
    ce.insert_text((20, 820), "Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04",
                   fontname=FONT, fontsize=6)

    nota = doc.new_page(width=595, height=842)
    nota.insert_text((30, 40), "Nota integrativa", fontname=FONT, fontsize=10)
    for i in range(15):
        nota.insert_text((30, 70 + i * 14), "I criteri di valutazione sono conformi al codice civile.",
                          fontname=FONT, fontsize=8)

    tabella_nota = doc.new_page(width=595, height=842)
    tabella_nota.insert_text((30, 40), "Analisi delle variazioni e della scadenza dei debiti", fontname=FONT, fontsize=9)
    _riga(tabella_nota, 60, intest)
    dettaglio = [(30, "Debiti verso banche entro l'esercizio", "300,00", "280,00"),
                 (30, "Debiti verso banche oltre l'esercizio", "200,00", "220,00"),
                 (30, "Debiti verso fornitori", "500,00", "500,00"),
                 (30, "Debiti tributari", "150,00", "140,00"),
                 (30, "Debiti verso istituti previdenziali", "50,00", "40,00"),
                 (30, "Totale", "1.200,00", "1.180,00")]
    y = 80
    for x, testo, a, b in dettaglio:
        _riga(tabella_nota, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    prosa = doc.new_page(width=595, height=842)
    prosa.insert_text((30, 40), "Informazioni ex art. 2427 del codice civile", fontname=FONT, fontsize=9)
    for i in range(10):
        prosa.insert_text((30, 70 + i * 14), "Testo descrittivo privo di importi.", fontname=FONT, fontsize=8)

    doc.save(path)
    return path


def pdf_intestazione_lunga_ce(path: str) -> str:
    """Una pagina CE 'quattro sezioni': intestazione aziendale lunga (22 righe brevi) prima delle
    parole di sezione ("COSTI, SPESE E PERDITE" / "RICAVI E PROFITTI"), che finiscono oltre le
    prime 15 righe ma ben dentro i primi 1500 caratteri (rilievo del bench reale, Task 7b:
    una finestra di sole righe perdeva questo CE)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for i in range(22):
        page.insert_text((30, 30 + i * 12), f"RIGA INTESTAZIONE AZIENDALE NUMERO {i + 1}", fontname=FONT, fontsize=7)
    y0 = 30 + 22 * 12
    page.insert_text((30, y0), "COSTI, SPESE E PERDITE", fontname=FONT, fontsize=9)
    page.insert_text((30, y0 + 14), "RICAVI E PROFITTI", fontname=FONT, fontsize=9)
    page.insert_text((30, y0 + 30), "CONTO CONTO DESCRIZIONE CONTO DESCRIZIONE CONTO SALDO SALDO", fontname=FONT, fontsize=8)
    conti = [("61", "MATERIE PRIME", "1.200,00"), ("62", "SERVIZI", "600,00"), ("63", "PERSONALE", "500,00"),
             ("71", "PROVENTI DI VENDITA", "3.000,00"), ("72", "ALTRI PROVENTI", "150,00")]
    y = y0 + 50
    for codice, testo, saldo in conti:
        _riga(page, y, [(30, codice, False), (90, testo, False), (400, saldo, True)])
        y += 14
    doc.save(path)
    return path


def pdf_bilancio_verifica_senza_titoli(path: str) -> str:
    """Cinque pagine di un bilancio di verifica (mastro/conto puro), senza nessun titolo di
    prospetto ne' SP ne' CE: l'intestazione di colonna e' identica su tutte, ma senza un titolo a
    dimostrarlo nessuna pagina puo' dirsi la continuazione di un'altra (rilievo del bench reale,
    Task 7b: un vero bilancio di verifica misto SP/CE, riusando la stessa mappa su 6 pagine
    diverse, e' uscito sbilanciato). Ognuna resta un blocco, e una chiamata, a se'."""
    doc = fitz.open()
    intestazione = "CONTO DESCRIZIONE SALDO SALDO"
    pagine_conti = [
        ("101", "IMMOBILIZZAZIONI MATERIALI", "1.500,00"),
        ("111", "CREDITI V/CLIENTI", "800,00"),
        ("120", "BANCA C/C", "250,00"),
        ("401", "FORNITORI ITALIA", "900,00"),
        ("601", "MATERIE PRIME", "1.200,00"),
    ]
    for codice, testo, saldo in pagine_conti:
        page = doc.new_page(width=595, height=842)
        page.insert_text((30, 40), intestazione, fontname=FONT, fontsize=8)
        y = 60
        for k in range(6):
            _riga(page, y, [(30, f"{codice}.{k:02d}", False), (90, testo, False), (400, saldo, True)])
            y += 14
    doc.save(path)
    return path


MAPPA_CONTRAPPOSTE = {
    "tipo_pagina": "prospetto_sp", "disposizione": "sezioni_contrapposte", "schema": "piano_dei_conti_gerarchico",
    "sezioni": [
        {"posizione": "sinistra", "contenuto": "attivo", "colonne": [
            {"ruolo": "saldo_non_rettificato", "intestazione": "Saldo non rettificato"},
            {"ruolo": "rettifiche", "intestazione": "Rettifiche"},
            {"ruolo": "saldo_finale", "intestazione": "Saldo finale"}]},
        {"posizione": "destra", "contenuto": "passivo", "colonne": [
            {"ruolo": "saldo_non_rettificato", "intestazione": "Saldo non rettificato"},
            {"ruolo": "rettifiche", "intestazione": "Rettifiche"},
            {"ruolo": "saldo_finale", "intestazione": "Saldo finale"}]}],
    "continuazione": False, "codici_conto": True, "totali_stampati": True, "anno_precedente": False,
    "negativi": "segno_meno", "fondi_ammortamento": "nel_passivo", "note": "", "pagina": 1,
}

MAPPA_COLONNA_UNICA = {
    "tipo_pagina": "prospetto_sp", "disposizione": "colonna_unica", "schema": "riclassificato_con_codici_ivcee",
    "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": [
        {"ruolo": "saldo_corrente", "intestazione": "Importo corrente"},
        {"ruolo": "saldo_precedente", "intestazione": "Importo comparato"}]}],
    "continuazione": False, "codici_conto": True, "totali_stampati": True, "anno_precedente": True,
    "negativi": "segno_meno", "fondi_ammortamento": "righe_negative_nell_attivo", "note": "", "pagina": 1,
}


def _scrivi_prospetto_irap(page) -> None:
    """Le righe di pagina 6 del pilota FORMETAL-TEST (Task 28): il prospetto di
    rideterminazione del risultato ai fini IRAP, non il conto economico. "Rettifiche costi" e
    "Rettifiche ricavi" sono due righe stampate separatamente da diverse righe di conto (una
    struttura fedele a quella misurata sul file reale, brief del task): un titolo di prospetto
    letto senza limite di riga le fondeva in un solo match "costi...ricavi", e sedici righe da
    100,00 (le percentuali di indeducibilita') finivano lette come ricavi."""
    righe = [
        "RAGIONE SOCIALE S.R.L.",
        "RIDETERMINAZIONE RISULTATO D'ESERCIZIO AI FINI I.R.A.P. AL 30/04/2026",
        "Utile / Perdita %                                    70.353,09",
        "Rettifiche costi",
        "68/05/150 COMP.AMM.-CO.CO.CO.(SOCIspa-srl)   38.333,28   100,00   38.333,28",
        "72/05/010 SALARI E STIPENDI                   1.809,60   100,00    1.809,60",
        "*** Totale rettifiche costi",
        "VARIAZIONI IN DIMINUZIONE",
        "Rettifiche ricavi",
        "80/01/010 PROVENTI STRAORDINARI               2.000,00   100,00    2.000,00",
    ]
    y = 40
    for riga in righe:
        page.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14


def pdf_prospetto_irap_rideterminazione(path: str) -> str:
    """Una pagina sola, il prospetto IRAP di `_scrivi_prospetto_irap` (Task 28, test 1)."""
    doc = fitz.open()
    _scrivi_prospetto_irap(doc.new_page(width=595, height=842))
    doc.save(path)
    return path


def pdf_prospetto_ires_costi_indeducibili(path: str) -> str:
    """Pagina 5 del pilota FORMETAL-TEST (Task 28): il prospetto IRES dei costi parzialmente
    indeducibili / ricavi imponibili aggiuntivi, non il conto economico. Una riga di conto
    contiene letteralmente "COSTI D'IMPIANTO" — l'occorrenza di "costi" piu' vicina alla testa
    pagina che il vecchio pattern senza limite di riga risolveva (misurato nel brief del task:
    "va da «COSTI D'IMPIANTO» a «Ricavi imponibili»") — e "Ricavi imponibili" arriva centinaia
    di caratteri dopo, in un'altra riga stampata, dopo le righe di conto (Task 28, test 2)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    righe = [
        "RAGIONE SOCIALE S.R.L.",
        "RIDETERMINAZIONE DEL REDDITO IMPONIBILE AI FINI I.R.ES. AL 30/04/2026",
        "Costi non deducibili",
        "68/05/320 SPESE TELEFONICHE                      723,52    20,00      144,70",
        "68/05/341 PASTI/SOGGIORNI-SPESE DI RAPPRES     1.310,94    25,00      327,74",
        "68/02/010 AMM.TO COSTI D'IMPIANTO E DI AMPLIAMENTO   500,00   50,00   250,00",
        "*** Totale costi non deducibili",
        "Ricavi imponibili",
        "80/01/020 PLUSVALENZE PATRIMONIALI              900,00   100,00    900,00",
    ]
    y = 40
    for riga in righe:
        page.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14
    doc.save(path)
    return path


def pdf_titolo_ce_contrapposte_stessa_riga(path: str) -> str:
    """Titolo di CE a sezioni contrapposte stampato su UNA riga sola — "COSTI, SPESE E
    PERDITE" e "RICAVI E PROFITTI" nella stessa stringa, una sola `insert_text` e quindi una
    sola riga estratta da fitz: il layout per cui l'alternativa `costi\\b.*\\bricavi` di
    TITOLI_CE esiste (Task 28, test 3). Deve restare riconosciuto dopo aver ristretto
    quell'alternativa alla riga stampata."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((30, 40), "COSTI, SPESE E PERDITE          RICAVI E PROFITTI", fontname=FONT, fontsize=9)
    conti = [("61", "MATERIE PRIME", "1.200,00"), ("62", "SERVIZI", "600,00"), ("63", "PERSONALE", "500,00"),
             ("71", "RICAVI DI VENDITA", "3.000,00"), ("72", "ALTRI RICAVI", "150,00")]
    y = 70
    for codice, testo, saldo in conti:
        _riga(page, y, [(30, codice, False), (90, testo, False), (400, saldo, True)])
        y += 14
    doc.save(path)
    return path


def pdf_titolo_ce_semplice(path: str, titolo: str) -> str:
    """Una pagina CE minima con `titolo` in testa e importi a sufficienza: verifica che i
    titoli diretti di TITOLI_CE (CONTO ECONOMICO, SITUAZIONE ECONOMICA) restino riconosciuti
    dopo la correzione dell'alternativa costi/ricavi (Task 28, test 4)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((30, 30), titolo, fontname=FONT, fontsize=10)
    conti = [("61", "MATERIE PRIME", "1.200,00"), ("62", "SERVIZI", "600,00"), ("63", "PERSONALE", "500,00"),
             ("71", "RICAVI DI VENDITA", "3.000,00"), ("72", "ALTRI RICAVI", "150,00")]
    y = 60
    for codice, testo, saldo in conti:
        _riga(page, y, [(30, codice, False), (90, testo, False), (400, saldo, True)])
        y += 14
    doc.save(path)
    return path


def pdf_ce_poi_prospetto_fiscale(path: str) -> str:
    """Due pagine (Task 28, test 5): una pagina di CE vero (titolo proprio, intestazione di
    colonna stampata: "Conto Descrizione Saldo"), seguita dalla pagina fiscale IRAP di
    `_scrivi_prospetto_irap` (nessuna intestazione di colonna propria). Dopo la correzione
    dell'alternativa costi/ricavi la seconda pagina non ha piu' un titolo proprio, quindi
    `blocchi()` deve restituire DUE blocchi, non uno solo — prima della correzione la pagina
    fiscale ereditava il falso titolo "conto economico" ed entrambe finivano in un blocco solo."""
    doc = fitz.open()
    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 30), "CONTO ECONOMICO", fontname=FONT, fontsize=10)
    _riga(ce, 50, [(30, "Conto", False), (90, "Descrizione", False), (400, "Saldo", True)])
    conti = [("61", "MATERIE PRIME", "1.200,00"), ("62", "SERVIZI", "600,00"), ("63", "PERSONALE", "500,00"),
             ("71", "RICAVI DI VENDITA", "3.000,00"), ("72", "ALTRI RICAVI", "150,00")]
    y = 70
    for codice, testo, saldo in conti:
        _riga(ce, y, [(30, codice, False), (90, testo, False), (400, saldo, True)])
        y += 14

    _scrivi_prospetto_irap(doc.new_page(width=595, height=842))
    doc.save(path)
    return path


# --- Lotto import-pdf-snello, fix 6 (continuazioni di pagina perse) ---------------------------


def pdf_xbrl_sp_continuazione_senza_date(path: str) -> str:
    """Attivo su pagina 1 (titolo + le due date di legge), passivo su pagina 2 SENZA ripetere
    ne' il titolo ne' le date in testa: una vera continuazione, come budget_671 (fix 6a).
    `mappa_xbrl` deve riconoscerla comunque, non solo quando le date combaciano esattamente."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(p1, 60, intest)
    righe_p1 = [(30, "B) Immobilizzazioni", "", ""),
                (34, "Totale immobilizzazioni (B)", "900,00", "950,00"),
                (30, "C) Attivo circolante", "", ""),
                (34, "Totale attivo circolante (C)", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_p1:
        _riga(p1, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    p2 = doc.new_page(width=595, height=842)  # nessun titolo, nessuna data in testa
    righe_p2 = [(30, "A) Patrimonio netto", "", ""),
                (34, "Totale patrimonio netto", "700,00", "650,00"),
                (30, "D) Debiti", "", ""),
                (34, "Totale debiti", "500,00", "500,00"),
                (30, "Totale passivo", "1.200,00", "1.150,00")]
    y = 40
    for x, testo, a, b in righe_p2:
        _riga(p2, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14
    doc.save(path)
    return path


def pdf_xbrl_sp_continuazione_oltre_il_limite(path: str) -> str:
    """Attivo su pagina 1 (titolo + date) seguito da TRE pagine senza titolo proprio, tutte con
    importi e nessuna parola di sezione nuova: il limite di 2 pagine di continuazione (fix 6)
    lascia la terza fuori."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(p1, 60, intest)
    righe_p1 = [(30, "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_p1:
        _riga(p1, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    for n in range(3):
        pagina = doc.new_page(width=595, height=842)
        y = 40
        for k in range(3):
            _riga(pagina, y, [(30, f"Voce continuazione {n}.{k}", False),
                              (380, f"{100 + n * 10 + k},00", True), (480, f"{90 + n * 10 + k},00", True)])
            y += 14
    doc.save(path)
    return path


def pdf_xbrl_rendiconto_dopo_ce(path: str) -> str:
    """SP e CE regolari (con titolo e date), seguiti da un vero Rendiconto Finanziario: titolo
    proprio in testa e prosa che contiene "attivita'" dentro preposizioni articolate
    ("dall'attivita'", "dell'attivita'"), con importi a sufficienza da sembrare un prospetto.
    Non deve diventare ne' un falso "stato patrimoniale" (vecchio TITOLI_SP, fix 7) ne' una
    continuazione del CE (fix 6, il testo apre una sezione nuova)."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    righe_sp = [(30, "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_sp:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 40), "Conto economico", fontname=FONT, fontsize=10)
    _riga(ce, 60, intest)
    righe_ce = [(30, "A) Valore della produzione", "2.000,00", "1.800,00"),
                (30, "B) Costi della produzione", "1.500,00", "1.350,00"),
                (30, "21) Utile (perdita) dell'esercizio", "500,00", "450,00")]
    y = 80
    for x, testo, a, b in righe_ce:
        _riga(ce, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    rendiconto = doc.new_page(width=595, height=842)
    righe = [
        "Rendiconto finanziario, metodo indiretto",
        "A. Flussi finanziari derivanti dall'attivita' operativa (metodo indiretto)",
        "Utile (perdita) dell'esercizio                       500,00      450,00",
        "Ammortamenti                                         100,00       90,00",
        "B. Flussi finanziari derivanti dall'attivita' di investimento",
        "Investimenti in immobilizzazioni materiali          -200,00     -150,00",
        "C. Flussi finanziari derivanti dall'attivita' di finanziamento",
        "Rimborso finanziamenti                              -100,00      -80,00",
        "Disponibilita' liquide a fine esercizio               300,00      200,00",
    ]
    y = 40
    for riga in righe:
        rendiconto.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14
    doc.save(path)
    return path


def pdf_xbrl_rendiconto_con_intestazione_ripetuta(path: str) -> str:
    """Come `pdf_xbrl_rendiconto_dopo_ce`, ma il Rendiconto Finanziario ha un'intestazione
    aziendale ripetuta (riga corta, un running header) PRIMA del titolo di sezione: "Rendiconto
    finanziario" e' sulla SECONDA riga di testa, non sulla prima (fix round 1, gap 1: controllare
    solo la riga 0 lasciava passare esattamente questo caso)."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    righe_sp = [(30, "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_sp:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 40), "Conto economico", fontname=FONT, fontsize=10)
    _riga(ce, 60, intest)
    righe_ce = [(30, "A) Valore della produzione", "2.000,00", "1.800,00"),
                (30, "B) Costi della produzione", "1.500,00", "1.350,00"),
                (30, "21) Utile (perdita) dell'esercizio", "500,00", "450,00")]
    y = 80
    for x, testo, a, b in righe_ce:
        _riga(ce, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    rendiconto = doc.new_page(width=595, height=842)
    righe = [
        "ACME SRL - Bilancio al 31-12-2025",
        "Rendiconto finanziario, metodo indiretto",
        "A. Flussi finanziari derivanti dall'attivita' operativa (metodo indiretto)",
        "Utile (perdita) dell'esercizio                       500,00      450,00",
        "Ammortamenti                                         100,00       90,00",
        "B. Flussi finanziari derivanti dall'attivita' di investimento",
        "Investimenti in immobilizzazioni materiali          -200,00     -150,00",
        "C. Flussi finanziari derivanti dall'attivita' di finanziamento",
        "Rimborso finanziamenti                              -100,00      -80,00",
        "Disponibilita' liquide a fine esercizio               300,00      200,00",
    ]
    y = 40
    for riga in righe:
        rendiconto.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14
    doc.save(path)
    return path


def pdf_xbrl_rendiconto_con_attivita_senza_preposizione(path: str) -> str:
    """Come `pdf_xbrl_rendiconto_dopo_ce`, ma la riga che nomina "attivita'" non ha la
    preposizione articolata che il fix 7 esclude ("dall'", "dell'", ...): e' la forma reale di
    budget_671, "(Plusvalenze)/Minusvalenze derivanti dalla cessione di attivita'" (6 parole,
    "di attivita'" - preceduta da uno spazio, non da un apostrofo). Il lookbehind di
    `_ATTIVITA_TITOLO` non la esclude, e la riga corta (<= 6 parole) supera
    `MASSIMO_PAROLE_TITOLO_ATTIVITA`: senza il fix del Task 22 questa pagina di Rendiconto
    Finanziario diventa un falso "stato patrimoniale"."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    righe_sp = [(30, "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_sp:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((30, 40), "Conto economico", fontname=FONT, fontsize=10)
    _riga(ce, 60, intest)
    righe_ce = [(30, "A) Valore della produzione", "2.000,00", "1.800,00"),
                (30, "B) Costi della produzione", "1.500,00", "1.350,00"),
                (30, "21) Utile (perdita) dell'esercizio", "500,00", "450,00")]
    y = 80
    for x, testo, a, b in righe_ce:
        _riga(ce, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    rendiconto = doc.new_page(width=595, height=842)
    rendiconto.insert_text((30, 40), "Rendiconto finanziario, metodo indiretto", fontname=FONT, fontsize=8)
    _riga(rendiconto, 60, intest)
    righe = [
        "A) Flussi finanziari derivanti dall'attivita' operativa (metodo indiretto)",
        "Utile (perdita) dell'esercizio                       500,00      450,00",
        "(Plusvalenze)/Minusvalenze derivanti dalla cessione di attivita'",
        "0                                                       0",
        "1) Utile prima delle imposte, interessi                1.034,00   1.033,00",
        "Ammortamenti                                          200,00       90,00",
    ]
    y = 80
    for riga in righe:
        rendiconto.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14
    doc.save(path)
    return path


def pdf_xbrl_sp_continuazione_tre_pagine_con_totale_passivo(path: str) -> str:
    """Forma reale di budget_671: Attivo su pagina 1 (titolo + date), poi TRE pagine di
    continuazione senza titolo proprio - le prime due generiche (immobilizzazioni/patrimonio
    netto), la TERZA (oltre `MAX_PAGINE_CONTINUAZIONE = 2`) porta la coda di D) DEBITI con
    "Totale debiti" e "Totale passivo" stampati. Senza il fix del Task 22 questa terza pagina
    resta fuori da `pagine_sp` (il tetto di 2 pagine la esclude), perdendo l'intero blocco
    debiti."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(p1, 60, intest)
    righe_p1 = [(30, "B) Immobilizzazioni", "", ""),
                (34, "Totale immobilizzazioni (B)", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_p1:
        _riga(p1, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    p2 = doc.new_page(width=595, height=842)  # continuazione 1, generica
    righe_p2 = [(30, "A) Patrimonio netto", "", ""),
                (34, "I - Capitale", "500,00", "500,00"),
                (34, "II - Riserva legale", "20,00", "15,00"),
                (34, "III - Altre riserve", "80,00", "60,00")]
    y = 40
    for x, testo, a, b in righe_p2:
        _riga(p2, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    p3 = doc.new_page(width=595, height=842)  # continuazione 2, generica
    righe_p3 = [(30, "Totale patrimonio netto", "700,00", "650,00"),
                (34, "B) Fondi per rischi e oneri", "50,00", "40,00"),
                (34, "C) Trattamento di fine rapporto", "30,00", "25,00")]
    y = 40
    for x, testo, a, b in righe_p3:
        _riga(p3, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    p4 = doc.new_page(width=595, height=842)  # continuazione 3, oltre il tetto: la coda dei debiti
    righe_p4 = [(30, "D) Debiti", "", ""),
                (34, "esigibili entro l'esercizio successivo", "300,00", "280,00"),
                (34, "esigibili oltre l'esercizio successivo", "150,00", "130,00"),
                (34, "Totale debiti", "450,00", "410,00"),
                (30, "Totale passivo", "1.200,00", "1.150,00")]
    y = 40
    for x, testo, a, b in righe_p4:
        _riga(p4, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14
    doc.save(path)
    return path


def pdf_sp_poi_rendiconto_senza_ce(path: str) -> str:
    """SP con titolo, seguito DIRETTAMENTE da un Rendiconto Finanziario (nessun CE in mezzo, a
    differenza di `pdf_xbrl_rendiconto_con_attivita_senza_preposizione`): il blocco SP
    immediatamente precedente ha lo STESSO titolo che il vecchio bug avrebbe attribuito per
    errore al Rendiconto ("stato patrimoniale") - la forma che avrebbe fatto FONDERE le due
    pagine in un solo blocco (`blocchi()`), riusando l'immagine della pagina SP per la pagina di
    Rendiconto. Nessuna intestazione di colonna sul Rendiconto: il solo titolo decide la fusione."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]

    sp = doc.new_page(width=595, height=842)
    sp.insert_text((30, 40), "Stato patrimoniale", fontname=FONT, fontsize=10)
    _riga(sp, 60, intest)
    righe_sp = [(30, "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "C) Attivo circolante", "300,00", "200,00"),
                (30, "Totale attivo", "1.200,00", "1.150,00")]
    y = 80
    for x, testo, a, b in righe_sp:
        _riga(sp, y, [(x, testo, False), (380, a, True), (480, b, True)])
        y += 14

    rendiconto = doc.new_page(width=595, height=842)
    rendiconto.insert_text((30, 40), "Rendiconto finanziario, metodo indiretto", fontname=FONT, fontsize=8)
    _riga(rendiconto, 60, intest)
    righe = [
        "A) Flussi finanziari derivanti dall'attivita' operativa (metodo indiretto)",
        "Utile (perdita) dell'esercizio                       500,00      450,00",
        "(Plusvalenze)/Minusvalenze derivanti dalla cessione di attivita'",
        "0                                                       0",
        "1) Utile prima delle imposte, interessi                1.034,00   1.033,00",
        "Ammortamenti                                          200,00       90,00",
    ]
    y = 80
    for riga in righe:
        rendiconto.insert_text((30, y), riga, fontname=FONT, fontsize=8)
        y += 14
    doc.save(path)
    return path
